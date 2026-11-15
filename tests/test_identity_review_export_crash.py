"""Kill actual resolution publication before/after its atomic final link, then retry CLI."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.identity import review_store
from nima.identity.artifacts import encode
from nima.identity.registry_report import build_report
from tests.test_identity_review_accept import ledger, request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import private_file
from tests.test_identity_review_support import source_snapshot
from tests.test_postgres_crash import wait_until

WORKER = """
import os,signal
from pathlib import Path
from nima.__main__ import main
original=os.link
def boundary(*args,**kwargs):
    if not args[1].endswith('.json'):
        return original(*args,**kwargs)
    if os.environ['NIMA_EXPORT_BOUNDARY']=='after':
        original(*args,**kwargs)
    Path(os.environ['NIMA_EXPORT_READY']).write_text('ready')
    signal.pause()
os.link=boundary
main(['identities','resolution','--report-file',os.environ['NIMA_EXPORT_REPORT'],
      '--output-dir',os.environ['NIMA_EXPORT_OUTPUT']])
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_actual_publication_kill_replays_through_normal_operator_cli(
    pg_dsn: str,
    tmp_path: Path,
    boundary: str,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    comparison = private_file(tmp_path, "report.json", encode(build_report(parsed.cohort)))
    output, ready = tmp_path / "exports", tmp_path / "ready"
    application = "nima_export_crash_" + uuid4().hex
    environment = {
        **os.environ,
        "NIMA_DATABASE_URL": make_conninfo(pg_dsn, application_name=application),
        "NIMA_EXPORT_REPORT": str(comparison),
        "NIMA_EXPORT_OUTPUT": str(output),
        "NIMA_EXPORT_READY": str(ready),
        "NIMA_EXPORT_BOUNDARY": boundary,
    }
    before = source_snapshot(pg_dsn)
    with subprocess.Popen(
        [sys.executable, "-c", WORKER],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as worker:
        try:
            wait_until(lambda: ready.exists() or worker.poll() is not None)
            assert ready.exists(), "Export did not reach its publication boundary"
            # Publication must not hold a database snapshot/connection open.
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
            worker.kill()
            stdout, stderr = worker.communicate(timeout=5)
            assert worker.returncode == -9 and stdout == stderr == b""
            command = [
                sys.executable,
                "-m",
                "nima",
                "identities",
                "resolution",
                "--report-file",
                str(comparison),
                "--output-dir",
                str(output),
            ]
            result = subprocess.run(
                command, env=environment, capture_output=True, text=True, timeout=30
            )
            assert result.returncode == 0 and not result.stderr
            summary = json.loads(result.stdout)
            artifacts = list(output.glob("*.json"))
            assert len(artifacts) == 1 and artifacts[0].stem == summary["report_sha256"]
            body = artifacts[0].read_bytes()
            assert hashlib.sha256(body).hexdigest() == summary["report_sha256"]
            assert encode(json.loads(body)) == body
            assert json.loads(body)["reviewed_accepted_links"] == 1
            for private in (
                pg_dsn,
                str(comparison),
                str(output),
                chosen.rationale,
                "001234567",
                "Άλφα",
            ):
                assert private not in result.stdout
            assert artifacts[0].stat().st_mode & 0o777 == 0o600
            assert output.stat().st_mode & 0o777 == 0o700
            assert ledger(pg_dsn) == (1, 1, 1) and source_snapshot(pg_dsn) == before
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
