"""Serve local collector/coordinator deployments; fresh installs have no schedules."""

import asyncio

from nima.orchestration.config import local_config


async def _serve() -> None:
    from prefect import aserve
    from prefect.types.entrypoint import EntrypointType

    from nima.orchestration.flows import kimdis_flow
    from nima.orchestration.refresh_flow import refresh_flow

    collector = await kimdis_flow.ato_deployment(
        name="local",
        concurrency_limit=1,
        entrypoint_type=EntrypointType.MODULE_PATH,
    )
    coordinator = await refresh_flow.ato_deployment(
        name="local",
        concurrency_limit=1,
        entrypoint_type=EntrypointType.MODULE_PATH,
    )
    # 3.9.2 defaults to [] (clear), while its update API rejects explicit null.
    # Omit this public Pydantic field from the SDK's exclude_unset update payload.
    coordinator.schedules = None
    coordinator.model_fields_set.discard("schedules")
    await aserve(
        collector, coordinator, limit=1, pause_on_shutdown=False, print_starting_message=False
    )


def main() -> None:
    local_config()
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
