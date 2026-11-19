"""A real killed process can leave an open trace after SQL commits."""

import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from nima.orchestration.pipeline import prepare_request
from nima.storage.postgres import migrate
from nima.storage.workflows import RequestStore
from tests.test_collection import QUERY
from tests.test_workflow_events import records

WORKER = """
import os,signal
from pathlib import Path
from uuid import UUID
from nima.orchestration.events import StageEvents
from nima.orchestration.pipeline import prepare_request
original=StageEvents.bind_run
def pause(self,run):
    original(self,run)
    Path(os.environ['NIMA_TRACE_READY']).write_text('ready')
    signal.pause()
StageEvents.bind_run=pause
prepare_request(os.environ['NIMA_TEST_DSN'],UUID(os.environ['NIMA_TRACE_REQUEST']))
"""


def test_sigkill_open_trace_requires_sql_inspection_and_same_id_retry(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    request, store = uuid4(), RequestStore(pg_dsn)
    store.submit(request, QUERY, tmp_path / "raw")
    ready, log_path = tmp_path / "ready", tmp_path / "events.jsonl"
    environment = {
        **os.environ,
        "NIMA_WORKFLOW_EVENTS": "stderr",
        "NIMA_TEST_DSN": pg_dsn,
        "NIMA_TRACE_REQUEST": str(request),
        "NIMA_TRACE_READY": str(ready),
    }
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=log,
            start_new_session=True,
        )
    try:
        until = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < until:
            time.sleep(0.01)
        assert ready.exists(), log_path.read_text()[-2000:]
        process.kill()
        assert process.wait(timeout=5) < 0
        opened = records(log_path.read_text())
        assert [row["event"] for row in opened] == ["started", "run_selected"]
        before = store.show(request)
        assert before["run_id"] == opened[-1]["run_id"]
        monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
        assert prepare_request(pg_dsn, request)["run_id"] == before["run_id"]
        retried = records(capsys.readouterr().err)
        assert retried[-1]["event"] == "succeeded"
        assert retried[-1]["invocation_id"] != opened[-1]["invocation_id"]
        assert store.show(request) == before
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
