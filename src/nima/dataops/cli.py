"""DataOps command routing; existing health parsing/events remain unchanged."""

import argparse


def run(argv: list[str]) -> int:
    if argv in (["--help"], ["-h"]):
        parser = argparse.ArgumentParser(prog="python -m nima dataops")
        parser.add_argument(
            "operation",
            choices=(
                "health",
                "refresh-health",
                "validate-readout",
                "validation-show",
                "validation-health",
            ),
        )
        parser.print_help()
        return 0
    if argv and argv[0] == "refresh-health":
        from nima.dataops.refresh_health_cli import run as refresh_health_run

        return refresh_health_run(argv)
    if argv and argv[0] in {"validate-readout", "validation-show", "validation-health"}:
        from nima.dataops.validation_cli import run as validation_run

        return validation_run(argv)
    from nima.dataops.health_cli import run as health_run

    return health_run(argv)
