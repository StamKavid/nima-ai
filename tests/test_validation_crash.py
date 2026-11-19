"""Actual process death leaves a resumable intent or a reusable committed outcome."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.analytics.export import export_readout
from nima.contracts.history import HistoryError
from nima.dataops.validation import validate_readout
from nima.storage.validations import show_validation
from tests.test_analytics_reconcile import seed_cohort
from tests.test_analytics_snapshot import reader, state
from tests.test_market_analytics import request_file
from tests.test_postgres_crash import wait_until
from tests.test_validation_store import journal_role

WORKER = """
import os,signal,httpx
from pathlib import Path
from nima.__main__ import main
from nima.storage.validations import JournalSession
def forbidden(*args,**kwargs): raise AssertionError('Unexpected HTTP')
httpx.Client.request=forbidden
original=JournalSession.finish
def finish(self,result):
    if os.environ['NIMA_TEST_BOUNDARY']=='after': original(self,result)
    Path(os.environ['NIMA_TEST_READY']).write_text('ready')
    signal.pause()
JournalSession.finish=finish
raise SystemExit(main(['dataops','validate-readout','--attempt-id',os.environ['NIMA_TEST_ATTEMPT'],
    '--request',os.environ['NIMA_TEST_REQUEST'],'--report',os.environ['NIMA_TEST_REPORT']]))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
@pytest.mark.parametrize("stop", ["kill", "interrupt"])
def test_commit_crash_and_concurrent_retry_preserve_originals(
    pg_dsn: str, tmp_path: Path, boundary: str, stop: str
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "raw")
    selection = request_file(request, tmp_path / "request.json")
    attempt, ready = uuid4(), tmp_path / "ready"
    application = "nima_validation_test_" + uuid4().hex
    with reader(pg_dsn) as (source, _), journal_role(pg_dsn) as journal:
        summary = export_readout(source, selection, tmp_path / "reports")
        report = tmp_path / "reports" / (summary.artifact_sha256 + ".json")
        preserved, before = (report.read_bytes(), report.stat().st_mtime_ns), state(pg_dsn)
        environment = {
            **os.environ,
            "NIMA_DATABASE_URL": source,
            "NIMA_VALIDATION_DATABASE_URL": make_conninfo(journal, application_name=application),
            "NIMA_TEST_BOUNDARY": boundary,
            "NIMA_TEST_READY": str(ready),
            "NIMA_TEST_ATTEMPT": str(attempt),
            "NIMA_TEST_REQUEST": str(selection),
            "NIMA_TEST_REPORT": str(report),
        }
        with subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as worker:
            try:
                wait_until(lambda: ready.exists() or worker.poll() is not None)
                assert ready.exists(), "Validation did not reach its commit boundary"
                current = show_validation(journal, attempt)
                assert current["status"] == ("passed" if boundary == "after" else "pending")
                with pytest.raises(HistoryError, match="^validation_busy$"):
                    validate_readout(source, journal, attempt, selection, report)
                if stop == "kill":
                    worker.kill()
                else:
                    worker.send_signal(signal.SIGINT)
                stdout, stderr = worker.communicate(timeout=10)
                assert worker.returncode == (-9 if stop == "kill" else 130)
                if stop == "interrupt":
                    assert json.loads(stdout)["failure"] == "validation_interrupted"
                assert str(tmp_path) not in stderr.decode()
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
        with psycopg.connect(pg_dsn, autocommit=True) as observer:
            wait_until(
                lambda: (
                    observer.execute(
                        "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s",
                        (application,),
                    ).fetchone()
                    == (0,)
                )
            )
        result = validate_readout(source, journal, attempt, selection, report)
        assert result["status"] == "passed" and result["reused"] == (boundary == "after")
        assert (report.read_bytes(), report.stat().st_mtime_ns) == preserved
        assert state(pg_dsn) == before
