"""Kill actual publication before/after its final link, then reverify and retry."""

import hashlib
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

from nima.analytics.change_readout import prepare_change_result
from nima.dataops.change_acceptance import prepare_change_acceptance
from tests.change_acceptance_samples import request_file
from tests.test_analytics_snapshot import reader, state
from tests.test_change_readout import two_captures
from tests.test_citation_acceptance import subject
from tests.test_graph_pilot_archive import state as archive_state
from tests.test_postgres_crash import wait_until

WORKER = """
import os, signal
from pathlib import Path
import httpx
from nima.__main__ import main
def forbidden(*args, **kwargs):
    raise AssertionError('Acceptance attempted HTTP')
httpx.Client.send = forbidden
original = os.link
def boundary(*args, **kwargs):
    if not args[1].endswith('.json'):
        return original(*args, **kwargs)
    if os.environ['NIMA_ACCEPTANCE_BOUNDARY'] == 'after':
        original(*args, **kwargs)
    Path(os.environ['NIMA_ACCEPTANCE_READY']).write_text('ready')
    signal.pause()
os.link = boundary
raise SystemExit(main(['dataops', 'assess-changes',
    '--request', os.environ['NIMA_ACCEPTANCE_REQUEST'],
    '--report', os.environ['NIMA_ACCEPTANCE_REPORT'],
    '--output-dir', os.environ['NIMA_ACCEPTANCE_OUTPUT']]))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
@pytest.mark.parametrize("stop", ["kill", "interrupt"])
def test_publication_crash_recovers_without_holding_sql_or_changing_evidence(
    pg_dsn: str, tmp_path: Path, boundary: str, stop: str
) -> None:
    root = tmp_path / "raw"
    request = two_captures(pg_dsn, root)
    with reader(pg_dsn) as (dsn, _):
        body = prepare_change_result(dsn, request).body
        report = subject(tmp_path / "reports", body)
        path = request_file(request, tmp_path / "request.json")
        expected = prepare_change_acceptance(dsn, request, report).body
        digest = hashlib.sha256(expected).hexdigest()
        before = state(pg_dsn)
        original = (
            archive_state(tmp_path / "raw"),
            archive_state(tmp_path / "reports"),
            path.read_bytes(),
        )
        output, ready = tmp_path / "output", tmp_path / "ready"
        application = "nima_u4_acceptance_crash_" + uuid4().hex
        normal = {
            **os.environ,
            "NIMA_DATABASE_URL": make_conninfo(dsn, application_name=application),
        }
        environment = {
            **normal,
            "NIMA_ACCEPTANCE_BOUNDARY": boundary,
            "NIMA_ACCEPTANCE_READY": str(ready),
            "NIMA_ACCEPTANCE_OUTPUT": str(output),
            "NIMA_ACCEPTANCE_REQUEST": str(path),
            "NIMA_ACCEPTANCE_REPORT": str(report),
        }
        with subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as worker:
            try:
                wait_until(lambda: ready.exists() or worker.poll() is not None)
                assert ready.exists(), "Worker did not reach its publication boundary"
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
                assert len(list(output.glob("*.json"))) == int(boundary == "after")
                temporary = list(output.glob(".tmp-*"))
                assert len(temporary) == 1 and temporary[0].read_bytes() == expected
                assert temporary[0].stat().st_mode & 0o777 == 0o600
                artifact = output / (digest + ".json")
                old = (
                    (artifact.read_bytes(), artifact.stat().st_mtime_ns)
                    if boundary == "after"
                    else None
                )
                if stop == "kill":
                    worker.kill()
                else:
                    worker.send_signal(signal.SIGINT)
                stdout, stderr = worker.communicate(timeout=5)
                if stop == "kill":
                    assert worker.returncode == -signal.SIGKILL and not stdout
                else:
                    assert worker.returncode == 130
                    assert json.loads(stdout) == {
                        "status": "failed",
                        "failure": "acceptance_interrupted",
                    }
                events = [json.loads(line)["event"] for line in stderr.splitlines()]
                assert events == (["started"] if stop == "kill" else ["started", "failed"])
                assert state(pg_dsn) == before
                retry = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "nima",
                        "dataops",
                        "assess-changes",
                        "--request",
                        str(path),
                        "--report",
                        str(report),
                        "--output-dir",
                        str(output),
                    ],
                    env=normal,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                assert retry.returncode == 0, retry.stderr
                assert json.loads(retry.stdout)["artifact_sha256"] == digest
                assert artifact.read_bytes() == expected
                if old is not None:
                    assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == old
                assert len(list(output.glob("*.json"))) == 1
                assert (
                    archive_state(tmp_path / "raw"),
                    archive_state(tmp_path / "reports"),
                    path.read_bytes(),
                ) == original
                assert state(pg_dsn) == before
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
