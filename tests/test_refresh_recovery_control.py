"""Recovery validates real saved children before making a local control-plane send."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import Self
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.__main__ import main
from nima.orchestration import dispatch, recovery
from nima.orchestration.config import LocalConfig
from nima.storage.refresh import RefreshStore
from nima.storage.workflows import RequestStore, WorkflowError, source_session
from tests.test_refresh_store import DAY, new_policy


def child(dsn: str, root: Path) -> tuple[RefreshStore, UUID, UUID]:
    store, policy = new_policy(dsn, root)
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        request = session.children(cycle)[0].request
        session.dispatch_state(request, "sending")
    RequestStore(dsn).begin_dispatch(request)
    return store, policy, request


def configuration(monkeypatch: pytest.MonkeyPatch, dsn: str, root: Path) -> None:
    config = LocalConfig("http://127.0.0.1:1/api", dsn, root)
    monkeypatch.setattr(recovery, "local_config", lambda: config)
    monkeypatch.setattr(dispatch, "local_config", lambda: config)
    monkeypatch.setenv("NIMA_DATABASE_URL", dsn)


def test_accepted_recovery_holds_both_locks_and_preserves_request(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store, policy, request = child(pg_dsn, tmp_path / "raw")
    configuration(monkeypatch, pg_dsn, tmp_path / "raw")
    engine_id = uuid4()
    with psycopg.connect(pg_dsn) as c:
        before = c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall()

    class Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(
            self,
            kind: type[BaseException] | None,
            error: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            pass

        async def read_deployment_by_name(self, name: str) -> SimpleNamespace:
            assert name == "nima-kimdis/local"
            return SimpleNamespace(id=uuid4())

        async def create_flow_run_from_deployment(
            self, deployment: UUID, **kwargs: object
        ) -> SimpleNamespace:
            assert kwargs["parameters"] == {"request_id": str(request)}
            with pytest.raises(WorkflowError, match="^policy_busy$"), store.lease(policy):
                pytest.fail("Recovery released the policy lock during RPC")
            with pytest.raises(WorkflowError, match="^source_busy$"), source_session(pg_dsn):
                pytest.fail("Recovery released the source lock during RPC")
            return SimpleNamespace(id=engine_id)

    monkeypatch.setattr("prefect.client.orchestration.PrefectClient", Client)
    for expected in (2, 3):
        assert main(["refresh", "recover", str(policy), "--request-id", str(request)]) == 0
        terminal = capsys.readouterr()
        result = json.loads(terminal.out)
        assert result["policy_id"] == str(policy) and result["request_id"] == str(request)
        assert result["dispatch_status"] == "accepted" and result["dispatches"] == expected
        assert pg_dsn not in terminal.out and str(tmp_path) not in terminal.out
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall() == before
        assert c.execute(
            "SELECT dispatch_state,completed_at FROM nima.refresh_windows WHERE request_id=%s",
            (request,),
        ).fetchone() == ("accepted", None)
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "paused",
        "allocated",
        "foreign",
        "policy_version",
        "request_version",
        "expired",
        "source_busy",
    ],
)
def test_ineligible_recovery_never_reaches_rpc_or_changes_evidence(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from contextlib import nullcontext

    from nima.storage import refresh, workflows
    from tests.test_analytics_snapshot import state

    store, policy, request = child(pg_dsn, tmp_path / "raw")
    configuration(monkeypatch, pg_dsn, tmp_path / "raw")
    expected = "recovery_child"
    if fault == "paused":
        with store.lease(policy) as session:
            session.state("paused")
        expected = "policy_paused"
    elif fault == "allocated":
        with store.lease(policy) as session:
            cycle = session.open_cycle()
            assert cycle is not None
            request = session.children(cycle)[1].request
    elif fault == "foreign":
        request = uuid4()
    elif fault in {"policy_version", "request_version"}:
        target = refresh if fault == "policy_version" else workflows
        monkeypatch.setattr(target, "NORMALIZER_VERSION", "synthetic-next")
        expected = (
            "policy_processing_version"
            if fault == "policy_version"
            else "request_processing_version"
        )
    elif fault == "expired":
        with psycopg.connect(pg_dsn) as c:
            c.execute(
                "UPDATE nima.workflow_requests "
                "SET started_at=clock_timestamp()-interval '31 minutes'"
            )
        expected = "workflow_deadline"
    elif fault == "source_busy":
        expected = "source_busy"

    def forbidden(**kwargs: object) -> None:
        pytest.fail("Ineligible recovery reached the engine RPC")

    monkeypatch.setattr("prefect.client.orchestration.PrefectClient", forbidden)
    before = state(pg_dsn)
    with (
        source_session(pg_dsn) if fault == "source_busy" else nullcontext(),
        pytest.raises(WorkflowError, match="^" + expected + "$"),
    ):
        asyncio.run(recovery.recover_child(policy, request))
    assert state(pg_dsn) == before


def test_unknown_send_retains_same_request_and_consumes_dispatch_headroom(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, policy, request = child(pg_dsn, tmp_path / "raw")
    configuration(monkeypatch, pg_dsn, tmp_path / "raw")

    def unavailable(**kwargs: object) -> None:
        raise RuntimeError("private-sentinel")

    monkeypatch.setattr("prefect.client.orchestration.PrefectClient", unavailable)
    for reason in (
        "engine_unavailable",
        "engine_unavailable",
        "engine_unavailable",
        "recovery_dispatch_limit",
    ):
        assert main(["refresh", "recover", str(policy), "--request-id", str(request)]) == 1
        terminal = capsys.readouterr()
        assert json.loads(terminal.out)["failure"] == reason
        assert "private-sentinel" not in terminal.out + terminal.err
    status = RequestStore(pg_dsn).show(request)
    assert status["dispatches"] == status["unknown_dispatches"] == 4
    assert status["executions"] == status["attempts"] == 0
    assert status["run_id"] is None
