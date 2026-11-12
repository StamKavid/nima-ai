"""Actual process death during SQL completion reconciliation is repeat-safe."""

import os
import signal
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest

from nima.storage.refresh_progress import reconcile, show
from tests.test_refresh_progress import finish
from tests.test_refresh_store import DAY, new_policy
from tests.test_workflow_engine import stop, wait

SCRIPT = """
import os,signal
from pathlib import Path
from uuid import UUID
import psycopg
from nima.storage.refresh import RefreshStore
from nima.storage.refresh_progress import reconcile
def pause():
    Path(os.environ['NIMA_REFRESH_READY']).write_text('ready')
    signal.pause()
original=psycopg.Connection.execute
def execute(self,query,*args,**kwargs):
    result=original(self,query,*args,**kwargs)
    if (os.environ['NIMA_REFRESH_BOUNDARY']=='window'
        and str(query).startswith('UPDATE nima.refresh_windows SET completed_at')):
        pause()
    return result
psycopg.Connection.execute=execute
store=RefreshStore(os.environ['NIMA_DATABASE_URL'])
with store.lease(UUID(os.environ['NIMA_REFRESH_POLICY'])) as session:
    if os.environ['NIMA_REFRESH_BOUNDARY']=='before': pause()
    reconcile(session)
    if os.environ['NIMA_REFRESH_BOUNDARY']=='cycle': pause()
"""


@pytest.mark.parametrize("boundary", ["before", "window", "cycle"])
def test_reconciliation_sigkill_keeps_completed_evidence(
    pg_dsn: str, tmp_path: Path, boundary: str
) -> None:
    store, policy = new_policy(pg_dsn, tmp_path / "raw", start=DAY - timedelta(days=1))
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        children = session.children(cycle)
        finish(pg_dsn, children[0].request)
    ready = tmp_path / "ready"
    environment = {
        **os.environ,
        "NIMA_DATABASE_URL": pg_dsn,
        "NIMA_REFRESH_POLICY": str(policy),
        "NIMA_REFRESH_BOUNDARY": boundary,
        "NIMA_REFRESH_READY": str(ready),
    }
    with (tmp_path / "process.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", SCRIPT],
            env=environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    try:
        wait(lambda: ready.exists() or process.poll() is not None)
        assert process.poll() is None, (tmp_path / "process.log").read_text()[-1000:]
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    finally:
        stop(process)
    with store.lease(policy) as session:
        assert reconcile(session)
        assert session.children(cycle)[0].request == children[0].request
    assert show(store, policy, DAY)["recent_status"] == "complete"
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.observations").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM nima.projection_receipts").fetchone() == (
            1,
        )
