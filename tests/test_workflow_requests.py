"""Request identity and budgets are enforced by real PostgreSQL, independently of SDKs."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Query
from nima.ingestion.transport import CollectionStopped
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from nima.storage.workflows import RequestStore, WorkflowError
from tests.test_collection import QUERY


def store(dsn: str) -> RequestStore:
    migrate(dsn)
    return RequestStore(dsn)


def test_concurrent_submission_has_one_identity_and_no_archive_creation(
    pg_dsn: str, tmp_path: Path
) -> None:
    requests = store(pg_dsn)
    request, root = uuid4(), tmp_path / "raw"
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lambda _: requests.submit(request, QUERY, root), range(2)))
    status = requests.show(request)
    assert status["status"] == "queued" and status["run_id"] is None
    assert status["attempts"] == status["executions"] == 0
    assert not root.exists()
    with pytest.raises(WorkflowError, match="request_conflict"):
        requests.submit(request, QUERY, tmp_path / "other")
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.workflow_requests").fetchone() == (1,)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute("UPDATE nima.workflow_requests SET parameters='{}'")


def test_dispatch_unknown_and_acknowledged_are_not_collection_success(
    pg_dsn: str, tmp_path: Path
) -> None:
    requests = store(pg_dsn)
    request = uuid4()
    requests.submit(request, QUERY, tmp_path / "raw")
    unknown = requests.begin_dispatch(request)
    requests.finish_dispatch(unknown, None)
    accepted = requests.begin_dispatch(request)
    engine = uuid4()
    requests.finish_dispatch(accepted, engine)
    result = requests.show(request)
    assert result["dispatches"] == 2 and result["unknown_dispatches"] == 1
    assert result["status"] == "queued" and result["engine_run_id"] == str(engine)
    assert result["collection_complete"] is False


def test_source_lease_and_persistent_budgets(pg_dsn: str, tmp_path: Path) -> None:
    requests = store(pg_dsn)
    request, other = uuid4(), uuid4()
    for value in (request, other):
        requests.submit(value, QUERY, tmp_path / "raw")
    with requests.source_lease(request) as guard:
        guard.start_execution()
        with pytest.raises(WorkflowError, match="source_busy"), requests.source_lease(other):
            pytest.fail("Source lease must exclude another workflow")
        with psycopg.connect(pg_dsn) as connection:
            connection.execute(
                "UPDATE nima.workflow_requests SET attempts=299 WHERE request_id=%s", (request,)
            )
        guard.reserve_attempt()
        with pytest.raises(CollectionStopped, match="workflow_attempt_limit"):
            guard.reserve_attempt()
    for _ in range(3):
        with requests.source_lease(request) as guard:
            guard.start_execution()
    with (
        requests.source_lease(request) as guard,
        pytest.raises(WorkflowError, match="workflow_execution_limit"),
    ):
        guard.start_execution()
    assert requests.show(request)["executions"] == 4
    assert requests.show(request)["attempts"] == 300


def test_expired_request_and_unknown_identity_fail_closed(pg_dsn: str, tmp_path: Path) -> None:
    requests = store(pg_dsn)
    with pytest.raises(WorkflowError, match="request_unavailable"):
        requests.show(UUID(int=1))
    request = uuid4()
    requests.submit(request, QUERY, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as connection:
        connection.execute(
            "UPDATE nima.workflow_requests SET started_at=clock_timestamp()-interval '31 minutes' "
            "WHERE request_id=%s",
            (request,),
        )
    with (
        requests.source_lease(request) as guard,
        pytest.raises(WorkflowError, match="workflow_deadline"),
    ):
        guard.start_execution()


def test_options_and_one_time_binding_survive_replay(pg_dsn: str, tmp_path: Path) -> None:
    requests = store(pg_dsn)
    request, run, different = uuid4(), uuid4(), uuid4()
    root = tmp_path / "raw"
    requests.submit(request, QUERY, root)
    assert requests.options(request) == (QUERY, Limits(), root)
    archive = Archive(root)
    for number in (run, different):
        writer = RunStore(pg_dsn, archive, number, Limits())
        with writer.lease():
            writer.begin(QUERY)
    requests.bind(request, run)
    requests.bind(request, run)
    with pytest.raises(WorkflowError, match="request_conflict"):
        requests.bind(request, different)
    assert requests.show(request)["run_id"] == str(run)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("UPDATE nima.ingest_runs SET status='complete' WHERE run_id=%s", (run,))
    assert requests.show(request)["collection_complete"] is False
    with pytest.raises(WorkflowError, match="request_conflict"):
        requests.submit(request, Query(date(2026, 11, 1), date(2026, 11, 1)), root)


def test_reservation_requires_execution_and_lost_owner_is_fenced(
    pg_dsn: str, tmp_path: Path
) -> None:
    requests = store(pg_dsn)
    request = uuid4()
    requests.submit(request, QUERY, tmp_path / "raw")
    with requests.source_lease(request) as guard:
        with pytest.raises(CollectionStopped, match="workflow_not_started"):
            guard.reserve_attempt()
        guard.start_execution()
        with psycopg.connect(pg_dsn) as connection:
            connection.execute(
                "UPDATE nima.workflow_requests SET source_owner=NULL WHERE request_id=%s",
                (request,),
            )
        with pytest.raises(CollectionStopped, match="workflow_fenced"):
            guard.reserve_attempt()
    assert requests.show(request)["attempts"] == 0


def test_populated_v4_upgrade_preserves_both_source_histories(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from nima.storage import postgres
    from nima.storage.gemi import import_run
    from tests.test_collection import body
    from tests.test_gemi_import_archive import archive_run

    migrations = postgres._migrations()
    with monkeypatch.context() as historical:
        historical.setattr(postgres, "_migrations", lambda: migrations[:4])
        migrate(pg_dsn)
        registry = tmp_path / "registry"
        import_run(pg_dsn, registry, archive_run(registry))
        pages = postgres.PageStore(pg_dsn, Archive(tmp_path / "kimdis"))
        run = uuid4()
        pages.start_run(run, QUERY)
        pages.commit_page(run, body(total=1), observed_at=datetime.now(UTC))
    with psycopg.connect(pg_dsn) as connection:
        before = connection.execute(
            "SELECT (SELECT jsonb_agg(to_jsonb(o)) FROM nima.observations o), "
            "(SELECT jsonb_agg(to_jsonb(g)) FROM nima.gemi_observations g)"
        ).fetchone()
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        assert (
            connection.execute(
                "SELECT (SELECT jsonb_agg(to_jsonb(o)) FROM nima.observations o), "
                "(SELECT jsonb_agg(to_jsonb(g)) FROM nima.gemi_observations g)"
            ).fetchone()
            == before
        )
        assert connection.execute("SELECT count(*) FROM nima.workflow_requests").fetchone() == (0,)
    RequestStore(pg_dsn).submit(uuid4(), QUERY, tmp_path / "new")
