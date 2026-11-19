"""A killed retirement transaction commits all control evidence or none of it."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nima.storage.refresh_lifecycle import retire
from tests.test_graph_support import database_snapshot
from tests.test_refresh_recovery_control import child

WORKER = """
import os,signal
from pathlib import Path
from uuid import UUID
from nima.storage import refresh_lifecycle as lifecycle
def pause():
    Path(os.environ['NIMA_RETIRE_READY']).write_text('ready')
    signal.pause()
original=lifecycle.retirement
def read(c,policy):
    result=original(c,policy)
    if result is not None and os.environ['NIMA_RETIRE_BOUNDARY']=='before': pause()
    return result
lifecycle.retirement=read
lifecycle.retire(os.environ['NIMA_TEST_DSN'],UUID(os.environ['NIMA_RETIRE_POLICY']),'operator_stop')
if os.environ['NIMA_RETIRE_BOUNDARY']=='after': pause()
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_sigkill_preserves_atomic_retirement_and_idempotent_retry(
    pg_dsn: str, tmp_path: Path, boundary: str
) -> None:
    _, policy, _ = child(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    ready = tmp_path / "ready"
    environment = {
        **os.environ,
        "NIMA_TEST_DSN": pg_dsn,
        "NIMA_RETIRE_POLICY": str(policy),
        "NIMA_RETIRE_READY": str(ready),
        "NIMA_RETIRE_BOUNDARY": boundary,
    }
    with (tmp_path / "worker.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    try:
        until = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < until:
            time.sleep(0.01)
        assert ready.exists(), (tmp_path / "worker.log").read_text()[-2000:]
        process.kill()
        assert process.wait(timeout=5) < 0
        killed = database_snapshot(pg_dsn)
        if boundary == "before":
            assert killed == before
        else:
            assert len(killed["refresh_retirements"]) == 1
        result = retire(pg_dsn, policy, "operator_stop")
        assert result["reused"] is (boundary == "after")
        committed = database_snapshot(pg_dsn)
        assert len(committed["refresh_retirements"]) == 1
        assert committed["workflow_requests"] == before["workflow_requests"]
        assert committed["refresh_windows"] == before["refresh_windows"]
        if boundary == "after":
            assert committed == killed
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
