"""Coverage advances from completed evidence, never an accepted dispatch or partial page."""

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx
import psycopg
import pytest

from nima.orchestration.pipeline import (
    collect_request,
    finalize_request,
    prepare_request,
    project_request,
)
from nima.storage.refresh_progress import reconcile, show
from tests.test_collection import Clock, body
from tests.test_refresh_store import DAY, new_policy


def finish(dsn: str, request: UUID, *, title: str = "A", empty: bool = False) -> None:
    prepare_request(dsn, request)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=body(total=0 if empty else 1, title=title))
        )
    ) as client:
        collect_request(dsn, request, client=client, clock=Clock())
    project_request(dsn, request)
    finalize_request(dsn, request)


def test_gaps_and_overlap_have_distinct_truthful_progress(pg_dsn: str, tmp_path: Path) -> None:
    store, policy = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        children = session.children(cycle)
        finish(pg_dsn, children[1].request, empty=True)
        assert not reconcile(session)
    status = show(store, policy, DAY)
    assert status["query_dates_through"] is None and status["missing_days"] == 1
    assert status["recent_status"] == "partial"
    with store.lease(policy) as session:
        finish(pg_dsn, children[0].request)
        assert reconcile(session)
        assert reconcile(session)
    status = show(store, policy, DAY)
    assert status["query_dates_through"] == (DAY - timedelta(days=1)).isoformat()
    assert status["recent_status"] == "complete" and status["missing_days"] == 0
    assert show(store, policy, DAY + timedelta(days=1))["recent_status"] == "stale"
    with store.lease(policy) as session:
        next_cycle = session.cycle(DAY + timedelta(days=1))
        assert next_cycle is not None
        next_children = session.children(next_cycle)
        repeated = next(c for c in next_children if c.day == children[0].day)
        assert repeated.request != children[0].request
        finish(pg_dsn, repeated.request, title="B")
        reconcile(session)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.record_versions").fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM nima.observations").fetchone() == (2,)


def test_false_complete_status_does_not_advance_coverage(pg_dsn: str, tmp_path: Path) -> None:
    store, policy = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        children = session.children(cycle)
        prepare_request(pg_dsn, children[0].request)
        with psycopg.connect(pg_dsn) as connection:
            connection.execute("UPDATE nima.workflow_requests SET status='complete'")
        assert not reconcile(session)
    status = show(store, policy, DAY)
    assert status["query_dates_through"] is None and status["missing_days"] == 2


@pytest.mark.parametrize("exhausted", [False, True])
def test_quarantine_or_exhaustion_blocks_new_cycle_without_new_budget(
    pg_dsn: str, tmp_path: Path, exhausted: bool
) -> None:
    import json

    from nima.storage.workflows import WorkflowError

    store, policy = new_policy(pg_dsn, tmp_path / "raw", start=DAY - timedelta(days=1))
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        child = session.children(cycle)[0]
        prepare_request(pg_dsn, child.request)
        payload = json.loads(body(total=1))
        payload["content"][0].pop("referenceNumber")
        if exhausted:
            with psycopg.connect(pg_dsn) as connection:
                connection.execute("UPDATE nima.workflow_requests SET attempts=300")
        with (
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda _: (
                        pytest.fail("Budget failed")
                        if exhausted
                        else httpx.Response(200, content=json.dumps(payload).encode())
                    )
                )
            ) as client,
            pytest.raises(WorkflowError),
        ):
            collect_request(pg_dsn, child.request, client=client, clock=Clock())
        assert not reconcile(session)
        with pytest.raises(WorkflowError, match="cycle_unresolved"):
            session.cycle(DAY + timedelta(days=1))
        assert session.children(cycle)[0].request == child.request
    assert show(store, policy, DAY)["query_dates_through"] is None
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.workflow_requests").fetchone() == (1,)
