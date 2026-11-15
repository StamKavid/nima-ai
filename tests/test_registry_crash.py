"""SIGKILL the real SQL-to-report CLI at its atomic publication boundary."""

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

from nima.identity.artifacts import encode
from nima.identity.registry_cohort import read_comparison_cohort
from nima.identity.registry_report import build_report
from nima.projections.worker import PROJECTION_VERSION
from tests.test_gemi_import import counts as registry_counts
from tests.test_gemi_import_archive import snapshot
from tests.test_identity_report import seed
from tests.test_kimdis_pages import record
from tests.test_page_store import counts
from tests.test_postgres_crash import wait_until
from tests.test_registry_cohort import registry_import

WORKER = """
import os, signal
from pathlib import Path
from nima.__main__ import main
original = os.link
def boundary(*args, **kwargs):
    if not args[1].endswith('.json'):
        return original(*args, **kwargs)
    if os.environ['NIMA_COMPARE_BOUNDARY'] == 'after':
        original(*args, **kwargs)
    Path(os.environ['NIMA_COMPARE_READY']).write_text('ready')
    signal.pause()
os.link = boundary
raise SystemExit(main(['identities', 'compare', os.environ['NIMA_COMPARE_RUN'],
    '--gemi-import', os.environ['NIMA_COMPARE_IMPORT'],
    '--projection-version', 'kimdis-participation-v1',
    '--output-dir', os.environ['NIMA_COMPARE_OUTPUT']]))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_killed_comparison_replays_one_complete_artifact_without_source_writes(
    pg_dsn: str,
    tmp_path: Path,
    boundary: str,
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    expected = encode(
        build_report(read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION))
    )
    digest = hashlib.sha256(expected).hexdigest()
    before = counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")
    output, ready = tmp_path / "reports", tmp_path / "ready"
    application = "nima_compare_" + uuid4().hex
    environment = {
        **os.environ,
        "NIMA_DATABASE_URL": make_conninfo(pg_dsn, application_name=application),
        "NIMA_COMPARE_BOUNDARY": boundary,
        "NIMA_COMPARE_READY": str(ready),
        "NIMA_COMPARE_RUN": str(run),
        "NIMA_COMPARE_IMPORT": str(selected),
        "NIMA_COMPARE_OUTPUT": str(output),
    }
    with subprocess.Popen(
        [sys.executable, "-c", WORKER],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as worker:
        try:
            wait_until(ready.exists)
            # Publication starts only after both snapshot/schema connections close.
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
            if boundary == "after":
                assert (output / (digest + ".json")).read_bytes() == expected
            worker.kill()
            stdout, stderr = worker.communicate(timeout=5)
            assert worker.returncode == -signal.SIGKILL and stdout == stderr == b""
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.communicate(timeout=5)
    command = [
        sys.executable,
        "-m",
        "nima",
        "identities",
        "compare",
        str(run),
        "--gemi-import",
        str(selected),
        "--projection-version",
        PROJECTION_VERSION,
        "--output-dir",
        str(output),
    ]
    for _ in range(2):
        result = subprocess.run(
            command, env=environment, capture_output=True, timeout=15, check=False
        )
        assert result.returncode == 0 and result.stderr == b""
        summary = json.loads(result.stdout)
        assert summary["report_sha256"] == digest and summary["automatic_identity_links"] == 0
        assert len(list(output.glob("*.json"))) == 1
        assert (output / (digest + ".json")).read_bytes() == expected
    assert (counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")) == before
