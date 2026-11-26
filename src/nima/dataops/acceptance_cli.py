"""One offline acceptance command with fixed, private-safe terminal results."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Never

from nima.dataops.citation_acceptance import CitationAcceptanceError, export_citation_acceptance


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CitationAcceptanceError("acceptance_input")


def _event(name: str, **values: object) -> None:
    print(json.dumps({"component": "dataops.acceptance", "event": name, **values}), file=sys.stderr)


def run(argv: list[str]) -> int:
    _event("started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        operations = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
        inspect = operations.add_parser("assess-citations", allow_abbrev=False)
        inspect.add_argument("--request", type=Path, required=True)
        inspect.add_argument("--report", type=Path, required=True)
        inspect.add_argument("--output-dir", type=Path, required=True)
        args = parser.parse_args(argv)
        result = export_citation_acceptance(
            os.environ.get("NIMA_DATABASE_URL", ""), args.request, args.report, args.output_dir
        )
    except CitationAcceptanceError as error:
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
