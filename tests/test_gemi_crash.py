"""SIGKILL during a synthetic request and before terminal manifest publication."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from nima.ingestion.gemi import collect
from tests.test_gemi_collection import KEY
from tests.test_gemi_contracts import profile
from tests.test_postgres_crash import wait_until

WORKER = """
import os, signal
from pathlib import Path
import httpx
from nima.ingestion.archive import Archive
from nima.ingestion.gemi import collect
from tests.test_gemi_contracts import profile
def pause():
    Path(os.environ['NIMA_GEMI_READY']).write_text('ready')
    signal.pause()
original = Archive.write_manifest
def write(self, run, manifest):
    if (os.environ['NIMA_GEMI_BOUNDARY'] == 'manifest'
            and manifest['summary']['status'] == 'complete'):
        pause()
    original(self, run, manifest)
Archive.write_manifest = write
def handle(request):
    if os.environ['NIMA_GEMI_BOUNDARY'] == 'request': pause()
    return httpx.Response(200, content=profile(), headers={'content-type':'application/json'})
with httpx.Client(transport=httpx.MockTransport(handle)) as client:
    collect(('1',), Path(os.environ['NIMA_GEMI_ARCHIVE']),
            api_key='synthetic-test-credential', client=client)
"""


@pytest.mark.parametrize("boundary", ["request", "manifest"])
def test_killed_worker_keeps_truthful_history_and_fresh_lookup_is_independent(
    tmp_path: Path, boundary: str
) -> None:
    root, ready = tmp_path / "raw", tmp_path / "ready"
    environment = {
        **os.environ,
        "NIMA_GEMI_READY": str(ready),
        "NIMA_GEMI_ARCHIVE": str(root),
        "NIMA_GEMI_BOUNDARY": boundary,
    }
    with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
        try:
            wait_until(ready.exists)
            worker.kill()
            worker.wait(timeout=5)
            old = next((root / "runs").glob("*/manifest.json"))
            original = old.read_bytes()
            snapshot = json.loads(original)
            assert snapshot["summary"]["status"] == "running"
            assert not snapshot["summary"]["collection_complete"]
            assert snapshot["attempts"][-1]["state"] == (
                "started" if boundary == "request" else "finished"
            )
            assert len(list((root / "objects").glob("*/*.body"))) == int(boundary == "manifest")
            with httpx.Client(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200, content=profile(), headers={"content-type": "application/json"}
                    )
                )
            ) as client:
                assert collect(("1",), root, api_key=KEY, client=client).status == "complete"
            assert old.read_bytes() == original and len(list((root / "runs").iterdir())) == 2
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
