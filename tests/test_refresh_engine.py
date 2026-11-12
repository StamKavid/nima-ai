"""Refresh uses the actual local control API, runner and SQL evidence."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from prefect.client.orchestration import PrefectClient
from prefect.client.schemas.schedules import IntervalSchedule

from nima.orchestration.refresh import Policy, business_date
from nima.orchestration.refresh_control import change_schedule, tick
from nima.storage.refresh import RefreshStore
from nima.storage.refresh_progress import show
from nima.storage.workflows import WorkflowError
from tests.test_workflow_engine import engine as engine
from tests.test_workflow_engine import runner, stop, wait


@pytest.fixture(autouse=True)
def faster_test_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PREFECT_SERVER_SERVICES_SCHEDULER_LOOP_SECONDS", "1")


def coordinator_ready(environment: dict[str, str]) -> bool:
    return (
        httpx.get(
            environment["PREFECT_API_URL"] + "/deployments/name/nima-refresh/local"
        ).status_code
        == 200
    )


def test_real_schedule_tick_duplicate_and_runner_restart(
    engine: dict[str, str], tmp_path: Path
) -> None:
    day = business_date(datetime.now(UTC))
    store, policy_id = RefreshStore(engine["NIMA_DATABASE_URL"]), uuid4()
    store.create(
        policy_id, Policy(day - timedelta(days=1), ("21",), Path(engine["NIMA_ARCHIVE_ROOT"]))
    )
    worker = runner(engine, tmp_path)
    try:
        wait(lambda: coordinator_ready(engine))
        assert show(store, policy_id, day)["state"] == "paused"
        with pytest.raises(WorkflowError, match="policy_paused"):
            asyncio.run(tick(policy_id, day))
        asyncio.run(change_schedule(policy_id, enabled=True))
        first = asyncio.run(tick(policy_id, day))
        assert first["cycle_id"] is not None
        asyncio.run(tick(policy_id, day))
        wait(lambda: httpx.get(engine["PREFECT_API_URL"] + "/health").status_code == 200)

        def complete() -> bool:
            result = asyncio.run(tick(policy_id, day))
            return result["recent_status"] == "complete"

        wait(complete)
        assert (tmp_path / "calls").read_text().count("provider") == 1
        deployment_url = engine["PREFECT_API_URL"] + "/deployments/name/nima-refresh/local"
        before_restart = httpx.get(deployment_url).json()["updated"]
        stop(worker)
        worker = runner(engine, tmp_path)
        wait(
            lambda: (
                worker.poll() is None
                and httpx.get(deployment_url).json()["updated"] != before_restart
            )
        )

        async def schedule_active() -> bool:
            async with PrefectClient(api=engine["PREFECT_API_URL"]) as client:
                deployment = await client.read_deployment_by_name("nima-refresh/local")
                schedules = await client.read_deployment_schedules(deployment.id)
                return len(schedules) == 1 and schedules[0].active

        wait(lambda: asyncio.run(schedule_active()))
        asyncio.run(change_schedule(policy_id, enabled=False))
        assert show(store, policy_id, day)["state"] == "paused"
        assert not asyncio.run(schedule_active())
    finally:
        stop(worker)


def test_real_scheduler_runs_coordinator_without_extra_child_budget(
    engine: dict[str, str], tmp_path: Path
) -> None:
    day = business_date(datetime.now(UTC))
    store, policy_id = RefreshStore(engine["NIMA_DATABASE_URL"]), uuid4()
    store.create(
        policy_id, Policy(day - timedelta(days=1), ("21",), Path(engine["NIMA_ARCHIVE_ROOT"]))
    )
    worker = runner(engine, tmp_path)
    try:
        wait(lambda: coordinator_ready(engine))
        asyncio.run(change_schedule(policy_id, enabled=True))

        async def short_schedule() -> None:
            async with PrefectClient(api=engine["PREFECT_API_URL"]) as client:
                deployment = await client.read_deployment_by_name("nima-refresh/local")
                schedules = await client.read_deployment_schedules(deployment.id)
                await client.update_deployment_schedule(
                    deployment.id,
                    schedules[0].id,
                    schedule=IntervalSchedule(
                        interval=timedelta(seconds=2), anchor_date=datetime.now(UTC)
                    ),
                )

        asyncio.run(short_schedule())
        wait(lambda: show(store, policy_id, day)["recent_status"] == "complete", timeout=90)
        asyncio.run(change_schedule(policy_id, enabled=False))
        assert (tmp_path / "calls").read_text().count("provider") == 1
    finally:
        stop(worker)


def test_missing_deployment_leaves_sql_gate_closed(engine: dict[str, str], tmp_path: Path) -> None:
    store, policy_id = RefreshStore(engine["NIMA_DATABASE_URL"]), uuid4()
    day = business_date(datetime.now(UTC))
    store.create(policy_id, Policy(day, ("21",), tmp_path / "raw"))
    with pytest.raises(WorkflowError, match="engine_unavailable"):
        asyncio.run(change_schedule(policy_id, enabled=True))
    assert show(store, policy_id, day)["state"] != "enabled"
    with pytest.raises(WorkflowError, match="policy_paused"):
        asyncio.run(tick(policy_id, day))
    assert not (tmp_path / "raw").exists()


CRASH_DISPATCH = """
import asyncio,os,signal
from datetime import date
from pathlib import Path
from uuid import UUID
from nima.storage.refresh import RefreshSession
from nima.orchestration.refresh_control import tick
original=RefreshSession.dispatch_state
def paused(self,request,state):
    if state=='sending':
        result=original(self,request,state)
        if os.environ['NIMA_REFRESH_BOUNDARY']=='before':
            Path(os.environ['NIMA_REFRESH_READY']).write_text('ready')
            signal.pause()
        return result
    if state=='accepted' and os.environ['NIMA_REFRESH_BOUNDARY']=='after':
        Path(os.environ['NIMA_REFRESH_READY']).write_text('ready')
        signal.pause()
    return original(self,request,state)
RefreshSession.dispatch_state=paused
asyncio.run(tick(UUID(os.environ['NIMA_REFRESH_POLICY']),date.fromisoformat(os.environ['NIMA_REFRESH_DAY'])))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_sigkill_dispatch_intent_requires_same_request_recovery(
    engine: dict[str, str], tmp_path: Path, boundary: str
) -> None:
    import os
    import signal
    import subprocess
    import sys

    import psycopg

    from nima.orchestration.dispatch import dispatch_request

    day = business_date(datetime.now(UTC))
    store, policy_id = RefreshStore(engine["NIMA_DATABASE_URL"]), uuid4()
    store.create(
        policy_id, Policy(day - timedelta(days=1), ("21",), Path(engine["NIMA_ARCHIVE_ROOT"]))
    )
    worker = runner(engine, tmp_path)
    try:
        wait(lambda: coordinator_ready(engine))
        asyncio.run(change_schedule(policy_id, enabled=True))
        stop(worker)
        ready = tmp_path / "coordinator-ready"
        environment = {
            **engine,
            "NIMA_REFRESH_BOUNDARY": boundary,
            "NIMA_REFRESH_READY": str(ready),
            "NIMA_REFRESH_POLICY": str(policy_id),
            "NIMA_REFRESH_DAY": day.isoformat(),
        }
        with (tmp_path / "coordinator.log").open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, "-c", CRASH_DISPATCH],
                env=environment,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        try:
            wait(lambda: ready.exists() or process.poll() is not None)
            assert process.poll() is None, (tmp_path / "coordinator.log").read_text()[-1000:]
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        finally:
            stop(process)
        status = asyncio.run(tick(policy_id, day))
        assert status["blocked_reason"] == "dispatch_unknown"
        with psycopg.connect(engine["NIMA_DATABASE_URL"]) as connection:
            row = connection.execute("SELECT request_id FROM nima.refresh_windows").fetchone()
            assert row is not None
            request = row[0]
            assert connection.execute("SELECT count(*) FROM nima.workflow_requests").fetchone() == (
                1,
            )
            assert connection.execute(
                "SELECT count(*) FROM nima.workflow_dispatches"
            ).fetchone() == (0 if boundary == "before" else 1,)
        asyncio.run(dispatch_request(request))
        worker = runner(engine, tmp_path)
        wait(lambda: asyncio.run(tick(policy_id, day))["recent_status"] == "complete")
        assert (tmp_path / "calls").read_text().count("provider") == 1
        asyncio.run(change_schedule(policy_id, enabled=False))
    finally:
        stop(worker)


def test_pause_cannot_interleave_with_dispatch_decision(
    engine: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from nima.orchestration import refresh_control
    from nima.orchestration.dispatch import dispatch_request

    day = business_date(datetime.now(UTC))
    store, policy_id = RefreshStore(engine["NIMA_DATABASE_URL"]), uuid4()
    store.create(
        policy_id, Policy(day - timedelta(days=1), ("21",), Path(engine["NIMA_ARCHIVE_ROOT"]))
    )
    worker = runner(engine, tmp_path)
    sent, release = Event(), Event()
    original = dispatch_request

    async def hold_real_ack(request: object) -> dict[str, object]:
        from uuid import UUID

        assert isinstance(request, UUID)
        result = await original(request)
        sent.set()
        assert release.wait(10)
        return result

    try:
        wait(lambda: coordinator_ready(engine))
        asyncio.run(change_schedule(policy_id, enabled=True))
        monkeypatch.setattr(refresh_control, "dispatch_request", hold_real_ack)
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(asyncio.run, tick(policy_id, day))
            try:
                assert sent.wait(10)
                with pytest.raises(WorkflowError, match="policy_busy"):
                    asyncio.run(change_schedule(policy_id, enabled=False))
            finally:
                release.set()
            running.result(timeout=10)
        asyncio.run(change_schedule(policy_id, enabled=False))
        with pytest.raises(WorkflowError, match="policy_paused"):
            asyncio.run(tick(policy_id, day))
    finally:
        release.set()
        stop(worker)


@pytest.mark.parametrize("unknown", [False, True])
def test_unknown_or_terminal_child_prevents_further_dispatch(
    engine: dict[str, str], tmp_path: Path, unknown: bool
) -> None:
    from nima.storage.workflows import RequestStore

    day = business_date(datetime.now(UTC))
    store, policy_id = RefreshStore(engine["NIMA_DATABASE_URL"]), uuid4()
    store.create(
        policy_id, Policy(day - timedelta(days=2), ("21",), Path(engine["NIMA_ARCHIVE_ROOT"]))
    )
    with store.lease(policy_id) as session:
        session.state("enabled")
        cycle = session.cycle(day)
        assert cycle is not None
        first, second = session.children(cycle)
        session.dispatch_state(first.request, "sending")
        if not unknown:
            session.dispatch_state(first.request, "accepted")
            RequestStore(engine["NIMA_DATABASE_URL"]).outcome(
                first.request, "deferred", "workflow_attempt_limit"
            )
    result = asyncio.run(tick(policy_id, day))
    assert result["blocked_reason"] == ("dispatch_unknown" if unknown else "child_incomplete")
    with store.lease(policy_id) as session:
        assert session.children(cycle)[1].state == "allocated"
    assert not (tmp_path / "calls").exists()
