"""Real local control/runner recovery after SIGKILL, using synthetic provider bytes."""

import asyncio
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest

from nima.orchestration.recovery import recover_child
from nima.orchestration.refresh import Policy
from nima.storage.refresh import RefreshStore
from nima.storage.refresh_progress import reconcile, show
from nima.storage.workflows import RequestStore
from tests.test_refresh_store import DAY
from tests.test_workflow_engine import engine as engine
from tests.test_workflow_engine import runner, stop, wait

WORKER = """
import asyncio,os,signal
from pathlib import Path
from uuid import UUID
from nima.storage.workflows import RequestStore
from nima.orchestration.recovery import recover_child
def pause():
    Path(os.environ['NIMA_RECOVERY_READY']).write_text('ready')
    signal.pause()
begin=RequestStore.begin_dispatch
def reserve(self,*args,**kwargs):
    result=begin(self,*args,**kwargs)
    if kwargs.get('recovery') and os.environ['NIMA_RECOVERY_BOUNDARY']=='reserved': pause()
    return result
RequestStore.begin_dispatch=reserve
finish=RequestStore.finish_dispatch
def acknowledge(self,*args,**kwargs):
    result=finish(self,*args,**kwargs)
    if os.environ['NIMA_RECOVERY_BOUNDARY']=='acknowledged': pause()
    return result
RequestStore.finish_dispatch=acknowledge
asyncio.run(recover_child(UUID(os.environ['NIMA_RECOVERY_POLICY']),
                          UUID(os.environ['NIMA_RECOVERY_REQUEST'])))
"""


@pytest.mark.parametrize("boundary", ["reserved", "acknowledged"])
def test_killed_recovery_preserves_budget_then_real_runner_reconciles_same_child(
    engine: dict[str, str], tmp_path: Path, boundary: str
) -> None:
    dsn = engine["NIMA_DATABASE_URL"]
    store, policy, requests = RefreshStore(dsn), uuid4(), RequestStore(dsn)
    store.create(
        policy, Policy(DAY - timedelta(days=1), ("21",), Path(engine["NIMA_ARCHIVE_ROOT"]))
    )
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        request = session.children(cycle)[0].request
        session.dispatch_state(request, "sending")
    requests.begin_dispatch(request)
    with psycopg.connect(dsn) as c:
        before = c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall()
    worker = runner(engine, tmp_path)
    stop(worker)  # Keep accepted engine work queued until after death/retry assertions.
    ready = tmp_path / "recovery-ready"
    environment = {
        **os.environ,
        **engine,
        "NIMA_RECOVERY_READY": str(ready),
        "NIMA_RECOVERY_POLICY": str(policy),
        "NIMA_RECOVERY_REQUEST": str(request),
        "NIMA_RECOVERY_BOUNDARY": boundary,
    }
    with (tmp_path / "recovery.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", WORKER],
            env=environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    try:
        wait(lambda: ready.exists() or process.poll() is not None)
        assert ready.exists(), (tmp_path / "recovery.log").read_text()[-2000:]
        process.kill()
        assert process.wait(timeout=5) < 0
        with psycopg.connect(dsn) as c:
            assert (
                c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall() == before
            )
            states = c.execute(
                "SELECT state FROM nima.workflow_dispatches ORDER BY created_at"
            ).fetchall()
            assert states == [("pending",), ("pending" if boundary == "reserved" else "accepted",)]
        result = asyncio.run(recover_child(policy, request))
        assert result["dispatch_status"] == "accepted" and result["dispatches"] == 3
        assert result["executions"] == result["attempts"] == 0
        assert not (tmp_path / "calls").exists()
        with psycopg.connect(dsn) as c:
            assert (
                c.execute("SELECT to_jsonb(r) FROM nima.workflow_requests r").fetchall() == before
            )
            accepted = c.execute(
                "SELECT engine_run_id FROM nima.workflow_dispatches WHERE state='accepted'"
            ).fetchall()
    finally:
        stop(process)
    worker = runner(engine, tmp_path)
    try:
        wait(lambda: requests.show(request)["status"] == "complete")
        wait(
            lambda: all(
                httpx.get(engine["PREFECT_API_URL"] + "/flow_runs/" + str(row[0])).json()[
                    "state_type"
                ]
                == "COMPLETED"
                for row in accepted
            )
        )
        with store.lease(policy) as session:
            assert reconcile(session)
            next_cycle = session.cycle(DAY + timedelta(days=1))
            assert next_cycle is not None and next_cycle.cycle_id != cycle.cycle_id
        assert show(store, policy, DAY)["missing_days"] == 0
        assert (tmp_path / "calls").read_text().count("provider") == 1
        assert requests.show(request)["executions"] == requests.show(request)["attempts"] == 1
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT count(*) FROM nima.workflow_requests").fetchone() == (1,)
            assert c.execute("SELECT count(*) FROM nima.observations").fetchone() == (1,)
    finally:
        stop(worker)
