"""Retirement closes future reservations without changing unfinished coverage."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from nima.__main__ import main
from nima.orchestration import dispatch, recovery, refresh_control
from nima.storage.refresh_lifecycle import retire
from nima.storage.refresh_progress import show
from nima.storage.workflows import RequestStore, WorkflowError
from tests.test_collection import QUERY
from tests.test_refresh_recovery_control import child, configuration
from tests.test_refresh_store import DAY, new_policy


def test_sql_only_retirement_cli_keeps_failed_child_and_discloses_no_config(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, policy, request = child(pg_dsn, tmp_path / "raw")
    RequestStore(pg_dsn).outcome(request, "deferred", "workflow_deadline")
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    monkeypatch.delenv("PREFECT_API_URL", raising=False)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Retirement inspected intent/archive or called an external service")

    with monkeypatch.context() as patch:
        patch.setattr(httpx.Client, "request", forbidden)
        patch.setattr(type(store), "saved", forbidden)
        for reused in (False, True):
            assert main(["refresh", "retire", str(policy), "--reason", "budget_exhausted"]) == 0
            output = capsys.readouterr().out
            result = json.loads(output)
            assert result["retired"] is True and result["reused"] is reused
            assert pg_dsn not in output and str(tmp_path) not in output
            assert "database_principal" not in result
    status = show(store, policy, DAY)
    assert status["retired"] is True and status["execution_enabled"] is False
    assert status["blocked_reason"] == "policy_retired" and status["missing_days"] == 2
    children = status["children"]
    assert isinstance(children, list) and children[0]["failure"] == "workflow_deadline"
    assert store.plan(policy, DAY)["retired"] is True


@pytest.mark.parametrize("operation", ["enable", "tick", "recover", "manual"])
def test_retired_policy_refuses_control_before_rpc(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    store, policy, request = child(pg_dsn, tmp_path / "raw")
    config = configuration(monkeypatch, pg_dsn, tmp_path / "raw")
    monkeypatch.setattr(refresh_control, "local_config", lambda: config)
    retire(pg_dsn, policy, "operator_stop")

    def forbidden(**kwargs: object) -> None:
        pytest.fail("Retired policy reached RPC")

    monkeypatch.setattr(refresh_control, "PrefectClient", forbidden)
    monkeypatch.setattr("prefect.client.orchestration.PrefectClient", forbidden)
    with pytest.raises(WorkflowError, match="^policy_retired$"):
        if operation == "enable":
            asyncio.run(refresh_control.change_schedule(policy, enabled=True))
        elif operation == "tick":
            asyncio.run(refresh_control.tick(policy, DAY))
        elif operation == "recover":
            asyncio.run(recovery.recover_child(policy, request))
        else:
            asyncio.run(dispatch.dispatch_request(request))
    assert RequestStore(pg_dsn).show(request)["dispatches"] == 1
    assert show(store, policy, DAY)["retired"] is True


def test_failed_engine_pause_never_reopens_retirement(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, policy, _ = child(pg_dsn, tmp_path / "raw")
    config = configuration(monkeypatch, pg_dsn, tmp_path / "raw")
    monkeypatch.setattr(refresh_control, "local_config", lambda: config)
    retire(pg_dsn, policy, "processing_incompatible")

    def unavailable(**kwargs: object) -> None:
        raise RuntimeError("private-sentinel")

    monkeypatch.setattr(refresh_control, "PrefectClient", unavailable)
    with pytest.raises(WorkflowError, match="^engine_unavailable$"):
        asyncio.run(refresh_control.change_schedule(policy, enabled=False))
    status = show(store, policy, DAY)
    assert status["retired"] is True and status["schedule_reconciliation"] == "required"
    assert status["execution_enabled"] is False
    with store.lease(policy) as session:
        session.state("paused")  # Existing schedule reconciliation's final SQL acknowledgement.
        with pytest.raises(WorkflowError, match="^policy_retired$"):
            session.state("enabled")


@pytest.mark.parametrize("operation", ["enable", "cycle", "window", "dispatch"])
def test_direct_sql_cannot_bypass_retirement(pg_dsn: str, tmp_path: Path, operation: str) -> None:
    store, policy = new_policy(pg_dsn, tmp_path / "raw")
    request, cycle_id = uuid4(), uuid4()
    RequestStore(pg_dsn).submit(request, QUERY, tmp_path / "raw")
    if operation in {"window", "dispatch"}:
        with store.lease(policy) as session:
            session.state("enabled")
            cycle = session.cycle(DAY)
            assert cycle is not None
            cycle_id = cycle.cycle_id
            if operation == "dispatch":
                request = session.children(cycle)[0].request
    retire(pg_dsn, policy, "operator_stop")
    statements: dict[str, tuple[str, tuple[object, ...]]] = {
        "enable": (
            "UPDATE nima.refresh_policies SET state='enabled' WHERE policy_id=%s",
            (policy,),
        ),
        "cycle": (
            "INSERT INTO nima.refresh_cycles(cycle_id,policy_id,business_date,query_dates) "
            "VALUES (%s,%s,%s,%s)",
            (uuid4(), policy, DAY, [DAY - timedelta(days=1)]),
        ),
        "window": (
            "INSERT INTO nima.refresh_windows(cycle_id,policy_id,query_date,request_id) "
            "VALUES (%s,%s,%s,%s)",
            (cycle_id, policy, DAY - timedelta(days=3), request),
        ),
        "dispatch": (
            "INSERT INTO nima.workflow_dispatches(dispatch_id,request_id) VALUES (%s,%s)",
            (uuid4(), request),
        ),
    }
    with (
        psycopg.connect(pg_dsn) as c,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState) as caught,
    ):
        c.execute(*statements[operation])
    assert caught.value.diag.constraint_name == "refresh_policy_live"


def test_inspection_keeps_one_snapshot_across_concurrent_retirement(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date

    from nima.storage import refresh_progress
    from nima.storage.connection import Connection
    from nima.storage.refresh import missing_dates

    store, policy, _ = child(pg_dsn, tmp_path / "raw")

    def interleave(c: Connection, policy_id: UUID, start: date, end: date) -> tuple[date, ...]:
        assert policy_id == policy
        result = missing_dates(c, policy_id, start, end)
        retire(pg_dsn, policy, "operator_stop")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(refresh_progress, "missing_dates", interleave)
        before = show(store, policy, DAY)
    assert before["retired"] is False and before["execution_enabled"] is True
    after = show(store, policy, DAY)
    assert after["retired"] is True and after["execution_enabled"] is False
