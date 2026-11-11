"""Serve one local deployment with no schedules or automatic provider requests."""

from nima.orchestration.config import local_config


def main() -> None:
    local_config()  # Validate before importing/executing the workflow SDK.
    from prefect.types.entrypoint import EntrypointType

    from nima.orchestration.flows import kimdis_flow

    kimdis_flow.serve(
        name="local",
        limit=1,
        global_limit=1,
        pause_on_shutdown=False,
        print_starting_message=False,
        entrypoint_type=EntrypointType.MODULE_PATH,
    )


if __name__ == "__main__":
    main()
