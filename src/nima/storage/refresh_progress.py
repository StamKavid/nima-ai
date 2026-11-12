"""Bounded, read-only freshness reports; completed query dates are not an update cursor."""

from datetime import date, datetime, timedelta
from typing import cast
from uuid import UUID

from nima.orchestration.pipeline import finalize_request
from nima.orchestration.refresh import select_dates
from nima.storage.refresh import RefreshSession, RefreshStore, missing_dates
from nima.storage.workflows import RequestStore, WorkflowError, _db


def reconcile(session: RefreshSession) -> bool:
    """Verify at most 14 saved children before advancing any coverage evidence."""
    row = session.connection.execute(
        "SELECT cycle_id,cardinality(query_dates) FROM nima.refresh_cycles "
        "WHERE policy_id=%s AND completed_at IS NULL",
        (session.policy_id,),
    ).fetchone()
    if row is None:
        return True
    cycle, expected = row
    children = session.connection.execute(
        "SELECT request_id FROM nima.refresh_windows WHERE cycle_id=%s "
        "AND completed_at IS NULL ORDER BY query_date",
        (cycle,),
    ).fetchall()
    for (request,) in children:
        request = cast(UUID, request)
        status = RequestStore(session.store.dsn).show(request)
        if not status["normalization_complete"]:
            continue
        try:
            result = finalize_request(session.store.dsn, request)
        except WorkflowError as exc:
            if exc.reason in {"collection_incomplete", "projection_incomplete"}:
                continue
            raise
        observed = session.connection.execute(
            "SELECT max(observed_at) FROM nima.run_pages WHERE run_id=%s",
            (result["run_id"],),
        ).fetchone()
        if observed is None or observed[0] is None:
            continue
        session.connection.execute(
            "UPDATE nima.refresh_windows SET completed_at=clock_timestamp(),source_observed_at=%s "
            "WHERE request_id=%s AND completed_at IS NULL",
            (observed[0], request),
        )
    count = session.connection.execute(
        "SELECT count(*) FROM nima.refresh_windows WHERE cycle_id=%s AND completed_at IS NOT NULL",
        (cycle,),
    ).fetchone()
    if count != (expected,):
        return False
    session.connection.execute(
        "UPDATE nima.refresh_cycles SET completed_at=clock_timestamp() WHERE cycle_id=%s",
        (cycle,),
    )
    return True


def show(store: RefreshStore, policy_id: UUID, day: date) -> dict[str, object]:
    policy = store.options(policy_id)
    end = day - timedelta(days=1)
    with _db(store.dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        state = connection.execute(
            "SELECT state,last_tick_at FROM nima.refresh_policies WHERE policy_id=%s",
            (policy_id,),
        ).fetchone()
        if state is None:
            raise WorkflowError("policy_unavailable")
        missing = missing_dates(connection, policy_id, policy.start, end)
        count = connection.execute(
            "SELECT count(DISTINCT query_date) FROM nima.refresh_windows "
            "WHERE policy_id=%s AND completed_at IS NOT NULL AND query_date BETWEEN %s AND %s",
            (policy_id, policy.start, end),
        ).fetchone()
        successful = cast(tuple[int], count)[0]
        recent_days = select_dates(policy, day, ())
        rows = connection.execute(
            "SELECT w.query_date,max(w.source_observed_at),max(c.business_date) "
            "FROM nima.refresh_windows w JOIN nima.refresh_cycles c USING(cycle_id,policy_id) "
            "WHERE w.policy_id=%s AND w.query_date=ANY(%s) AND w.completed_at IS NOT NULL "
            "GROUP BY w.query_date",
            (policy_id, list(recent_days)),
        ).fetchall()
        by_day = {r[0]: r for r in rows}
        recent: list[dict[str, object]] = []
        for query_day in recent_days:
            entry = by_day.get(query_day)
            recent.append(
                {
                    "query_date": query_day.isoformat(),
                    "last_observed_at": cast(datetime, entry[1]).isoformat() if entry else None,
                    "reobserved": bool(entry and cast(date, entry[2]) >= day),
                }
            )
        cycle = connection.execute(
            "SELECT cycle_id,business_date,completed_at FROM nima.refresh_cycles "
            "WHERE policy_id=%s ORDER BY business_date DESC LIMIT 1",
            (policy_id,),
        ).fetchone()
        children = []
        if cycle:
            children = connection.execute(
                "SELECT w.query_date,w.request_id,w.dispatch_state,w.completed_at IS NOT NULL, "
                "r.status,r.failure FROM nima.refresh_windows w JOIN nima.workflow_requests r "
                "USING(request_id) WHERE w.cycle_id=%s ORDER BY query_date",
                (cycle[0],),
            ).fetchall()
    blocked = None
    if cycle and cycle[2] is None:
        blocked = "work_unresolved"
        if any(not r[3] and r[2] == "sending" for r in children):
            blocked = "dispatch_unknown"
        elif any(not r[3] and r[4] in {"partial", "failed", "deferred"} for r in children):
            blocked = "child_incomplete"
    fresh = sum(bool(r["reobserved"]) for r in recent)
    through = (missing[0] - timedelta(days=1)) if missing else end
    return {
        "policy_id": str(policy_id),
        "state": state[0],
        "enabled": state[0] == "enabled",
        "schedule_reconciliation": "required" if state[0] == "pending" else "last_acknowledged",
        "business_date": day.isoformat(),
        "coverage_start": policy.start.isoformat(),
        "query_dates_through": through.isoformat() if through >= policy.start else None,
        "missing_days": max(0, (end - policy.start).days + 1) - successful,
        "oldest_missing_dates": [d.isoformat() for d in missing],
        "recent": recent,
        "recent_status": (
            "not_due"
            if not recent
            else "complete"
            if fresh == len(recent)
            else "partial"
            if fresh
            else "stale"
        ),
        "last_tick_at": cast(datetime, state[1]).isoformat() if state[1] else None,
        "cycle_id": str(cycle[0]) if cycle else None,
        "cycle_business_date": cast(date, cycle[1]).isoformat() if cycle else None,
        "blocked_reason": blocked,
        "worker_liveness": "unknown",
        "children": [
            {
                "query_date": cast(date, r[0]).isoformat(),
                "request_id": str(r[1]),
                "dispatch_state": r[2],
                "evidence_reconciled": r[3],
                "request_state": r[4],
                "failure": r[5],
            }
            for r in children
        ],
    }
