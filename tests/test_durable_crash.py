"""A real killed collector leaves inspectable checkpoints and uncertain attempts."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import httpx
import psycopg
import pytest

from nima.ingestion.collector import RunError
from nima.ingestion.resume import resume
from nima.storage.postgres import migrate
from nima.storage.runs import inspect_run
from tests.test_collection import Clock, body
from tests.test_postgres_crash import wait_until

WORKER = """
import os, signal
from pathlib import Path
import httpx
from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from tests.test_collection import QUERY, Clock, body
def handle(request):
    page = int(request.url.params['page'])
    if page == int(os.environ['NIMA_BLOCKED_PAGE']):
        Path(os.environ['NIMA_READY']).write_text('request entered')
        signal.pause()
    return httpx.Response(200, content=body(page=page))
with httpx.Client(transport=httpx.MockTransport(handle)) as client:
    collect(QUERY, Limits(), Archive(Path(os.environ['NIMA_ARCHIVE'])),
            client=client, clock=Clock(), database_dsn=os.environ['NIMA_DATABASE_URL'])
"""


@pytest.mark.parametrize("blocked_page", [0, 1])
def test_killed_http_worker_remains_inspectable(
    pg_dsn: str, tmp_path: Path, blocked_page: int
) -> None:
    migrate(pg_dsn)
    ready = tmp_path / "ready"
    archive = tmp_path / "raw"
    environment = {
        **os.environ,
        "NIMA_DATABASE_URL": pg_dsn,
        "NIMA_ARCHIVE": str(archive),
        "NIMA_READY": str(ready),
        "NIMA_BLOCKED_PAGE": str(blocked_page),
    }
    with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
        try:
            wait_until(ready.exists)
            with psycopg.connect(pg_dsn) as observer:
                active = observer.execute("SELECT run_id FROM nima.ingest_runs").fetchone()
                assert active is not None

            def no_http(_: httpx.Request) -> httpx.Response:
                pytest.fail("Active worker allowed competing source access")

            with (
                httpx.Client(transport=httpx.MockTransport(no_http)) as client,
                pytest.raises(RunError) as busy,
            ):
                resume(pg_dsn, active[0], client=client, clock=Clock())
            assert busy.value.reason == "run_busy"
            worker.kill()
            assert worker.wait(timeout=5) == -signal.SIGKILL
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
    with psycopg.connect(pg_dsn) as connection:
        row = connection.execute("SELECT run_id FROM nima.ingest_runs").fetchone()
        assert row is not None
        run_id = row[0]
    # The filesystem projection is not the source of durable inspection counts.
    manifest = next(archive.glob("runs/*/manifest.json"))
    manifest.write_text(json.dumps({"summary": {"status": "complete", "pages": 999}}))
    state = inspect_run(pg_dsn, run_id)
    assert state["status"] == "running" and state["worker_liveness"] == "unknown"
    assert state["pages"] == state["records"] == state["next_page"] == blocked_page
    assert state["attempts"] == blocked_page + 1 and state["pending_attempts"] == 1
    assert state["collection_complete"] is False and state["normalization_complete"] is False
    with psycopg.connect(pg_dsn, autocommit=True) as observer:
        wait_until(
            lambda: (
                observer.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                ).fetchone()
                == (0,)
            )
        )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body(page=int(request.url.params["page"])))
        )
    ) as client:
        recovered = resume(pg_dsn, run_id, client=client, clock=Clock())
    assert recovered.status == "complete" and recovered.records == 2
    state = inspect_run(pg_dsn, run_id)
    assert state["pending_attempts"] == 1 and state["active_pending_attempts"] == 0
    with psycopg.connect(pg_dsn) as observer:
        assert observer.execute("SELECT count(*) FROM nima.observations").fetchone() == (2,)
        assert observer.execute("SELECT count(*) FROM nima.outbox").fetchone() == (2,)


def test_kill_before_checkpoint_replays_saved_http_response(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    environment = {
        **os.environ,
        "NIMA_DATABASE_URL": pg_dsn,
        "NIMA_ARCHIVE": str(tmp_path / "raw"),
        "NIMA_READY": str(tmp_path / "unused"),
        "NIMA_BLOCKED_PAGE": "99",
    }
    with psycopg.connect(pg_dsn, autocommit=True) as observer:
        observer.execute("SELECT pg_advisory_lock(812344099)")
        observer.execute("""CREATE FUNCTION nima.test_checkpoint_wait() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            PERFORM pg_advisory_xact_lock(812344099); RETURN NEW; END; $$;
            CREATE TRIGGER test_checkpoint_wait BEFORE UPDATE ON nima.ingest_runs
            FOR EACH ROW EXECUTE FUNCTION nima.test_checkpoint_wait();""")
        with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
            try:
                wait_until(
                    lambda: (
                        observer.execute(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() AND wait_event = 'advisory'"
                        ).fetchone()
                        == (1,)
                    )
                )
                receipt = observer.execute(
                    "SELECT run_id, raw_sha256, started_at "
                    "FROM nima.http_attempts WHERE page_number = 0 AND state = 'finished'"
                ).fetchone()
                assert receipt is not None
                worker.kill()
                worker.wait(timeout=5)
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
                observer.execute("SELECT pg_advisory_unlock(812344099)")
        wait_until(
            lambda: (
                observer.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                ).fetchone()
                == (0,)
            )
        )
        assert observer.execute("SELECT count(*) FROM nima.run_pages").fetchone() == (0,)
        observer.execute("DROP TRIGGER test_checkpoint_wait ON nima.ingest_runs")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body(page=int(request.url.params["page"])))
        )
    ) as client:
        recovered = resume(pg_dsn, receipt[0], client=client, clock=Clock())
    assert recovered.status == "complete" and recovered.attempts == 3
    with psycopg.connect(pg_dsn) as observer:
        assert (
            observer.execute(
                "SELECT raw_sha256, observed_at FROM nima.run_pages WHERE page_number = 0"
            ).fetchone()
            == receipt[1:]
        )
        assert observer.execute("SELECT count(*) FROM nima.observations").fetchone() == (2,)
        assert observer.execute("SELECT count(*) FROM nima.outbox").fetchone() == (2,)
