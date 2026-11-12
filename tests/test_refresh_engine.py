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
