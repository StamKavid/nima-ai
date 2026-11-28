"""Thin offline insight commands; stdout is a bounded result, stderr fixed stage events."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Never

from nima.insights.buyer_participation import InsightError, export_buyer_insight


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise InsightError("insight_input")


def _event(name: str, **values: object) -> None:
    print(
        json.dumps({"component": "insights.buyer_participation", "event": name, **values}),
        file=sys.stderr,
    )


def run(argv: list[str]) -> int:
    _event("started")
    try:
        parser = _Parser(prog="python -m nima insights", allow_abbrev=False)
        commands = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
        buyer = commands.add_parser("buyer-participation", allow_abbrev=False)
        buyer.add_argument("--request", type=Path, required=True)
        buyer.add_argument("--report", type=Path, required=True)
        buyer.add_argument("--output-dir", type=Path, required=True)
        args = parser.parse_args(argv)
        result = export_buyer_insight(
            os.environ.get("NIMA_DATABASE_URL", ""), args.request, args.report, args.output_dir
        )
    except InsightError as error:
        reason = str(error)
    except KeyboardInterrupt:
        reason = "insight_interrupted"
    except SystemExit as error:
        return 0 if error.code == 0 else 2
    else:
        _event("completed", status=result.status)
        print(json.dumps(asdict(result), allow_nan=False))
        return 0 if result.status == "answered" else 3
    _event("failed", reason=reason)
    print(json.dumps({"status": "failed", "failure": reason}))
    return 130 if reason == "insight_interrupted" else 2 if reason == "insight_input" else 1
