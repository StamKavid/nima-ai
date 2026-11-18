"""Saved intent is immutable history; execution compatibility is a separate boundary."""

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from nima.ingestion.config import Limits
from nima.storage import workflows
from nima.storage.postgres import migrate
from nima.storage.workflows import RequestStore, WorkflowError
from tests.test_collection import QUERY


def test_recorded_limits_survive_default_change_and_same_id_resubmission(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    store = RequestStore(pg_dsn)
    request = uuid4()
    root = tmp_path / "raw"
    store.submit(request, QUERY, root)
    with psycopg.connect(pg_dsn) as c:
        before = c.execute(
            "SELECT parameters,parameters_sha256 FROM nima.workflow_requests"
        ).fetchone()
    monkeypatch.setattr(workflows, "Limits", lambda: Limits(max_pages=50, request_timeout=10.0))
    assert store.options(request) == (QUERY, Limits(), root)
    store.submit(request, QUERY, root)
    assert store.options(request) == (QUERY, Limits(), root)
    fresh = uuid4()
    store.submit(fresh, QUERY, tmp_path / "new")
    assert store.options(fresh)[1] == Limits(max_pages=50, request_timeout=10.0)
    with psycopg.connect(pg_dsn) as c:
        assert (
            c.execute(
                "SELECT parameters,parameters_sha256 FROM nima.workflow_requests "
                "WHERE request_id=%s",
                (request,),
            ).fetchone()
            == before
        )


@pytest.mark.parametrize("pin", ["CONNECTOR_VERSION", "NORMALIZER_VERSION"])
def test_historical_request_stays_visible_but_cannot_dispatch_or_take_source_lease(
    pin: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    store = RequestStore(pg_dsn)
    request = uuid4()
    root = tmp_path / "raw"
    store.submit(request, QUERY, root)
    monkeypatch.setattr(workflows, pin, "synthetic-next-version")
    status = store.show(request)
    assert status["execution_compatible"] is False
    assert status["compatibility_failure"] == "request_processing_version"
    store.submit(request, QUERY, root)
    with pytest.raises(WorkflowError, match="^request_processing_version$"):
        store.options(request)
    with pytest.raises(WorkflowError, match="^request_processing_version$"):
        store.begin_dispatch(request)
    with (
        pytest.raises(WorkflowError, match="^request_processing_version$"),
        store.source_lease(request),
    ):
        pytest.fail("Incompatible intent acquired source lease")
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT executions,attempts,source_owner FROM nima.workflow_requests "
            "WHERE request_id=%s",
            (request,),
        ).fetchone() == (0, 0, None)
        assert c.execute("SELECT count(*) FROM nima.workflow_dispatches").fetchone() == (0,)
    assert not root.exists()


@pytest.mark.parametrize("pin", ["CONNECTOR_VERSION", "NORMALIZER_VERSION"])
def test_old_refresh_policy_is_inspectable_and_pausable_but_cannot_activate(
    pin: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import refresh
    from nima.storage.refresh_progress import show
    from tests.test_refresh_store import DAY, new_policy

    store, policy_id = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy_id) as session:
        session.state("enabled")
    before = store.options(policy_id)
    monkeypatch.setattr(refresh, pin, "synthetic-next-version")
    assert store.options(policy_id) == before
    assert store.plan(policy_id, DAY)["execution_compatible"] is False
    status = show(store, policy_id, DAY)
    assert status["state"] == "enabled" and status["enabled"] is True
    assert status["execution_enabled"] is False
    assert status["compatibility_failure"] == "policy_processing_version"
    store.create(policy_id, before)
    with store.lease(policy_id) as session:
        with pytest.raises(WorkflowError, match="^policy_processing_version$"):
            session.cycle(DAY)
        session.state("paused")
        with pytest.raises(WorkflowError, match="^policy_processing_version$"):
            session.state("enabled")
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT state,last_tick_at FROM nima.refresh_policies").fetchone() == (
            "paused",
            None,
        )
        assert c.execute("SELECT count(*) FROM nima.refresh_cycles").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM nima.workflow_requests").fetchone() == (0,)
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize("operation", ["enable", "tick", "children", "send"])
def test_incompatible_policy_cannot_reach_state_changes_or_control_rpc(
    operation: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    from typing import Never

    from nima.orchestration import refresh_control as control
    from nima.orchestration.config import LocalConfig
    from nima.storage import refresh
    from tests.test_analytics_snapshot import state
    from tests.test_refresh_store import DAY, new_policy

    store, policy_id = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy_id) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
    assert cycle is not None
    before = state(pg_dsn)
    monkeypatch.setattr(refresh, "NORMALIZER_VERSION", "synthetic-next-version")
    monkeypatch.setattr(
        control,
        "local_config",
        lambda: LocalConfig("http://localhost:12345/api", pg_dsn, tmp_path / "raw"),
    )

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Incompatible policy reached control RPC")

    monkeypatch.setattr(control, "PrefectClient", forbidden)
    with pytest.raises(WorkflowError, match="^policy_processing_version$"):
        if operation == "enable":
            asyncio.run(control.change_schedule(policy_id, enabled=True))
        elif operation == "tick":
            asyncio.run(control.tick(policy_id, DAY))
        else:
            with store.lease(policy_id) as session:
                if operation == "children":
                    session.children(cycle)
                else:
                    session.dispatch_state(uuid4(), "sending")
    assert state(pg_dsn) == before
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize("pin", ["CRON", "TIMEZONE", "VERSION"])
def test_recorded_policy_profile_survives_changed_runtime_profile(
    pin: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import refresh
    from tests.test_refresh_store import DAY, new_policy

    store, policy_id = new_policy(pg_dsn, tmp_path / "raw")
    policy = store.options(policy_id)
    monkeypatch.setattr(refresh, pin, "synthetic-next-profile")
    assert store.options(policy_id) == policy
    assert store.plan(policy_id, DAY)["compatibility_failure"] == "policy_profile_version"
    with store.lease(policy_id) as session:
        session.state("paused")
        with pytest.raises(WorkflowError, match="^policy_profile_version$"):
            session.state("enabled")


@pytest.mark.parametrize(
    "field",
    [
        "max_pages",
        "max_attempts",
        "max_bytes",
        "requests_per_minute",
        "request_timeout",
        "run_timeout",
        "max_retry_delay",
    ],
)
def test_saved_out_of_profile_limits_are_visible_but_cannot_execute(
    field: str, pg_dsn: str, tmp_path: Path
) -> None:
    import hashlib
    import json

    from psycopg.types.json import Jsonb

    from nima.intent import V1_CEILINGS

    migrate(pg_dsn)
    store = RequestStore(pg_dsn)
    request = uuid4()
    store.submit(request, QUERY, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        row = c.execute(
            "SELECT parameters FROM nima.workflow_requests WHERE request_id=%s", (request,)
        ).fetchone()
        assert row is not None
        p = row[0]
        p["limits"][field] = getattr(V1_CEILINGS, field) + 1
        changed = uuid4()
        digest = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        c.execute(
            "INSERT INTO nima.workflow_requests(request_id,parameters,parameters_sha256) "
            "VALUES (%s,%s,%s)",
            (changed, Jsonb(p), digest),
        )
    assert store.show(changed)["compatibility_failure"] == "request_limits"
    with pytest.raises(WorkflowError, match="^request_limits$"), store.source_lease(changed):
        pytest.fail("Oversized intent took lease")


@pytest.mark.parametrize(
    "bad",
    [
        "hash",
        "format",
        "extra",
        "missing",
        "bad_query",
        "bool_limit",
        "negative_limit",
        "text_limit",
        "relative_root",
        "parent_root",
        "empty_pin",
    ],
)
def test_bad_saved_request_is_never_reinterpreted(bad: str, pg_dsn: str, tmp_path: Path) -> None:
    import hashlib
    import json

    from psycopg.types.json import Jsonb

    migrate(pg_dsn)
    store = RequestStore(pg_dsn)
    request = uuid4()
    store.submit(request, QUERY, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        row = c.execute(
            "SELECT parameters FROM nima.workflow_requests WHERE request_id=%s", (request,)
        ).fetchone()
        assert row is not None
        p = row[0]
        if bad == "format":
            p["format_version"] = "future-format"
        elif bad == "extra":
            p["extra"] = "private-sentinel"
        elif bad == "missing":
            del p["limits"]["max_bytes"]
        elif bad == "bad_query":
            p["query"]["dateFrom"] = "private-sentinel"
        elif bad == "bool_limit":
            p["limits"]["max_pages"] = True
        elif bad == "negative_limit":
            p["limits"]["request_timeout"] = -1
        elif bad == "text_limit":
            p["limits"]["request_timeout"] = "20"
        elif bad == "relative_root":
            p["archive_root"] = "private-sentinel"
        elif bad == "parent_root":
            p["archive_root"] = "/tmp/../private-sentinel"
        elif bad == "empty_pin":
            p["normalizer_version"] = ""
        digest = (
            "0" * 64
            if bad == "hash"
            else hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        )
        changed = uuid4()
        c.execute(
            "INSERT INTO nima.workflow_requests(request_id,parameters,parameters_sha256) "
            "VALUES (%s,%s,%s)",
            (changed, Jsonb(p), digest),
        )
    with pytest.raises(WorkflowError, match="^request_version$"):
        store.show(changed)
    with pytest.raises(WorkflowError, match="^request_version$"):
        store.options(changed)


@pytest.mark.parametrize(
    "bad",
    ["hash", "format", "bool_lag", "window", "cron", "buyers", "start", "extra", "pin", "root"],
)
def test_bad_saved_policy_fails_with_fixed_reason(bad: str, pg_dsn: str, tmp_path: Path) -> None:
    import hashlib
    import json

    from psycopg.types.json import Jsonb

    from tests.test_refresh_store import new_policy

    store, policy_id = new_policy(pg_dsn, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        row = c.execute(
            "SELECT configuration FROM nima.refresh_policies WHERE policy_id=%s", (policy_id,)
        ).fetchone()
        assert row is not None
        p = row[0]
        if bad == "format":
            p["version"] = "future-format"
        elif bad == "bool_lag":
            p["lag"] = True
        elif bad == "window":
            p["overlap"] = 8
        elif bad == "cron":
            p["cron"] = "private-sentinel"
        elif bad == "buyers":
            p["buyers"] = ["21", "21"]
        elif bad == "start":
            p["start_date"] = "private-sentinel"
        elif bad == "extra":
            p["extra"] = "private-sentinel"
        elif bad == "pin":
            p["connector_version"] = "private sentinel"
        elif bad == "root":
            p["archive_root"] = "private-sentinel"
        digest = (
            "0" * 64
            if bad == "hash"
            else hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
        )
        if bad == "start":
            from nima.intent import IntentError, refresh_intent

            with pytest.raises(IntentError):
                refresh_intent(p, digest)
            return
        changed = uuid4()
        c.execute(
            "INSERT INTO nima.refresh_policies"
            "(policy_id,configuration,configuration_sha256,start_date) "
            "VALUES (%s,%s,%s,%s)",
            (changed, Jsonb(p), digest, store.options(policy_id).start),
        )
    with pytest.raises(WorkflowError, match="^policy_invalid$"):
        store.options(changed)


def test_refresh_child_replay_keeps_original_defaults(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_analytics_snapshot import state
    from tests.test_refresh_store import DAY, new_policy

    store, policy_id = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy_id) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        children = session.children(cycle)
    before = state(pg_dsn)
    monkeypatch.setattr(workflows, "Limits", lambda: Limits(max_pages=50))
    with store.lease(policy_id) as session:
        assert session.children(cycle) == children
    assert all(RequestStore(pg_dsn).options(c.request)[1] == Limits() for c in children)
    assert state(pg_dsn) == before


def test_pause_closes_historical_gate_before_unavailable_engine_rpc(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from nima.orchestration import refresh_control as control
    from nima.orchestration.config import LocalConfig
    from nima.storage import refresh
    from tests.test_refresh_store import new_policy

    store, policy_id = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy_id) as session:
        session.state("enabled")
    monkeypatch.setattr(refresh, "NORMALIZER_VERSION", "synthetic-next-version")
    monkeypatch.setattr(
        control,
        "local_config",
        lambda: LocalConfig("http://localhost:12345/api", pg_dsn, tmp_path / "raw"),
    )
    attempted = []

    def unreachable(*args: object, **kwargs: object) -> None:
        with psycopg.connect(pg_dsn) as c:
            assert c.execute("SELECT state FROM nima.refresh_policies").fetchone() == ("pending",)
        attempted.append(True)
        raise RuntimeError("private-sentinel")

    monkeypatch.setattr(control, "PrefectClient", unreachable)
    with pytest.raises(WorkflowError, match="^engine_unavailable$"):
        asyncio.run(control.change_schedule(policy_id, enabled=False))
    assert attempted == [True]
    with store.lease(policy_id) as session:
        session.state("paused")


def test_prepared_manifest_records_saved_request_format(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from nima.orchestration import pipeline

    migrate(pg_dsn)
    store = RequestStore(pg_dsn)
    request = uuid4()
    root = tmp_path / "raw"
    store.submit(request, QUERY, root)
    monkeypatch.setattr(workflows, "REQUEST_VERSION", "synthetic-next-format")
    monkeypatch.setattr(pipeline, "REQUEST_VERSION", "synthetic-next-format", raising=False)
    assert store.show(request)["format_version"] == "nima-kimdis-request-v1"
    pipeline.prepare_request(pg_dsn, request)
    manifest = next((root / "runs").glob("*/manifest.json"))
    assert json.loads(manifest.read_text())["request_version"] == "nima-kimdis-request-v1"
