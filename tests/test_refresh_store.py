"""Cycle intent and replay identity use real PostgreSQL and no provider calls."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.orchestration.refresh import Policy
from nima.storage.postgres import migrate
from nima.storage.refresh import RefreshStore
from nima.storage.workflows import RequestStore, WorkflowError

DAY = date(2026, 11, 12)


def new_policy(
    dsn: str, root: Path, *, start: date = DAY - timedelta(days=2)
) -> tuple[RefreshStore, UUID]:
    migrate(dsn)
    store, policy_id = RefreshStore(dsn), uuid4()
    store.create(policy_id, Policy(start, ("21",), root))
    return store, policy_id


def test_paused_create_and_concurrent_reuse_are_immutable(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    store, policy_id = RefreshStore(pg_dsn), uuid4()
    policy = Policy(DAY - timedelta(days=1), ("21",), tmp_path / "raw")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: store.create(policy_id, policy), range(2)))
    assert store.options(policy_id) == policy and not policy.root.exists()
    with store.lease(policy_id) as session, pytest.raises(WorkflowError, match="policy_paused"):
        session.cycle(DAY)
    with pytest.raises(WorkflowError, match="policy_conflict"):
        store.create(policy_id, Policy(policy.start, ("22",), policy.root))
    with (
        psycopg.connect(pg_dsn) as connection,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
    ):
        connection.execute("UPDATE nima.refresh_policies SET configuration='{}'")


def test_frozen_cycle_and_child_creation_recover_without_new_ids(
    pg_dsn: str, tmp_path: Path
) -> None:
    store, policy_id = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy_id) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
    with store.lease(policy_id) as session:
        assert session.cycle(DAY) == cycle
        first = session.children(cycle)
        assert session.children(cycle) == first and len(first) == 2
        with pytest.raises(WorkflowError, match="cycle_unresolved"):
            session.cycle(DAY + timedelta(days=1))
    assert len({child.request for child in first}) == 2
    assert all(RequestStore(pg_dsn).show(child.request)["status"] == "queued" for child in first)
    assert not (tmp_path / "raw").exists()
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.workflow_requests").fetchone() == (2,)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute("UPDATE nima.refresh_cycles SET query_dates=ARRAY[CURRENT_DATE]")


def test_bounded_catchup_and_per_policy_lease(pg_dsn: str, tmp_path: Path) -> None:
    store, policy_id = new_policy(pg_dsn, tmp_path / "raw", start=date(2000, 1, 1))
    plan = store.plan(policy_id, DAY)
    dates = plan["query_dates"]
    assert isinstance(dates, list) and len(dates) == 14
    assert dates[0] == "2000-01-01"
    with store.lease(policy_id) as session:
        with pytest.raises(WorkflowError, match="policy_busy"), store.lease(policy_id):
            pytest.fail("Another worker acquired the policy lock")
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        assert len(session.children(cycle)) == 14
        session.state("paused")
        with pytest.raises(WorkflowError, match="policy_paused"):
            session.cycle(DAY)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.refresh_events").fetchone() == (3,)


def test_populated_v5_upgrade_keeps_requests_and_both_sources(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from nima.ingestion.archive import Archive
    from nima.storage import postgres
    from nima.storage.gemi import import_run
    from tests.test_collection import QUERY, body
    from tests.test_gemi_import_archive import archive_run

    migrations = postgres._migrations()
    request = uuid4()
    with monkeypatch.context() as historical:
        historical.setattr(postgres, "_migrations", lambda: migrations[:5])
        migrate(pg_dsn)
        registry = tmp_path / "registry"
        import_run(pg_dsn, registry, archive_run(registry))
        pages = postgres.PageStore(pg_dsn, Archive(tmp_path / "kimdis"))
        run = uuid4()
        pages.start_run(run, QUERY)
        pages.commit_page(run, body(total=1), observed_at=datetime.now(UTC))
        RequestStore(pg_dsn).submit(request, QUERY, tmp_path / "workflow")
    migrate(pg_dsn)
    assert RequestStore(pg_dsn).show(request)["run_id"] is None
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.observations").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM nima.gemi_observations").fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM nima.refresh_policies").fetchone() == (0,)
