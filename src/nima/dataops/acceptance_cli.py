"""Offline acceptance commands with fixed, private-safe terminal results."""

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Never

from nima.dataops.acceptance_files import AcceptanceError
from nima.dataops.buyer_acceptance import BuyerAcceptanceExport, export_buyer_acceptance
from nima.dataops.change_acceptance import ChangeAcceptanceExport, export_change_acceptance
from nima.dataops.citation_acceptance import CitationAcceptanceExport, export_citation_acceptance
from nima.dataops.cpv_acceptance import CpvAcceptanceExport, export_cpv_acceptance
from nima.dataops.participation_acceptance import (
    ParticipationAcceptanceExport,
    export_participation_acceptance,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise AcceptanceError("acceptance_input")


def _event(name: str, **values: object) -> None:
    print(json.dumps({"component": "dataops.acceptance", "event": name, **values}), file=sys.stderr)


def run(argv: list[str]) -> int:
    _event("started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        operations = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
        exporters: dict[
            str,
            Callable[
                [str, Path, Path, Path],
                CitationAcceptanceExport
                | ParticipationAcceptanceExport
                | CpvAcceptanceExport
                | BuyerAcceptanceExport
                | ChangeAcceptanceExport,
            ],
        ] = {
            "assess-citations": export_citation_acceptance,
            "assess-participation": export_participation_acceptance,
            "assess-cpv": export_cpv_acceptance,
            "assess-buyer": export_buyer_acceptance,
            "assess-changes": export_change_acceptance,
        }
        for command in exporters:
            inspect = operations.add_parser(command, allow_abbrev=False)
            inspect.add_argument("--request", type=Path, required=True)
            inspect.add_argument("--report", type=Path, required=True)
            inspect.add_argument("--output-dir", type=Path, required=True)
        args = parser.parse_args(argv)
        exporter = exporters[args.operation]
        result = exporter(
            os.environ.get("NIMA_DATABASE_URL", ""), args.request, args.report, args.output_dir
        )
    except AcceptanceError as error:
        reason = str(error)
    except KeyboardInterrupt:
        reason = "acceptance_interrupted"
    except SystemExit as error:
        return 0 if error.code == 0 else 2
    else:
        _event("completed", decision=result.decision)
        print(json.dumps({"status": "complete", **asdict(result)}, allow_nan=False))
        return 0 if result.decision in {"ready", "limited"} else 3
    _event("failed", reason=reason)
    print(json.dumps({"status": "failed", "failure": reason}))
    return 130 if reason == "acceptance_interrupted" else 2 if reason == "acceptance_input" else 1
