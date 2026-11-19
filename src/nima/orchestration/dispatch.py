"""SQL-first, at-least-once dispatch to a local Prefect deployment.

https://docs.prefect.io/v3/how-to-guides/deployments/run-deployments
"""

from uuid import UUID

from nima.orchestration.config import local_config
from nima.storage.workflows import RequestStore, WorkflowError


async def dispatch_request(request: UUID, *, recovery: bool = False) -> dict[str, object]:
    config = local_config()
    store = RequestStore(config.dsn)
    status = store.show(request)
    if status["status"] == "complete" and not recovery:
        return status
    dispatch = (
        store.begin_dispatch(request, recovery=True) if recovery else store.begin_dispatch(request)
    )
    try:
        from prefect.client.orchestration import PrefectClient

        async with PrefectClient(api=config.api_url, api_key=None) as client:
            deployment = await client.read_deployment_by_name("nima-kimdis/local")
            run = await client.create_flow_run_from_deployment(
                deployment.id,
                parameters={"request_id": str(request)},
                idempotency_key=dispatch.hex,
            )
    except Exception:
        # A failed/unknown send cannot prove that the server did not accept it.
        store.finish_dispatch(dispatch, None)
        raise WorkflowError("engine_unavailable", True) from None
    store.finish_dispatch(dispatch, run.id)
    return {**store.show(request), "dispatch_status": "accepted"}
