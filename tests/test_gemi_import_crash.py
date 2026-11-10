"""SIGKILL at real PostgreSQL transaction boundaries, then verify offline replay."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.storage.gemi import import_run
from nima.storage.postgres import migrate
from tests.test_gemi_import import counts
from tests.test_gemi_import_archive import archive_run, snapshot
from tests.test_postgres_crash import wait_until

WORKER = """
import os, signal
from pathlib import Path
from uuid import UUID
from nima.storage.gemi import import_run
import_run(os.environ['NIMA_IMPORT_DSN'], Path(os.environ['NIMA_IMPORT_ARCHIVE']),
           UUID(os.environ['NIMA_IMPORT_RUN']))
Path(os.environ['NIMA_IMPORT_COMMITTED']).write_text('committed')
signal.pause()
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_killed_import_replays_without_partial_evidence(
    pg_dsn: str, tmp_path: Path, boundary: str
) -> None:
    migrate(pg_dsn)
    root, committed = tmp_path / "raw", tmp_path / "committed"
    run = archive_run(root, retry=True)
    original = snapshot(root)
    application = "nima_gemi_crash_" + uuid4().hex
    with psycopg.connect(pg_dsn, autocommit=True) as observer:
        if boundary == "before":
            observer.execute("SELECT pg_advisory_lock(812344020)")
            observer.execute("""CREATE FUNCTION nima.test_wait() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                PERFORM pg_advisory_xact_lock(812344020); RETURN NEW; END; $$;
                CREATE TRIGGER test_wait BEFORE INSERT ON nima.gemi_observations
                FOR EACH ROW WHEN (NEW.registry_number = '2')
                EXECUTE FUNCTION nima.test_wait();""")
        environment = {
            **os.environ,
            "NIMA_IMPORT_DSN": make_conninfo(pg_dsn, application_name=application),
            "NIMA_IMPORT_ARCHIVE": str(root),
            "NIMA_IMPORT_RUN": str(run),
            "NIMA_IMPORT_COMMITTED": str(committed),
        }
        with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
            try:
                if boundary == "before":
                    wait_until(
                        lambda: (
                            observer.execute(
                                "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s "
                                "AND wait_event='advisory'",
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
                    observer.execute("SELECT pg_advisory_unlock(812344020)")
                    wait_until(
                        lambda: (
                            observer.execute(
                                "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s",
                                (application,),
                            ).fetchone()
                            == (0,)
                        )
                    )
                    observer.execute("DROP TRIGGER test_wait ON nima.gemi_observations")
                assert counts(pg_dsn) == (
                    (0, 0, 0, 0, 0) if boundary == "before" else (1, 3, 1, 2, 0)
                )
                assert import_run(pg_dsn, root, run).reused == (boundary == "after")
                assert counts(pg_dsn) == (1, 3, 1, 2, 0)
                assert snapshot(root) == original
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
