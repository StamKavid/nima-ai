"""Kill a real SQL promoter before/after commit, then retry the exact selection."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.metadata.export import prepare_metadata
from nima.metadata.store import promote_metadata
from tests.test_analytics_snapshot import state
from tests.test_metadata_export import kimdis_run
from tests.test_postgres_crash import wait_until

WORKER = """
import os,signal
from pathlib import Path
from uuid import UUID
from nima.metadata.store import promote_metadata
promote_metadata(os.environ['NIMA_META_DSN'],'kimdis',UUID(os.environ['NIMA_META_RUN']),
                 Path(os.environ['NIMA_META_ROOT']),os.environ['NIMA_META_SHA'])
Path(os.environ['NIMA_META_DONE']).write_text('committed')
signal.pause()
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_sigkill_and_retry_preserve_one_complete_snapshot(
    boundary: str, pg_dsn: str, tmp_path: Path
) -> None:
    root, committed = tmp_path / "archive", tmp_path / "committed"
    run = kimdis_run(pg_dsn, root)
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    before = state(pg_dsn)
    application = "nima_metadata_crash_" + uuid4().hex
    with psycopg.connect(pg_dsn, autocommit=True) as observer:
        if boundary == "before":
            observer.execute("SELECT pg_advisory_lock(812344092)")
            observer.execute("""CREATE FUNCTION nima_processing.test_metadata_wait() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock(812344092);
                RETURN NULL; END; $$;
                CREATE TRIGGER test_metadata_wait AFTER INSERT ON nima_processing.metadata_snapshots
                FOR EACH STATEMENT EXECUTE FUNCTION nima_processing.test_metadata_wait();""")
        env = {
            **os.environ,
            "NIMA_META_DSN": make_conninfo(pg_dsn, application_name=application),
            "NIMA_META_RUN": str(run),
            "NIMA_META_ROOT": str(root),
            "NIMA_META_SHA": selected.artifact_sha256,
            "NIMA_META_DONE": str(committed),
        }
        with subprocess.Popen([sys.executable, "-c", WORKER], env=env) as worker:
            try:
                if boundary == "before":
                    wait_until(
                        lambda: (
                            observer.execute(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE application_name=%s AND wait_event=%s",
                                (application, "advisory"),
                            ).fetchone()
                            == (1,)
                        )
                    )
                else:
                    wait_until(committed.exists)
                worker.kill()
                worker.wait(timeout=5)
                if boundary == "before":
                    observer.execute("SELECT pg_advisory_unlock(812344092)")
                    wait_until(
                        lambda: (
                            observer.execute(
                                "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s",
                                (application,),
                            ).fetchone()
                            == (0,)
                        )
                    )
                    observer.execute(
                        "DROP TRIGGER test_metadata_wait ON nima_processing.metadata_snapshots"
                    )
                assert observer.execute(
                    "SELECT count(*) FROM nima_processing.metadata_snapshots"
                ).fetchone() == (0 if boundary == "before" else 1,)
                result = promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)
                assert result.reused == (boundary == "after")
                assert observer.execute(
                    "SELECT count(*) FROM nima_processing.reported_market_metadata"
                ).fetchone() == (4,)
                assert state(pg_dsn) == before
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
