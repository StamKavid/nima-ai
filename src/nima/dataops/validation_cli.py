"""Explicit validation/inspection with private-safe summaries and stage events."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Never
from uuid import UUID

from nima.contracts.history import HistoryError
from nima.dataops.validation import validate_readout
from nima.storage.validations import show_validation


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise HistoryError("validation_configuration")


def _uuid(value: str) -> UUID:
    try:
        parsed = UUID(value)
        if str(parsed) != value:
            raise ValueError
        return parsed
    except ValueError:
        raise HistoryError("validation_configuration") from None


def _event(name: str, **values: object) -> None:
    print(json.dumps({"component": "dataops.validation", "event": name, **values}), file=sys.stderr)


def run(argv: list[str]) -> int:
    _event("started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        operations = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
        verify = operations.add_parser("validate-readout", allow_abbrev=False)
        inspect = operations.add_parser("validation-show", allow_abbrev=False)
        for operation in (verify, inspect):
            operation.add_argument("--attempt-id", required=True, type=_uuid)
        verify.add_argument("--request", required=True, type=Path)
        verify.add_argument("--report", required=True, type=Path)
        args = parser.parse_args(argv)
        journal_dsn = os.environ.get("NIMA_VALIDATION_DATABASE_URL", "")
        if args.operation == "validation-show":
            result = show_validation(journal_dsn, args.attempt_id)
        else:
            result = validate_readout(
                os.environ.get("NIMA_DATABASE_URL", ""),
                journal_dsn,
                args.attempt_id,
                args.request,
                args.report,
            )
    except HistoryError as error:
        reason = str(error)
    except KeyboardInterrupt:
        reason = "validation_interrupted"
    else:
        _event("completed", status=result["status"], reused=result.get("reused"))
        print(json.dumps(result, allow_nan=False))
        return 3 if result["status"] in {"failed", "blocked"} else 0
    _event("failed", reason=reason)
    print(json.dumps({"status": "failed", "failure": reason}))
    return (
        130
        if reason == "validation_interrupted"
        else 2
        if reason == "validation_configuration"
        else 1
    )
