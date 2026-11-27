"""Bounded record/inspect commands; arbitrary errors and sidecars stay private."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Never
from uuid import UUID

from nima.contracts.acceptance_history import HistoryError
from nima.dataops.citation_acceptance_history import record_citation_acceptance
from nima.storage.acceptance_history import show_acceptance


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise HistoryError("acceptance_history_configuration")


def _uuid(value: str) -> UUID:
    try:
        result = UUID(value)
        if str(result) != value:
            raise ValueError
        return result
    except ValueError:
        raise HistoryError("acceptance_history_configuration") from None


def _event(name: str, **values: object) -> None:
    print(
        json.dumps({"component": "dataops.acceptance_history", "event": name, **values}),
        file=sys.stderr,
    )


def run(argv: list[str]) -> int:
    _event("started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        operations = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
        record = operations.add_parser("record-citation-acceptance", allow_abbrev=False)
        inspect = operations.add_parser("acceptance-show", allow_abbrev=False)
        for operation in (record, inspect):
            operation.add_argument("--attempt-id", required=True, type=_uuid)
        record.add_argument("--request", required=True, type=Path)
        record.add_argument("--report", required=True, type=Path)
        args = parser.parse_args(argv)
        dsn = os.environ.get("NIMA_ACCEPTANCE_DATABASE_URL", "")
        if args.operation == "acceptance-show":
            result = show_acceptance(dsn, args.attempt_id).payload()
            code = 0
        else:
            result = record_citation_acceptance(
                os.environ.get("NIMA_DATABASE_URL", ""),
                dsn,
                args.attempt_id,
                args.request,
                args.report,
            )
            outcome = result["outcome"]
            code = (
                0
                if isinstance(outcome, dict) and outcome["data_fitness"] in {"ready", "limited"}
                else 3
            )
        output = json.dumps(result, allow_nan=False, separators=(",", ":"))
        if len(output.encode()) > 16 * 1024:
            raise HistoryError("acceptance_history_limit")
    except HistoryError as error:
        reason = str(error)
    except KeyboardInterrupt:
        reason = "acceptance_history_interrupted"
    except SystemExit as error:
        return 0 if error.code == 0 else 2
    except Exception:
        reason = "acceptance_history_integrity"
    else:
        _event("completed", execution_state=result["execution_state"], reused=result["reused"])
        print(output)
        return code
    _event("failed", reason=reason)
    print(json.dumps({"status": "failed", "failure": reason}))
    return (
        130
        if reason == "acceptance_history_interrupted"
        else 2
        if reason == ("acceptance_history_configuration")
        else 1
    )
