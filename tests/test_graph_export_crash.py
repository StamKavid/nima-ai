"""Real SIGKILL/Ctrl+C at the final link, followed by the uninstrumented graph CLI."""

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

from nima.graph.build import build_graph
from nima.graph.snapshot import read_snapshot
from nima.identity import review_store
from nima.identity.artifacts import encode
from nima.identity.registry_report import build_report
from tests.test_graph_support import database_snapshot
from tests.test_identity_review_accept import request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import private_file
from tests.test_postgres_crash import wait_until

WORKER = """
import os,signal
from pathlib import Path
from nima.__main__ import main
original=os.link
def boundary(*args,**kwargs):
    if not args[1].endswith('.json'):
        return original(*args,**kwargs)
    if os.environ['NIMA_GRAPH_BOUNDARY']=='after':
        original(*args,**kwargs)
    Path(os.environ['NIMA_GRAPH_READY']).write_text('ready')
    signal.pause()
os.link=boundary
raise SystemExit(main(['graph','snapshot','--report-file',os.environ['NIMA_GRAPH_REPORT'],
    '--entity-id',os.environ['NIMA_GRAPH_ENTITY'],'--output-dir',os.environ['NIMA_GRAPH_OUTPUT']]))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
@pytest.mark.parametrize("stop", ["kill", "interrupt"])
def test_actual_publication_interruption_recovers_with_closed_sql_and_unchanged_rows(
    pg_dsn: str, tmp_path: Path, boundary: str, stop: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    comparison = private_file(tmp_path, "report.json", encode(build_report(parsed.cohort)))
    expected = encode(build_graph(read_snapshot(pg_dsn, parsed), entity_id=chosen.entity_id))
    digest = hashlib.sha256(expected).hexdigest()
    output, ready = tmp_path / "exports", tmp_path / "ready"
    application = "nima_graph_crash_" + uuid4().hex
    normal_environment = {
        **os.environ,
        "NIMA_DATABASE_URL": make_conninfo(pg_dsn, application_name=application),
    }
    environment = {
        **normal_environment,
        "NIMA_GRAPH_REPORT": str(comparison),
        "NIMA_GRAPH_ENTITY": str(chosen.entity_id),
        "NIMA_GRAPH_OUTPUT": str(output),
        "NIMA_GRAPH_READY": str(ready),
        "NIMA_GRAPH_BOUNDARY": boundary,
    }
    before = database_snapshot(pg_dsn)
    with subprocess.Popen(
        [sys.executable, "-c", WORKER],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as worker:
        try:
            wait_until(lambda: ready.exists() or worker.poll() is not None)
            assert ready.exists(), "Graph export did not reach its real publication boundary"
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
            assert database_snapshot(pg_dsn) == before
            assert len(list(output.glob("*.json"))) == int(boundary == "after")
            temporary = list(output.glob(".tmp-*"))
            assert temporary and all(p.stat().st_mode & 0o777 == 0o600 for p in temporary)
            assert all(p.read_bytes() == expected for p in temporary)
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
            assert not stderr
            if stop == "kill":
                assert worker.returncode == -9 and not stdout
            else:
                assert worker.returncode == 130
                assert json.loads(stdout) == {"status": "failed", "failure": "graph_interrupted"}
            assert database_snapshot(pg_dsn) == before
            command = [
                sys.executable,
                "-m",
                "nima",
                "graph",
                "snapshot",
                "--report-file",
                str(comparison),
                "--entity-id",
                str(chosen.entity_id),
                "--output-dir",
                str(output),
            ]
            result = subprocess.run(
                command, env=normal_environment, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0 and not result.stderr
            summary = json.loads(result.stdout)
            assert summary["graph_sha256"] == digest and summary["reviewed_accepted_links"] == 1
            assert len(list(output.glob("*.json"))) == 1
            assert artifact.read_bytes() == expected
            assert encode(json.loads(expected)) == expected
            if old is not None:
                assert old == (artifact.read_bytes(), artifact.stat().st_mtime_ns)
            assert output.stat().st_mode & 0o777 == 0o700
            assert artifact.stat().st_mode & 0o777 == 0o600
            for value in (
                pg_dsn,
                str(comparison),
                str(output),
                chosen.rationale,
                "001234567",
                "Άλφα",
            ):
                assert value not in result.stdout
            assert database_snapshot(pg_dsn) == before
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
