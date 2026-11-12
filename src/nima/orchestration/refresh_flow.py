"""Short coordinator; it never holds its runner slot waiting for child collections."""

import asyncio
from uuid import UUID

from prefect import flow
from prefect.runtime import flow_run

from nima.orchestration.refresh import business_date
from nima.orchestration.refresh_control import tick
from nima.storage.workflows import WorkflowError


@flow(
    name="nima-refresh",
    version="kimdis-refresh-v1",
    retries=0,
    persist_result=False,
    log_prints=False,
)
def refresh_flow(policy_id: str) -> dict[str, object]:
    try:
        policy = UUID(policy_id)
    except ValueError:
        raise WorkflowError("policy_invalid") from None
    # Scheduled time is stable across delayed execution and flow-run replay.
    return asyncio.run(tick(policy, business_date(flow_run.scheduled_start_time)))
