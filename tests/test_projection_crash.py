"""Kill a real projector at both sides of its SQL commit boundary."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.projections.worker import drain
from tests.test_participation import counts, seed
from tests.test_postgres_crash import wait_until

WORKER = """
import os, signal
from pathlib import Path
from nima.projections.worker import drain
drain(os.environ['NIMA_WORKER_DSN'])
Path(os.environ['NIMA_WORKER_COMMITTED']).write_text('committed')
signal.pause()
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_killed_projector_replays_atomically(pg_dsn: str, tmp_path: Path, boundary: str) -> None:
    seed(pg_dsn, tmp_path, "A")
    committed = tmp_path / "committed"
    application = f"nima_projection_crash_{uuid4().hex}"
    with psycopg.connect(pg_dsn, autocommit=True) as observer:
        if boundary == "before":
            observer.execute("SELECT pg_advisory_lock(812344003)")
            observer.execute("""CREATE FUNCTION nima.wait_projection() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                PERFORM pg_advisory_xact_lock(812344003); RETURN NEW; END; $$;
                CREATE TRIGGER wait_projection BEFORE UPDATE ON nima.outbox
                FOR EACH ROW EXECUTE FUNCTION nima.wait_projection();""")
        environment = {
            **os.environ,
            "NIMA_WORKER_DSN": make_conninfo(pg_dsn, application_name=application),
            "NIMA_WORKER_COMMITTED": str(committed),
        }
        with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
            try:
                if boundary == "before":
                    wait_until(
                        lambda: (
                            observer.execute(
                                """SELECT count(*) FROM pg_stat_activity
                        WHERE application_name=%s AND wait_event='advisory'""",
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
                    observer.execute("SELECT pg_advisory_unlock(812344003)")
                    wait_until(
                        lambda: (
                            observer.execute(
                                """SELECT count(*) FROM pg_stat_activity
                        WHERE application_name=%s""",
                                (application,),
                            ).fetchone()
                            == (0,)
                        )
                    )
                    observer.execute("DROP TRIGGER wait_projection ON nima.outbox")
                assert counts(pg_dsn) == ((0, 0, 0, 0) if boundary == "before" else (1, 3, 1, 1))
                assert drain(pg_dsn)["processed_events"] == (1 if boundary == "before" else 0)
                assert counts(pg_dsn) == (1, 3, 1, 1)
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
