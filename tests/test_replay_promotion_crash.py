"""Kill a real promoter at SQL commit boundaries, then retry the selected replay."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.dataops.promotion import promote_run
from nima.storage.postgres import NORMALIZER_VERSION
from tests.test_analytics_snapshot import state
from tests.test_postgres_crash import wait_until
from tests.test_replay_promotion import selection

WORKER = """
import os,signal
from pathlib import Path
from uuid import UUID
from nima.dataops.promotion import promote_run
from nima.storage.postgres import NORMALIZER_VERSION
promote_run(os.environ['NIMA_PROMO_DSN'],UUID(os.environ['NIMA_PROMO_RUN']),
            Path(os.environ['NIMA_PROMO_ARCHIVE']),NORMALIZER_VERSION,
            os.environ['NIMA_PROMO_SHA'])
Path(os.environ['NIMA_PROMO_COMMITTED']).write_text('committed')
signal.pause()
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_sigkill_preserves_atomic_batch_and_retry(
    boundary: str, pg_dsn: str, tmp_path: Path
) -> None:
    root, committed = tmp_path / "archive", tmp_path / "committed"
    run, digest = selection(pg_dsn, root)
    before = state(pg_dsn)
    application = "nima_promotion_crash_" + uuid4().hex
    with psycopg.connect(pg_dsn, autocommit=True) as observer:
        if boundary == "before":
            observer.execute("SELECT pg_advisory_lock(812344091)")
            observer.execute("""CREATE FUNCTION nima_processing.test_wait() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                PERFORM pg_advisory_xact_lock(812344091); RETURN NULL; END; $$;
                CREATE TRIGGER test_wait AFTER INSERT ON nima_processing.replay_results
                FOR EACH STATEMENT EXECUTE FUNCTION nima_processing.test_wait();""")
        environment = {
            **os.environ,
            "NIMA_PROMO_DSN": make_conninfo(pg_dsn, application_name=application),
            "NIMA_PROMO_RUN": str(run),
            "NIMA_PROMO_ARCHIVE": str(root),
            "NIMA_PROMO_SHA": digest,
            "NIMA_PROMO_COMMITTED": str(committed),
        }
        with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
            try:
                if boundary == "before":
                    wait_until(
                        lambda: (
                            observer.execute(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE application_name=%s AND wait_event='advisory'",
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
                    observer.execute("SELECT pg_advisory_unlock(812344091)")
                    wait_until(
                        lambda: (
                            observer.execute(
                                "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s",
                                (application,),
                            ).fetchone()
                            == (0,)
                        )
                    )
                    observer.execute("DROP TRIGGER test_wait ON nima_processing.replay_results")
                expected = 0 if boundary == "before" else 1
                assert observer.execute(
                    "SELECT count(*) FROM nima_processing.replay_batches"
                ).fetchone() == (expected,)
                assert observer.execute(
                    "SELECT count(*) FROM nima_processing.replay_results"
                ).fetchone() == (expected,)
                assert promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest).replayed == (
                    boundary == "after"
                )
                assert observer.execute(
                    "SELECT count(*) FROM nima_processing.replay_batches"
                ).fetchone() == (1,)
                assert observer.execute(
                    "SELECT count(*) FROM nima_processing.replay_results"
                ).fetchone() == (1,)
                assert state(pg_dsn) == before
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
