"""SIGKILL a real worker before/after SQL commit, then replay archived evidence."""

import hashlib
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from tests.test_collection import QUERY
from tests.test_page_store import counts, store

WORKER = """
import os, signal
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID
from nima.ingestion.archive import Archive
from nima.storage.postgres import PageStore
from tests.test_collection import body
store = PageStore(os.environ['NIMA_WORKER_DSN'],
                  Archive(Path(os.environ['NIMA_WORKER_ARCHIVE'])))
store.commit_page(UUID(os.environ['NIMA_WORKER_RUN']), body(total=1),
                  observed_at=datetime.now(UTC))
Path(os.environ['NIMA_WORKER_COMMITTED']).write_text('committed')
signal.pause()
"""


def wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 8
    while not condition():
        if time.monotonic() >= deadline:
            pytest.fail("Worker did not reach the expected database boundary within 8 seconds")
        time.sleep(0.02)


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_killed_worker_replay_is_atomic(pg_dsn: str, tmp_path: Path, boundary: str) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    committed = tmp_path / "committed"
    application = f"nima_crash_{uuid4().hex}"
    with psycopg.connect(pg_dsn, autocommit=True) as observer:
        if boundary == "before":
            # Hold the worker at its final UPDATE, after inserting records/outbox
            # but before COMMIT. These SQL hooks exist only in this disposable DB.
            observer.execute("SELECT pg_advisory_lock(812344002)")
            observer.execute("""CREATE FUNCTION nima.test_wait() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                PERFORM pg_advisory_xact_lock(812344002); RETURN NEW; END; $$;
                CREATE TRIGGER test_wait BEFORE UPDATE ON nima.ingest_runs
                FOR EACH ROW EXECUTE FUNCTION nima.test_wait();""")
        environment = {
            **os.environ,
            "NIMA_WORKER_DSN": make_conninfo(pg_dsn, application_name=application),
            "NIMA_WORKER_ARCHIVE": str(database.archive.root),
            "NIMA_WORKER_RUN": str(run),
            "NIMA_WORKER_COMMITTED": str(committed),
        }
        with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
            try:
                if boundary == "before":
                    wait_until(
                        lambda: (
                            observer.execute(
                                """SELECT count(*) FROM pg_stat_activity
                        WHERE application_name = %s AND wait_event = 'advisory'""",
                                (application,),
                            ).fetchone()
                            == (1,)
                        )
                    )
                else:
                    wait_until(committed.exists)
                worker.kill()
                worker.wait(timeout=5)
                if boundary == "before":
                    observer.execute("SELECT pg_advisory_unlock(812344002)")
                    wait_until(
                        lambda: (
                            observer.execute(
                                """SELECT count(*) FROM pg_stat_activity
                        WHERE application_name = %s""",
                                (application,),
                            ).fetchone()
                            == (0,)
                        )
                    )
                    observer.execute("DROP TRIGGER test_wait ON nima.ingest_runs")
                expected = (0, 0, 0, 0) if boundary == "before" else (1, 1, 1, 1)
                assert counts(pg_dsn) == expected
                blobs = list(database.archive.root.glob("objects/*/*.body"))
                assert len(blobs) == 1
                archived = blobs[0].read_bytes()
                assert blobs[0].stem == hashlib.sha256(archived).hexdigest()
                assert database.commit_page(run, archived, observed_at=datetime.now(UTC)) == (
                    boundary == "before"
                )
                assert counts(pg_dsn) == (1, 1, 1, 1)
                assert observer.execute("SELECT next_page FROM nima.ingest_runs").fetchone() == (1,)
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
