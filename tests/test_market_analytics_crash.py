"""Real process interruption before originals and on both sides of publication."""

import hashlib
import json
import os
import signal
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.analytics.export import export_readout
from nima.analytics.reconcile import reconcile
from nima.analytics.result import build_result
from nima.analytics.snapshot import read_snapshot
from tests.test_analytics_cli import arguments
from tests.test_analytics_reconcile import body_path, captured
from tests.test_analytics_snapshot import reader, state
from tests.test_market_analytics import request_file
from tests.test_postgres_crash import wait_until

WORKER = """
import os,signal,socket,httpx
from pathlib import Path
from nima.__main__ import main
from nima.analytics import export
def forbidden(*args,**kwargs):
    raise AssertionError('Unexpected source route')
httpx.Client=forbidden
socket.socket=forbidden
def pause():
    Path(os.environ['NIMA_ANALYTICS_READY']).write_text('ready')
    signal.pause()
original_link=os.link
def link(*args,**kwargs):
    if not args[1].endswith('.json'):
        return original_link(*args,**kwargs)
    if os.environ['NIMA_ANALYTICS_BOUNDARY']=='after':
        original_link(*args,**kwargs)
    pause()
original_reconcile=export.reconcile
def originals(*args,**kwargs):
    pause()
    return original_reconcile(*args,**kwargs)
if os.environ['NIMA_ANALYTICS_BOUNDARY']=='originals':
    export.reconcile=originals
else:
    os.link=link
raise SystemExit(main(['analytics','supplier-buyers',
    '--request',os.environ['NIMA_ANALYTICS_REQUEST'],
    '--output-dir',os.environ['NIMA_ANALYTICS_OUTPUT']]))
"""


@pytest.mark.parametrize("boundary", ["originals", "before", "after"])
@pytest.mark.parametrize("stop", ["kill", "interrupt"])
def test_actual_interruption_replays_identically_and_preserves_old_reports(
    pg_dsn: str, tmp_path: Path, boundary: str, stop: str
) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    path = request_file(request, tmp_path / "request.json")
    output, ready = tmp_path / "reports", tmp_path / "ready"
    application = "nima_analytics_crash_" + uuid4().hex
    with reader(pg_dsn) as (dsn, _):
        prior_summary = export_readout(dsn, path, output)
        prior = output / (prior_summary.artifact_sha256 + ".json")
        preserved = prior.read_bytes(), prior.stat().st_mtime_ns
        request = replace(request, observation_cutoff=datetime(2025, 1, 1, tzinfo=UTC))
        request_file(request, path)
        selected = read_snapshot(
            dsn, request.run_ids, tax_id=request.supplier_tax_id, cutoff=request.observation_cutoff
        )
        expected = build_result(reconcile(selected, request))
        digest = hashlib.sha256(expected).hexdigest()
        assert digest != prior_summary.artifact_sha256
        final = output / (digest + ".json")
        before = state(pg_dsn)
        original_bytes = body_path(request, snapshot).read_bytes()
        normal_environment = {
            **os.environ,
            "NIMA_DATABASE_URL": make_conninfo(dsn, application_name=application),
        }
        environment = {
            **normal_environment,
            "NIMA_ANALYTICS_REQUEST": str(path),
            "NIMA_ANALYTICS_OUTPUT": str(output),
            "NIMA_ANALYTICS_READY": str(ready),
            "NIMA_ANALYTICS_BOUNDARY": boundary,
        }
        with subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as worker:
            try:
                wait_until(lambda: ready.exists() or worker.poll() is not None)
                assert ready.exists(), "Readout did not reach its real process boundary"
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
                assert state(pg_dsn) == before
                assert preserved == (prior.read_bytes(), prior.stat().st_mtime_ns)
                assert final.exists() == (boundary == "after")
                temporary = list(output.glob(".tmp-*"))
                assert bool(temporary) == (boundary != "originals")
                assert all(
                    p.read_bytes() == expected and p.stat().st_mode & 0o777 == 0o600
                    for p in temporary
                )
                published = (
                    (final.read_bytes(), final.stat().st_mtime_ns) if final.exists() else None
                )
                if stop == "kill":
                    worker.kill()
                else:
                    worker.send_signal(signal.SIGINT)
                stdout, stderr = worker.communicate(timeout=5)
                assert not stderr
                if stop == "kill":
                    assert worker.returncode == -9 and not stdout
                else:
                    assert worker.returncode == 130
                    assert json.loads(stdout) == {
                        "status": "failed",
                        "failure": "analytics_interrupted",
                    }
                result = subprocess.run(
                    [sys.executable, "-m", "nima", *arguments(path, output)],
                    env=normal_environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert result.returncode == 0 and not result.stderr
                summary = json.loads(result.stdout)
                assert summary["artifact_sha256"] == digest and summary["record_count"] == 0
                assert summary["outcome"] == "no_observations_before_cutoff"
                assert len(list(output.glob("*.json"))) == 2
                assert final.read_bytes() == expected
                assert final.stat().st_mode & 0o777 == 0o600
                assert output.stat().st_mode & 0o777 == 0o700
                if published is not None:
                    assert published == (final.read_bytes(), final.stat().st_mtime_ns)
                assert preserved == (prior.read_bytes(), prior.stat().st_mtime_ns)
                assert state(pg_dsn) == before
                assert body_path(request, snapshot).read_bytes() == original_bytes
                for private in (dsn, str(path), str(output), request.supplier_tax_id):
                    assert private not in result.stdout
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=5)
