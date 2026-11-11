"""Engine-independent workflow stages reuse real archive and PostgreSQL boundaries."""

from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from nima.orchestration.pipeline import (
    collect_request,
    finalize_request,
    prepare_request,
    project_request,
)
from nima.storage.postgres import migrate
from nima.storage.workflows import RequestStore, WorkflowError
from tests.test_collection import QUERY, Clock, body
from tests.test_page_store import store as page_store


def test_stable_run_and_run_scoped_projection(pg_dsn: str, tmp_path: Path) -> None:
    other = page_store(pg_dsn, tmp_path / "other")
    from datetime import UTC, datetime

    unrelated = uuid4()
    other.start_run(unrelated, QUERY)
    other.commit_page(unrelated, body(total=1, title="unrelated"), observed_at=datetime.now(UTC))
    requests = RequestStore(pg_dsn)
    request = uuid4()
    requests.submit(request, QUERY, tmp_path / "raw")
    first = prepare_request(pg_dsn, request)
    assert prepare_request(pg_dsn, request) == first
    calls = []

    def handle(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, content=body(total=1))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert collect_request(pg_dsn, request, client=client, clock=Clock())["collection_complete"]
        assert collect_request(pg_dsn, request, client=client, clock=Clock())["collection_complete"]
    assert len(calls) == 1 and requests.show(request)["attempts"] == 1
    assert project_request(pg_dsn, request)["remaining_events"] == 0
    assert finalize_request(pg_dsn, request)["status"] == "complete"
    with psycopg.connect(pg_dsn) as connection:
        connection.execute(
            "UPDATE nima.workflow_requests SET projection_batches=100 WHERE request_id=%s",
            (request,),
        )
    assert project_request(pg_dsn, request)["remaining_events"] == 0
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.projection_receipts").fetchone() == (
            1,
        )
        assert connection.execute(
            "SELECT count(*) FROM nima.outbox WHERE delivered_at IS NULL"
        ).fetchone() == (1,)
    assert requests.show(request)["run_id"] == str(UUID(str(first["run_id"])))


def test_request_budget_blocks_source_before_http(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    requests = RequestStore(pg_dsn)
    request = uuid4()
    requests.submit(request, QUERY, tmp_path / "raw")
    prepare_request(pg_dsn, request)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute(
            "UPDATE nima.workflow_requests SET attempts=300 WHERE request_id=%s", (request,)
        )
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected provider call"))
        ) as client,
        pytest.raises(WorkflowError, match="workflow_attempt_limit"),
    ):
        collect_request(pg_dsn, request, client=client, clock=Clock())
    assert requests.show(request)["status"] == "deferred"
    with pytest.raises(WorkflowError):
        finalize_request(pg_dsn, request)


def test_resume_verification_also_reserves_persistent_attempts(pg_dsn: str, tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from nima.ingestion.archive import Archive
    from nima.ingestion.config import Limits
    from nima.storage.runs import RunStore

    migrate(pg_dsn)
    request = uuid4()
    root = tmp_path / "raw"
    requests = RequestStore(pg_dsn)
    requests.submit(request, QUERY, root)
    run = UUID(str(prepare_request(pg_dsn, request)["run_id"]))
    writer = RunStore(pg_dsn, Archive(root), run, Limits())
    with writer.lease():
        writer.takeover(QUERY)
        writer.commit_page(run, body(), observed_at=datetime.now(UTC), owner=writer.owner)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute(
            "UPDATE nima.workflow_requests SET attempts=299 WHERE request_id=%s", (request,)
        )
    calls: list[int] = []

    def handle(req: httpx.Request) -> httpx.Response:
        page = int(req.url.params["page"])
        calls.append(page)
        return httpx.Response(200, content=body(page=page))

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(WorkflowError, match="workflow_attempt_limit"),
    ):
        collect_request(pg_dsn, request, client=client, clock=Clock())
    assert calls == [0]  # Verification consumes the last reservation; page 1 cannot be fetched.
    assert requests.show(request)["attempts"] == 300
