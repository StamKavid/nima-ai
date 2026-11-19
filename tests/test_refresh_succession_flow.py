"""Explicit generation changes retain evidence and earn fresh coverage separately."""

import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from nima.__main__ import main
from nima.ingestion.resume import resume
from nima.orchestration.pipeline import prepare_request
from nima.storage.refresh import RefreshStore
from nima.storage.refresh_lifecycle import retire
from nima.storage.refresh_progress import reconcile, show
from nima.storage.refresh_succession import supersede
from nima.storage.workflows import RequestStore, WorkflowError
from tests.test_collection import Clock, body
from tests.test_graph_support import database_snapshot
from tests.test_refresh_progress import finish
from tests.test_refresh_store import DAY, new_policy
from tests.test_refresh_succession_store import retired


def test_actual_cli_creates_paused_successor_without_source_or_engine(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old, new = retired(pg_dsn, tmp_path / "raw")
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    monkeypatch.delenv("PREFECT_API_URL", raising=False)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Creating a successor contacted the source or engine")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    assert (
        main(
            [
                "refresh",
                "supersede",
                str(old),
                "--successor-id",
                str(new),
                "--authorize-new-budgets",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["successor_state"] == "paused" and result["new_budgets_authorized"] is True
    assert pg_dsn not in output and str(tmp_path) not in output
    assert "database_principal" not in output and not (tmp_path / "raw").exists()
    status = show(RefreshStore(pg_dsn), new, DAY)
    links = status["policy_links"]
    assert isinstance(links, list) and links[0]["predecessor_id"] == str(old)
    assert status["execution_enabled"] is False and status["missing_days"] == 2


@pytest.mark.parametrize("runtime_change", ["normalizer", "unsupported_profile"])
def test_new_processing_pins_or_unsupported_profile_never_rewrite_old_intent(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runtime_change: str
) -> None:
    from nima.storage import refresh

    old, new = retired(pg_dsn, tmp_path / "raw")
    store = RefreshStore(pg_dsn)
    original = store.saved(old)
    before = database_snapshot(pg_dsn)
    if runtime_change == "unsupported_profile":
        monkeypatch.setattr(refresh, "VERSION", "synthetic-unsupported")
        with pytest.raises(WorkflowError, match="^succession_profile$"):
            supersede(pg_dsn, old, new, authorize_new_budgets=True)
        assert database_snapshot(pg_dsn) == before
    else:
        monkeypatch.setattr(refresh, "NORMALIZER_VERSION", "synthetic-next-version")
        supersede(pg_dsn, old, new, authorize_new_budgets=True)
        assert store.saved(new).normalizer_version == "synthetic-next-version"
        assert store.compatibility(new)["execution_compatible"] is True
        assert store.compatibility(old)["execution_compatible"] is False
    assert store.saved(old) == original


def test_expired_generation_stays_failed_while_new_observation_reconciles(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "raw"
    store, old = new_policy(pg_dsn, root, start=DAY - timedelta(days=1))
    with store.lease(old) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        request = session.children(cycle)[0].request
    prepared = prepare_request(pg_dsn, request)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=body(total=1, title="A"))
        )
    ) as client:
        resume(pg_dsn, UUID(str(prepared["run_id"])), client=client, clock=Clock())
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "UPDATE nima.workflow_requests SET started_at=clock_timestamp()-interval '31 minutes',"
            "executions=1,attempts=1,status='deferred',failure='workflow_deadline' "
            "WHERE request_id=%s",
            (request,),
        )
        old_requests = c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall()
        old_versions = c.execute("SELECT to_jsonb(v) FROM nima.record_versions v").fetchall()
    old_files = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(WorkflowError, match="^workflow_deadline$"):
        RequestStore(pg_dsn).begin_dispatch(request, recovery=True)
    retire(pg_dsn, old, "budget_exhausted")
    new = uuid4()
    supersede(pg_dsn, old, new, authorize_new_budgets=True)
    with store.lease(new) as session:
        with pytest.raises(WorkflowError, match="^policy_paused$"):
            session.cycle(DAY)
        session.state("enabled")  # Explicit fixture-only collection authorization.
        next_cycle = session.cycle(DAY)
        assert next_cycle is not None
        fresh = session.children(next_cycle)[0].request
        assert fresh != request
        finish(pg_dsn, fresh, title="B")
        assert reconcile(session)
    assert show(store, old, DAY)["missing_days"] == 1
    assert show(store, new, DAY)["missing_days"] == 0
    assert all(p.read_bytes() == b for p, b in old_files.items())
    with psycopg.connect(pg_dsn) as c:
        assert (
            c.execute(
                "SELECT to_jsonb(r) FROM nima.workflow_requests r WHERE request_id=%s", (request,)
            ).fetchall()
            == old_requests
        )
        versions = c.execute("SELECT to_jsonb(v) FROM nima.record_versions v").fetchall()
        assert len(versions) == 2 and all(v in versions for v in old_versions)
        assert c.execute("SELECT count(*) FROM nima.observations").fetchone() == (2,)
