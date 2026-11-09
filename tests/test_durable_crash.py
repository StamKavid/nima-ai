"""A real killed collector leaves inspectable checkpoints and uncertain attempts."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from nima.storage.postgres import migrate
from nima.storage.runs import inspect_run
from tests.test_postgres_crash import wait_until

WORKER = """
import os, signal
from pathlib import Path
import httpx
from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from tests.test_collection import QUERY, Clock, body
def handle(request):
    page = int(request.url.params['page'])
    if page == int(os.environ['NIMA_BLOCKED_PAGE']):
        Path(os.environ['NIMA_READY']).write_text('request entered')
        signal.pause()
    return httpx.Response(200, content=body(page=page))
with httpx.Client(transport=httpx.MockTransport(handle)) as client:
    collect(QUERY, Limits(), Archive(Path(os.environ['NIMA_ARCHIVE'])),
            client=client, clock=Clock(), database_dsn=os.environ['NIMA_DATABASE_URL'])
"""


@pytest.mark.parametrize("blocked_page", [0, 1])
def test_killed_http_worker_remains_inspectable(
    pg_dsn: str, tmp_path: Path, blocked_page: int
) -> None:
    migrate(pg_dsn)
    ready = tmp_path / "ready"
    archive = tmp_path / "raw"
    environment = {
        **os.environ,
        "NIMA_DATABASE_URL": pg_dsn,
        "NIMA_ARCHIVE": str(archive),
        "NIMA_READY": str(ready),
        "NIMA_BLOCKED_PAGE": str(blocked_page),
    }
    with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
        try:
            wait_until(ready.exists)
            worker.kill()
            assert worker.wait(timeout=5) == -signal.SIGKILL
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
    with psycopg.connect(pg_dsn) as connection:
        row = connection.execute("SELECT run_id FROM nima.ingest_runs").fetchone()
        assert row is not None
        run_id = row[0]
    # The filesystem projection is not the source of durable inspection counts.
    manifest = next(archive.glob("runs/*/manifest.json"))
    manifest.write_text(json.dumps({"summary": {"status": "complete", "pages": 999}}))
    state = inspect_run(pg_dsn, run_id)
    assert state["status"] == "running" and state["worker_liveness"] == "unknown"
    assert state["pages"] == state["records"] == state["next_page"] == blocked_page
    assert state["attempts"] == blocked_page + 1 and state["pending_attempts"] == 1
    assert state["collection_complete"] is False and state["normalization_complete"] is False
