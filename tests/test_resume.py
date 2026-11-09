"""Resume uses saved evidence, a worker lease, and source-prefix validation."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.ingestion.archive import Archive
from nima.ingestion.collector import RunError
from nima.ingestion.config import Limits
from nima.ingestion.resume import resume
from nima.storage.postgres import CheckpointError, migrate
from nima.storage.runs import RunBusy, RunStore, inspect_run
from tests.test_collection import QUERY, Clock, body
from tests.test_page_store import counts


def test_active_worker_is_excluded(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    run = uuid4()
    first = RunStore(pg_dsn, Archive(tmp_path / "raw"), run, Limits())
    second = RunStore(pg_dsn, first.archive, run, Limits())
    with first.lease():
        first.begin(QUERY)
        with pytest.raises(RunBusy), second.lease():
            pytest.fail("Second writer acquired an active run")


def test_committed_prefix_is_verified_and_continuation_is_idempotent(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    archive = Archive(tmp_path / "raw")
    run = uuid4()
    writer = RunStore(pg_dsn, archive, run, Limits())
    with writer.lease():
        writer.begin(QUERY)
        writer.commit_page(run, body(), observed_at=datetime.now(UTC), owner=writer.owner)
    requests: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requests.append(page)
        return httpx.Response(200, content=body(page=page))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = resume(pg_dsn, run, client=client, clock=Clock())
        assert result.status == "complete" and requests == [0, 1]
        repeated = resume(pg_dsn, run, client=client, clock=Clock())
    assert repeated.status == "complete" and requests == [0, 1]
    assert counts(pg_dsn) == (2, 2, 2, 2)


def test_drift_blocks_continuation_and_preserves_checkpoint(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    run = uuid4()
    writer = RunStore(pg_dsn, Archive(tmp_path / "raw"), run, Limits())
    with writer.lease():
        writer.begin(QUERY)
        writer.commit_page(run, body(), observed_at=datetime.now(UTC), owner=writer.owner)
    requests: list[int] = []

    def changed(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params["page"])
        requests.append(number)
        return httpx.Response(
            200, content=body(page=number, title="Changed source" if number == 0 else "Synthetic")
        )

    with httpx.Client(transport=httpx.MockTransport(changed)) as client:
        result = resume(pg_dsn, run, client=client, clock=Clock())
    assert requests == [0]
    assert result.failure == "source_changed" and not result.collection_complete
    assert inspect_run(pg_dsn, run)["next_page"] == 1
    assert counts(pg_dsn) == (1, 1, 1, 1)


@pytest.mark.parametrize("changed", [False, True])
def test_pending_response_keeps_original_bytes_and_time(
    pg_dsn: str, tmp_path: Path, changed: bool
) -> None:
    migrate(pg_dsn)
    run = uuid4()
    writer = RunStore(pg_dsn, Archive(tmp_path / "raw"), run, Limits())
    observed = datetime(2026, 11, 6, tzinfo=UTC)
    raw = body()
    digest = writer.archive.store(raw)
    receipt: dict[str, object] = {
        "page": 0,
        "attempt": 1,
        "observed_at": observed.isoformat(),
        "body_complete": False,
    }
    with writer.lease():
        writer.begin(QUERY)
        writer.started(receipt)
        receipt.update(body_complete=True, sha256=digest, bytes=len(raw), status=200)
        writer.finished(receipt)

    def handle(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        source = json.loads(body(page=page))
        if changed:
            source["content"][0]["title"] = "Changed pending source"
        return httpx.Response(200, content=json.dumps(source, indent=2).encode())

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = resume(pg_dsn, run, client=client, clock=Clock())
    if changed:
        assert result.failure == "source_changed" and result.attempts == 2
        assert counts(pg_dsn) == (0, 0, 0, 0)
        return
    assert result.status == "complete" and result.attempts == 3
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT raw_sha256, observed_at FROM nima.run_pages WHERE page_number = 0"
        ).fetchone() == (digest, observed)
    assert counts(pg_dsn) == (2, 2, 2, 2)


@pytest.mark.parametrize("missing", [False, True])
def test_bad_archive_blocks_network_before_resume(
    pg_dsn: str, tmp_path: Path, missing: bool
) -> None:
    migrate(pg_dsn)
    run = uuid4()
    writer = RunStore(pg_dsn, Archive(tmp_path / "raw"), run, Limits())
    raw = body()
    digest = writer.archive.store(raw)
    with writer.lease():
        writer.begin(QUERY)
        writer.commit_page(run, raw, observed_at=datetime.now(UTC), owner=writer.owner)
    blob = writer.archive.root / "objects" / digest[:2] / f"{digest}.body"
    if missing:
        blob.unlink()
    else:
        blob.write_bytes(b"corrupt")

    def no_http(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid archive allowed source access")

    with httpx.Client(transport=httpx.MockTransport(no_http)) as client, pytest.raises(RunError):
        resume(pg_dsn, run, client=client, clock=Clock())
    assert inspect_run(pg_dsn, run)["next_page"] == 1


def test_lost_lease_cannot_bypass_new_writer_token(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    run = uuid4()
    application = f"nima_test_lease_{uuid4().hex}"
    scoped = make_conninfo(pg_dsn, application_name=application)
    old = RunStore(scoped, Archive(tmp_path / "raw"), run, Limits())
    new = RunStore(pg_dsn, old.archive, run, Limits())
    with old.lease():
        old.begin(QUERY)
        with psycopg.connect(pg_dsn, autocommit=True) as observer:
            observer.execute(
                "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity "
                "WHERE datname = current_database() AND application_name = %s",
                (application,),
            )
        with new.lease():
            new.takeover(QUERY)
            with pytest.raises((CheckpointError, psycopg.Error)):
                old.takeover(QUERY)
            with pytest.raises(CheckpointError):
                old.commit_page(run, body(), observed_at=datetime.now(UTC), owner=old.owner)
            with pytest.raises(CheckpointError):
                old.started(
                    {
                        "page": 0,
                        "attempt": 1,
                        "observed_at": datetime.now(UTC).isoformat(),
                        "body_complete": False,
                    }
                )


@pytest.mark.parametrize("bad", ["integer", "number", "version"])
def test_incompatible_saved_options_do_not_reach_source(
    pg_dsn: str, tmp_path: Path, bad: str
) -> None:
    migrate(pg_dsn)
    run = uuid4()
    writer = RunStore(pg_dsn, Archive(tmp_path / "raw"), run, Limits())
    with writer.lease():
        writer.begin(QUERY)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        if bad == "version":
            connection.execute("UPDATE nima.ingest_runs SET normalizer_version = 'unsupported'")
        else:
            key, value = ("max_pages", '"bad"') if bad == "integer" else ("run_timeout", "true")
            connection.execute(
                "UPDATE nima.ingest_runs SET settings = jsonb_set(settings, %s, %s::jsonb)",
                ([key], value),
            )

    def no_http(_: httpx.Request) -> httpx.Response:
        pytest.fail("Incompatible saved options reached source")

    with (
        httpx.Client(transport=httpx.MockTransport(no_http)) as client,
        pytest.raises((CheckpointError, RunError)),
    ):
        resume(pg_dsn, run, client=client, clock=Clock())


def test_missing_archive_root_is_not_silently_recreated(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    run = uuid4()
    writer = RunStore(pg_dsn, Archive(tmp_path / "raw"), run, Limits())
    with writer.lease():
        writer.begin(QUERY)
    shutil.rmtree(writer.archive.root)

    def no_http(_: httpx.Request) -> httpx.Response:
        pytest.fail("Missing original archive allowed source access")

    with httpx.Client(transport=httpx.MockTransport(no_http)) as client, pytest.raises(RunError):
        resume(pg_dsn, run, client=client, clock=Clock())
    assert not writer.archive.root.exists()
