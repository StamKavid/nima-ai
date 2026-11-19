"""Private selected-policy health publication with fixed operational diagnostics."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import NoReturn
from uuid import UUID

from nima.dataops.health import HealthError
from nima.dataops.health_store import validate_path
from nima.dataops.refresh_health import assess, validate_ages
from nima.dataops.refresh_health_store import read_snapshot
from nima.identity import AssessmentError
from nima.identity.artifacts import publish


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise HealthError("refresh_health_configuration")


def _event(event: str, **fields: str) -> None:
    print(
        json.dumps({"component": "dataops.refresh_health", "event": event, **fields}),
        file=sys.stderr,
    )


def run(argv: list[str]) -> int:
    _event("started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        parser.add_argument("operation", choices=("refresh-health",))
        parser.add_argument("--policy-id", type=UUID, required=True)
        parser.add_argument("--max-tick-age-hours", type=int, required=True)
        parser.add_argument("--max-observation-age-hours", type=int, required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        args = parser.parse_args(argv)
        try:
            validate_path(args.output_dir)
        except HealthError:
            raise HealthError("refresh_health_configuration") from None
        validate_ages(args.max_tick_age_hours, args.max_observation_age_hours)
        result = assess(
            read_snapshot(os.environ.get("NIMA_DATABASE_URL", ""), args.policy_id),
            max_tick_age_hours=args.max_tick_age_hours,
            max_observation_age_hours=args.max_observation_age_hours,
        )
        publish(args.output_dir, result.body)
    except HealthError as error:
        reason = str(error)
    except (AssessmentError, OSError):
        reason = "refresh_health_output"
    except KeyboardInterrupt:
        reason = "refresh_health_interrupted"
    else:
        _event("completed", assessment=result.status)
        print(json.dumps({"status": result.status, "attention_count": result.attention_count}))
        return 3 if result.status == "attention" else 0
    _event("failed", reason=reason)
    print(json.dumps({"status": "failed", "failure": reason}))
    return (
        130
        if reason == "refresh_health_interrupted"
        else 2
        if reason == "refresh_health_configuration"
        else 1
    )
