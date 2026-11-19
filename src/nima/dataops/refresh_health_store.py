"""Bounded single-snapshot policy diagnostics; no execution-policy filesystem checks."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import psycopg
from psycopg.rows import class_row

from nima.dataops.health import HealthError
from nima.dataops.refresh_health import (
    PolicyHealthSample,
    RecentWindow,
    RefreshChild,
    RefreshCycle,
    recent_dates,
    validate_cycle,
)
from nima.ingestion.config import CONNECTOR_VERSION
from nima.intent import IntentError, refresh_intent
from nima.orchestration.refresh import CRON, TIMEZONE, VERSION, business_date
from nima.storage.connection import connect
from nima.storage.postgres import NORMALIZER_VERSION, MigrationError, validate_schema
from nima.storage.refresh import missing_dates
from nima.workflows.recovery import RecoveryBudget


@dataclass(frozen=True)
class _PolicyRow:
    policy_id: UUID
    start_date: date
    state: str
    last_tick_at: datetime | None
    retired: bool
    sampled_at: datetime
    configuration_bytes: int


@dataclass(frozen=True)
class _CycleRow:
    cycle_id: UUID
    business_date: date
    completed_at: datetime | None
    query_dates: list[date]


@dataclass(frozen=True)
class _ChildRow:
    query_date: date
    request_id: UUID
    run_id: UUID | None
    dispatch_state: str
    completed_at: datetime | None
    source_observed_at: datetime | None
    updated_at: datetime
    status: str
    started_at: datetime | None
    executions: int
    attempts: int
    projection_batches: int
    dispatches: int


def read_snapshot(dsn: str, policy_id: UUID) -> PolicyHealthSample:
    if not isinstance(policy_id, UUID) or not isinstance(dsn, str) or not dsn.strip():
        raise HealthError("refresh_health_configuration")
    try:
        with connect(dsn) as c, c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            c.execute("SET LOCAL TIME ZONE 'UTC'")
            c.execute("SET LOCAL statement_timeout = 5000")
            c.execute("SET LOCAL lock_timeout = 2000")
            c.execute("SET LOCAL row_security = off")
            validate_schema(c)
            with c.cursor(row_factory=class_row(_PolicyRow)) as cursor:
                policy = cursor.execute(
                    """SELECT p.policy_id,p.start_date,p.state,p.last_tick_at,
                    EXISTS(SELECT 1 FROM nima.refresh_retirements r
                        WHERE r.policy_id=p.policy_id) retired,
                    clock_timestamp() sampled_at,
                    octet_length(p.configuration::text) configuration_bytes
                    FROM nima.refresh_policies p WHERE p.policy_id=%s""",
                    (policy_id,),
                ).fetchone()
            if policy is None:
                raise HealthError("refresh_health_unavailable")
            if policy.configuration_bytes > 16 * 1024:
                raise HealthError("refresh_health_limit")
            raw = c.execute(
                "SELECT configuration,configuration_sha256 FROM nima.refresh_policies "
                "WHERE policy_id=%s",
                (policy_id,),
            ).fetchone()
            if raw is None:
                raise HealthError("refresh_health_evidence")
            saved = refresh_intent(raw[0], raw[1])
            if saved.start != policy.start_date:
                raise HealthError("refresh_health_evidence")
            compatible = (
                saved.failure(CONNECTOR_VERSION, NORMALIZER_VERSION, VERSION, CRON, TIMEZONE)
                is None
            )
            day = business_date(policy.sampled_at)
            end = date.fromordinal(day.toordinal() - 1)
            completed = c.execute(
                """SELECT count(DISTINCT query_date) FROM nima.refresh_windows
                WHERE policy_id=%s AND completed_at IS NOT NULL AND query_date BETWEEN %s AND %s""",
                (policy_id, saved.start, end),
            ).fetchone()
            if completed is None or not isinstance(completed[0], int):
                raise HealthError("refresh_health_evidence")
            gaps = missing_dates(c, policy_id, saved.start, end)
            due = recent_dates(saved.start, day)
            with c.cursor(row_factory=class_row(RecentWindow)) as cursor:
                observations = cursor.execute(
                    """SELECT DISTINCT ON(w.query_date) w.query_date,
                    w.source_observed_at observed_at,cy.business_date latest_business_date
                    FROM nima.refresh_windows w
                    JOIN nima.refresh_cycles cy USING(cycle_id,policy_id)
                    WHERE w.policy_id=%s AND w.completed_at IS NOT NULL AND w.query_date=ANY(%s)
                    ORDER BY w.query_date,cy.business_date DESC LIMIT 7""",
                    (policy_id, list(due)),
                ).fetchall()
            observed = {r.query_date: r for r in observations}
            with c.cursor(row_factory=class_row(_CycleRow)) as cursor:
                selected = cursor.execute(
                    """SELECT cycle_id,business_date,completed_at,query_dates
                    FROM nima.refresh_cycles WHERE policy_id=%s
                    ORDER BY (completed_at IS NULL) DESC,business_date DESC LIMIT 1""",
                    (policy_id,),
                ).fetchone()
            cycle = None
            if selected is not None:
                with c.cursor(row_factory=class_row(_ChildRow)) as cursor:
                    rows = cursor.execute(
                        """SELECT w.query_date,w.request_id,r.run_id,w.dispatch_state,
                        w.completed_at,w.source_observed_at,r.updated_at,r.status,r.started_at,
                        r.executions,r.attempts,r.projection_batches,
                        (SELECT count(*) FROM nima.workflow_dispatches d
                            WHERE d.request_id=r.request_id) dispatches
                        FROM nima.refresh_windows w JOIN nima.workflow_requests r USING(request_id)
                        WHERE w.policy_id=%s AND w.cycle_id=%s ORDER BY w.query_date LIMIT 15""",
                        (policy_id, selected.cycle_id),
                    ).fetchall()
                children = tuple(
                    RefreshChild(
                        r.query_date,
                        r.request_id,
                        r.run_id,
                        r.dispatch_state,
                        r.completed_at,
                        r.source_observed_at,
                        r.updated_at,
                        RecoveryBudget(
                            r.status,
                            r.started_at,
                            r.executions,
                            r.attempts,
                            r.projection_batches,
                            r.dispatches,
                        ),
                    )
                    for r in rows
                )
                cycle = RefreshCycle(
                    selected.cycle_id,
                    selected.business_date,
                    selected.completed_at,
                    tuple(selected.query_dates),
                    children,
                )
                validate_cycle(cycle, saved.start)
            return PolicyHealthSample(
                policy_id,
                policy.sampled_at,
                saved.start,
                policy.state,
                policy.last_tick_at,
                policy.retired,
                compatible,
                max(0, (day - saved.start).days) - completed[0],
                gaps,
                tuple(observed.get(d, RecentWindow(d, None, None)) for d in due),
                cycle,
            )
    except MigrationError:
        raise HealthError("refresh_health_schema") from None
    except psycopg.Error:
        raise HealthError("refresh_health_database") from None
    except IntentError:
        raise HealthError("refresh_health_evidence") from None
