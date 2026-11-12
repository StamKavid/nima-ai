"""Local Prefect control calls under the same policy lock used by dispatch and pause.

https://docs.prefect.io/v3/how-to-guides/deployments/create-schedules
"""

from datetime import date
from uuid import UUID

from prefect.client.orchestration import PrefectClient
from prefect.client.schemas.actions import DeploymentScheduleCreate
from prefect.client.schemas.schedules import CronSchedule

from nima.orchestration.config import local_config
from nima.orchestration.dispatch import dispatch_request
from nima.orchestration.refresh import CRON, TIMEZONE
from nima.storage.refresh import RefreshStore
from nima.storage.refresh_progress import reconcile, show
from nima.storage.workflows import WorkflowError

DEPLOYMENT = "nima-refresh/local"


async def change_schedule(policy_id: UUID, *, enabled: bool) -> None:
    config = local_config()
    store = RefreshStore(config.dsn)
    with store.lease(policy_id) as session:
        # Close the SQL gate before any RPC, including enable acknowledgement loss.
        session.state("pending")
        try:
            async with PrefectClient(api=config.api_url, api_key=None) as client:
                deployment = await client.read_deployment_by_name(DEPLOYMENT)
                schedules = await client.read_deployment_schedules(deployment.id)
                slug = "policy-" + policy_id.hex
                matches = [s for s in schedules if s.slug == slug]
                if len(matches) > 1:
                    raise WorkflowError("schedule_conflict")
                parameters = {"policy_id": str(policy_id)}
                expected = CronSchedule(cron=CRON, timezone=TIMEZONE)
                if not matches and enabled:
                    matches = await client.create_deployment_schedules(
                        deployment.id,
                        [
                            DeploymentScheduleCreate(
                                schedule=expected,
                                active=False,
                                parameters=parameters,
                                slug=slug,
                                max_scheduled_runs=1,
                            )
                        ],
                    )
                if matches:
                    schedule = matches[0]
                    if enabled and (
                        schedule.schedule != expected or schedule.parameters != parameters
                    ):
                        raise WorkflowError("schedule_conflict")
                    await client.update_deployment_schedule(
                        deployment.id, schedule.id, active=enabled
                    )
        except WorkflowError:
            raise
        except Exception:
            raise WorkflowError("engine_unavailable", True) from None
        session.state("enabled" if enabled else "paused")


async def tick(policy_id: UUID, day: date) -> dict[str, object]:
    config = local_config()
    store = RefreshStore(config.dsn)
    with store.lease(policy_id) as session:
        if not session.enabled():
            raise WorkflowError("policy_paused")
        session.connection.execute(
            "UPDATE nima.refresh_policies SET last_tick_at=clock_timestamp() WHERE policy_id=%s",
            (policy_id,),
        )
        reconcile(session)
        cycle = session.open_cycle() or session.cycle(day)
        if cycle and not session.blocked():
            for child in session.children(cycle):
                if session.blocked():
                    break
                if child.complete or child.state != "allocated":
                    continue
                # This lease connection must still be alive before a new send.
                if not session.enabled():
                    raise WorkflowError("policy_paused")
                session.dispatch_state(child.request, "sending")
                await dispatch_request(child.request)
                session.dispatch_state(child.request, "accepted")
            reconcile(session)
    return show(store, policy_id, day)
