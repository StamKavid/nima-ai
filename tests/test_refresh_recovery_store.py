"""Actual dispatch reservations retain original intent, budgets and acknowledgements."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.storage.postgres import migrate
from nima.storage.workflows import RequestStore, WorkflowError, source_session
from tests.test_collection import QUERY


def submitted(dsn: str, root: Path) -> tuple[RequestStore, UUID]:
    migrate(dsn)
    store, request = RequestStore(dsn), uuid4()
    store.submit(request, QUERY, root)
    return store, request


def test_recovery_cap_counts_original_unknown_and_pending_sends(
    pg_dsn: str, tmp_path: Path
) -> None:
    store, request = submitted(pg_dsn, tmp_path / "raw")
    original = store.begin_dispatch(request)
    store.finish_dispatch(original, None)
    for _ in range(3):
        store.begin_dispatch(request, recovery=True)
    with pytest.raises(WorkflowError, match="^recovery_dispatch_limit$"):
        store.begin_dispatch(request, recovery=True)
    status = store.show(request)
    assert status["dispatches"] == status["unknown_dispatches"] == 4
    assert status["attempts"] == status["executions"] == 0
    assert status["run_id"] is None and not (tmp_path / "raw").exists()


def test_concurrent_final_reservation_consumes_one_slot(pg_dsn: str, tmp_path: Path) -> None:
    store, request = submitted(pg_dsn, tmp_path / "raw")
    for _ in range(3):
        store.begin_dispatch(request)

    def reserve(_: int) -> str:
        try:
            store.begin_dispatch(request, recovery=True)
        except WorkflowError as error:
            return error.reason
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == ["recovery_dispatch_limit", "reserved"]
    assert store.show(request)["dispatches"] == 4


@pytest.mark.parametrize(
    "assignment,reason",
    [
        ("executions=4", "workflow_execution_limit"),
        ("attempts=300", "workflow_attempt_limit"),
        ("projection_batches=100", "projection_budget"),
        ("started_at=clock_timestamp()-interval '31 minutes'", "workflow_deadline"),
        ("started_at=clock_timestamp()+interval '1 minute'", "recovery_clock"),
        ("status='complete'", "recovery_complete"),
    ],
)
def test_exhausted_requests_do_not_gain_a_dispatch_or_reset_history(
    pg_dsn: str, tmp_path: Path, assignment: str, reason: str
) -> None:
    from psycopg import sql

    store, request = submitted(pg_dsn, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        c.execute(sql.SQL("UPDATE nima.workflow_requests SET ") + sql.SQL(assignment))
        before = c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall()
    with pytest.raises(WorkflowError, match="^" + reason + "$"):
        store.begin_dispatch(request, recovery=True)
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall() == before
        assert c.execute("SELECT count(*) FROM nima.workflow_dispatches").fetchone() == (0,)


def test_shared_source_session_excludes_collection_without_budget_side_effects(
    pg_dsn: str, tmp_path: Path
) -> None:
    store, request = submitted(pg_dsn, tmp_path / "raw")
    with (
        source_session(pg_dsn),
        pytest.raises(WorkflowError, match="^source_busy$"),
        store.source_lease(request),
    ):
        pytest.fail("Collection acquired the recovery source lock")
    with (
        store.source_lease(request),
        pytest.raises(WorkflowError, match="^source_busy$"),
        source_session(pg_dsn),
    ):
        pytest.fail("Recovery acquired an active collector's source lock")
    assert store.show(request)["attempts"] == store.show(request)["executions"] == 0
