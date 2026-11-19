"""Real waiting transactions recheck committed fences and quotas after row locks."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.storage.workflows import RequestStore, WorkflowError
from nima.workflows.recovery import RecoveryBudget
from tests.test_refresh_recovery_control import child
from tests.test_refresh_recovery_store import submitted


def configured(dsn: str, isolation: str) -> str:
    value = make_conninfo(
        dsn, options="-c default_transaction_isolation=" + isolation.replace(" ", "\\ ")
    )
    with psycopg.connect(value) as c:
        assert c.execute("SHOW transaction_isolation").fetchone() == (isolation,)
    return value


def waiting(dsn: str, pattern: str) -> None:
    until = time.monotonic() + 5
    with psycopg.connect(dsn, autocommit=True) as monitor:
        while time.monotonic() < until:
            row = monitor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                "AND wait_event_type='Lock' AND query LIKE %s)",
                (pattern,),
            ).fetchone()
            if row == (True,):
                return
            time.sleep(0.01)
    pytest.fail("Expected a real waiting reservation transaction")


@pytest.mark.parametrize("isolation", ["read committed", "repeatable read"])
def test_waiting_dispatch_sees_retirement_committed_before_reservation(
    pg_dsn: str, tmp_path: Path, isolation: str
) -> None:
    _, policy, request = child(pg_dsn, tmp_path / "raw")
    store = RequestStore(configured(pg_dsn, isolation))
    with psycopg.connect(pg_dsn) as retiring, ThreadPoolExecutor(max_workers=1) as pool:
        retiring.execute(
            "INSERT INTO nima.refresh_retirements(policy_id,reason) VALUES (%s,'operator_stop')",
            (policy,),
        )
        future = pool.submit(store.begin_dispatch, request)
        try:
            waiting(pg_dsn, "INSERT INTO nima.workflow_dispatches%")
        finally:
            retiring.commit()
        with pytest.raises(WorkflowError, match="^policy_retired$"):
            future.result(timeout=10)
    assert store.show(request)["dispatches"] == 1


@pytest.mark.parametrize("isolation", ["read committed", "repeatable read"])
def test_waiting_recovery_cannot_use_old_snapshot_to_take_fifth_slot(
    pg_dsn: str, tmp_path: Path, isolation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, request = submitted(pg_dsn, tmp_path / "raw")
    store = RequestStore(configured(pg_dsn, isolation))
    for _ in range(3):
        store.begin_dispatch(request)
    locked, release = Event(), Event()
    original = RecoveryBudget.failure

    def hold(budget: RecoveryBudget, sampled_at: datetime) -> str | None:
        if budget.dispatches == 3:
            locked.set()
            assert release.wait(timeout=5)
        return original(budget, sampled_at)

    monkeypatch.setattr(RecoveryBudget, "failure", hold)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store.begin_dispatch, request, recovery=True)
        try:
            assert locked.wait(timeout=5)
            second = pool.submit(store.begin_dispatch, request, recovery=True)
            waiting(pg_dsn, "SELECT status,started_at,executions,attempts,projection_batches%")
        finally:
            release.set()
        first.result(timeout=10)
        with pytest.raises(WorkflowError, match="^recovery_dispatch_limit$"):
            second.result(timeout=10)
    assert store.show(request)["dispatches"] == 4
