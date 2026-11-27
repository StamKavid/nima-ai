"""Actual SIGKILL/SIGINT on both sides of the single terminal transaction."""

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

from nima.analytics.citation_readout import prepare_citation_readout
from nima.contracts.acceptance_history import HistoryError
from nima.dataops.citation_acceptance_history import record_citation_acceptance
from nima.storage.acceptance_history import show_acceptance
from tests.test_acceptance_history_store import journal_role
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_acceptance import subject
from tests.test_citation_acceptance_native import request_file
from tests.test_citation_cohort import seed
from tests.test_postgres_crash import wait_until

WORKER = """
import os,signal,httpx
from pathlib import Path
from nima.__main__ import main
from nima.storage.acceptance_history import JournalSession
def forbidden(*args,**kwargs): raise AssertionError('Unexpected HTTP')
httpx.Client.send=forbidden
original=JournalSession.finish
def finish(self,result,body=None):
    if os.environ['NIMA_TEST_BOUNDARY']=='after': original(self,result,body)
    Path(os.environ['NIMA_TEST_READY']).write_text('ready')
    signal.pause()
JournalSession.finish=finish
raise SystemExit(main(['dataops','record-citation-acceptance',
    '--attempt-id',os.environ['NIMA_TEST_ATTEMPT'],
    '--request',os.environ['NIMA_TEST_REQUEST'],'--report',os.environ['NIMA_TEST_REPORT']]))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
@pytest.mark.parametrize("stop", ["kill", "interrupt"])
def test_terminal_crash_and_concurrency(
    pg_dsn: str, tmp_path: Path, boundary: str, stop: str
) -> None:
    request = seed(pg_dsn, tmp_path / "raw")
    path = request_file(tmp_path, request)
    attempt, ready = uuid4(), tmp_path / "ready"
    application = "nima_acceptance_test_" + uuid4().hex
    with (
        reader(pg_dsn) as (source, _),
        journal_role(pg_dsn) as journal,
        journal_role(pg_dsn, write=False) as inspector,
    ):
        body, _ = prepare_citation_readout(source, request)
        report = subject(tmp_path / "reports", body)
        preserved, before = (report.read_bytes(), report.stat().st_mtime_ns), state(pg_dsn)
        environment = {
            **os.environ,
            "NIMA_DATABASE_URL": source,
            "NIMA_ACCEPTANCE_DATABASE_URL": make_conninfo(journal, application_name=application),
            "NIMA_TEST_BOUNDARY": boundary,
            "NIMA_TEST_READY": str(ready),
            "NIMA_TEST_ATTEMPT": str(attempt),
            "NIMA_TEST_REQUEST": str(path),
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
                assert ready.exists(), "Recorder did not reach the terminal boundary"
                current = show_acceptance(inspector, attempt)
                assert current.execution_state == ("assessed" if boundary == "after" else "pending")
                with pytest.raises(HistoryError, match="^acceptance_history_busy$"):
                    record_citation_acceptance(source, journal, attempt, path, report)
                if stop == "kill":
                    worker.kill()
                else:
                    worker.send_signal(signal.SIGINT)
                stdout, stderr = worker.communicate(timeout=10)
                assert worker.returncode == (-9 if stop == "kill" else 130)
                if stop == "interrupt":
                    assert json.loads(stdout)["failure"] == "acceptance_history_interrupted"
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
        result = record_citation_acceptance(source, journal, attempt, path, report)
        assert result["execution_state"] == "assessed"
        assert result["reused"] == (boundary == "after")
        if boundary == "after":
            assert show_acceptance(inspector, attempt) == current
        assert (report.read_bytes(), report.stat().st_mtime_ns) == preserved
        assert state(pg_dsn) == before
