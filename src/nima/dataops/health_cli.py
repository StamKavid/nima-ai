"""Selected-run health command with fixed private-safe stdout/stderr events."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import NoReturn
from uuid import UUID

from nima.dataops.health import HealthError, validate_thresholds
from nima.dataops.health_store import prepare_health, validate_path
from nima.identity import AssessmentError
from nima.identity.artifacts import publish


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise HealthError("health_configuration")


def _event(event: str, **fields: str) -> None:
    print(
        json.dumps({"component": "dataops.health", "event": event, **fields}, allow_nan=False),
        file=sys.stderr,
    )


def run(argv: list[str]) -> int:
    _event("started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        parser.add_argument("operation", choices=("health",))
        parser.add_argument("--run-id", type=UUID, required=True)
        parser.add_argument("--capacity-dir", type=Path, required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--max-capture-age-hours", type=int, required=True)
        parser.add_argument("--min-free-bytes", type=int, required=True)
        args = parser.parse_args(argv)
        validate_path(args.output_dir)
        validate_path(args.capacity_dir)
        validate_thresholds(args.max_capture_age_hours, args.min_free_bytes)
        if args.output_dir.is_relative_to(args.capacity_dir):
            raise HealthError("health_configuration")
        result = prepare_health(
            os.environ.get("NIMA_DATABASE_URL", ""),
            args.run_id,
            args.capacity_dir,
            max_age_hours=args.max_capture_age_hours,
            min_free_bytes=args.min_free_bytes,
        )
        publish(args.output_dir, result.body)
    except HealthError as error:
        reason = str(error)
    except (AssessmentError, OSError):
        reason = "health_output"
    except KeyboardInterrupt:
        reason = "health_interrupted"
    else:
        _event("completed", assessment=result.status)
        print(
            json.dumps(
                {"status": result.status, "attention_count": result.attention_count},
                allow_nan=False,
            )
        )
        return 3 if result.status == "attention" else 0
    _event("failed", reason=reason)
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    return 130 if reason == "health_interrupted" else 2 if reason == "health_configuration" else 1
