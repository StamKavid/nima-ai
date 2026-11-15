"""SIGKILL complete SQL writers before/after COMMIT, with acknowledgment still unsent."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from nima.identity import review_store
from nima.identity.artifacts import encode
from nima.identity.registry_report import build_report
from nima.identity.review_state import fold_events
from tests.test_identity_review_accept import ledger, request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import private_file
from tests.test_identity_review_reversal import revoke
from tests.test_identity_review_support import source_snapshot
from tests.test_postgres_crash import wait_until

WORKER = """
import os,signal
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID
from nima.identity import review_store
from nima.identity.review_inputs import read_request,read_report
os.umask(0o077)
request=read_request(UUID(os.environ['NIMA_REVIEW_REQUEST_ID']),Path(os.environ['NIMA_REVIEW_REQUEST']))
report=None if request.operation=='revoke' else read_report(Path(os.environ['NIMA_REVIEW_REPORT']))
def ready(connection):
    marker=Path(os.environ['NIMA_REVIEW_READY'])
    temporary=marker.with_suffix('.tmp')
    temporary.write_text(str(connection.info.backend_pid)+':'+connection.info.transaction_status.name)
    temporary.replace(marker)
    signal.pause()
if os.environ['NIMA_REVIEW_BOUNDARY']=='before':
    original_append=review_store._append
    def append(connection,event,**kwargs):
        original_append(connection,event,**kwargs)
        ready(connection)
    review_store._append=append
else:
    original_connect=review_store._connect
    @contextmanager
    def connect(dsn):
        with original_connect(dsn) as connection:
            yield connection
            # The nested transaction context has completed its real COMMIT,
            # while the outer connection context still precedes API return.
            ready(connection)
    review_store._connect=connect
review_store.review(os.environ['NIMA_REVIEW_DSN'],request,report=report)
Path(os.environ['NIMA_REVIEW_ACK']).write_text('acknowledged')
"""


@pytest.mark.parametrize("operation", ["accept", "reject", "revoke"])
@pytest.mark.parametrize("boundary", ["before", "after"])
def test_real_commit_interruption_retries_one_complete_decision(
    pg_dsn: str,
    tmp_path: Path,
    operation: str,
    boundary: str,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    initial = (0, 0, 0)
    if operation == "reject":
        chosen = replace(chosen, operation="reject", entity_id=None)
    elif operation == "revoke":
        review_store.review(pg_dsn, chosen, report=parsed)
        chosen = revoke(chosen, 1)
        initial = (1, 1, 1)
    before = source_snapshot(pg_dsn)
    path = private_file(tmp_path, "request.json", encode(chosen.payload()))
    comparison = private_file(tmp_path, "report.json", encode(build_report(parsed.cohort)))
    ready, ack = path.parent / "ready", path.parent / "ack"
    application = "nima_review_crash_" + uuid4().hex
    environment = {
        **os.environ,
        "NIMA_REVIEW_DSN": make_conninfo(pg_dsn, application_name=application),
        "NIMA_REVIEW_REQUEST_ID": str(chosen.request_id),
        "NIMA_REVIEW_REQUEST": str(path),
        "NIMA_REVIEW_REPORT": str(comparison),
        "NIMA_REVIEW_BOUNDARY": boundary,
        "NIMA_REVIEW_READY": str(ready),
        "NIMA_REVIEW_ACK": str(ack),
    }
    expected = (1, 0 if operation == "reject" else 1, 2 if operation == "revoke" else 1)
    with subprocess.Popen(
        [sys.executable, "-c", WORKER],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    ) as worker:
        try:
            wait_until(lambda: ready.exists() or worker.poll() is not None)
            assert ready.exists(), "Review writer did not reach its SQL boundary"
            pid, status = ready.read_text().split(":")
            assert status == ("IDLE" if boundary == "after" else "INTRANS")
            assert not ack.exists()
            assert ledger(pg_dsn) == (expected if boundary == "after" else initial)
            with psycopg.connect(pg_dsn, autocommit=True) as observer:
                assert observer.execute(
                    "SELECT state FROM pg_stat_activity WHERE pid=%s", (int(pid),)
                ).fetchone() == ("idle" if boundary == "after" else "idle in transaction",)
                worker.kill()
                worker.wait(timeout=5)
                assert worker.returncode == -9 and not ack.exists()
                wait_until(
                    lambda: (
                        observer.execute(
                            "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s",
                            (application,),
                        ).fetchone()
                        == (0,)
                    )
                )
            retried = review_store.review(
                pg_dsn, chosen, report=None if operation == "revoke" else parsed
            )
            assert retried.event_id == chosen.request_id and retried.replayed == (
                boundary == "after"
            )
            assert ledger(pg_dsn) == expected
            with psycopg.connect(pg_dsn) as connection:
                folded = fold_events(
                    chosen.subject, review_store._events(connection, chosen.subject)
                )
                assert folded.revision == retried.subject_revision
                assert (folded.accepted_entity_id is not None) == (operation == "accept")
            assert source_snapshot(pg_dsn) == before
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
