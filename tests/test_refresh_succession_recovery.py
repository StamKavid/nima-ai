"""Native atomicity and collisions retain a single explicit budget authorization."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest

from nima.storage.refresh_succession import supersede
from nima.storage.workflows import WorkflowError
from tests.test_graph_support import database_snapshot
from tests.test_refresh_retirement_races import configured
from tests.test_refresh_succession_store import retired

WORKER = """
import os,signal
from pathlib import Path
from uuid import UUID
from nima.storage import refresh_succession as succession
def pause():
    Path(os.environ['NIMA_SUCCEED_READY']).write_text('ready')
    signal.pause()
original=succession._outgoing
def read(c,policy):
    result=original(c,policy)
    if result is not None and os.environ['NIMA_SUCCEED_BOUNDARY']=='before': pause()
    return result
succession._outgoing=read
succession.supersede(os.environ['NIMA_TEST_DSN'],UUID(os.environ['NIMA_SUCCEED_OLD']),
    UUID(os.environ['NIMA_SUCCEED_NEW']),authorize_new_budgets=True)
if os.environ['NIMA_SUCCEED_BOUNDARY']=='after': pause()
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_kill_before_or_after_commit_preserves_one_atomic_approval(
    pg_dsn: str, tmp_path: Path, boundary: str
) -> None:
    old, new = retired(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    ready = tmp_path / "ready"
    environment = {
        **os.environ,
        "NIMA_TEST_DSN": pg_dsn,
        "NIMA_SUCCEED_OLD": str(old),
        "NIMA_SUCCEED_NEW": str(new),
        "NIMA_SUCCEED_READY": str(ready),
        "NIMA_SUCCEED_BOUNDARY": boundary,
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
        result = supersede(pg_dsn, old, new, authorize_new_budgets=True)
        assert result["reused"] is (boundary == "after")
        after = database_snapshot(pg_dsn)
        assert len(after["refresh_policies"]) == 2 and len(after["refresh_successions"]) == 1
        assert after["refresh_retirements"] == before["refresh_retirements"]
        if boundary == "after":
            assert after == killed
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.mark.parametrize("isolation", ["read committed", "repeatable read"])
def test_competing_predecessors_cannot_authorize_the_same_successor_twice(
    pg_dsn: str, tmp_path: Path, isolation: str
) -> None:
    a, new = retired(pg_dsn, tmp_path / "raw")
    b, _ = retired(pg_dsn, tmp_path / "raw")
    dsn = configured(pg_dsn, isolation)

    def approve(old: UUID) -> str:
        try:
            supersede(dsn, old, new, authorize_new_budgets=True)
        except WorkflowError as error:
            return error.reason
        return "approved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve, (a, b))) == ["approved", "succession_conflict"]
    after = database_snapshot(pg_dsn)
    assert len(after["refresh_policies"]) == 3 and len(after["refresh_successions"]) == 1
