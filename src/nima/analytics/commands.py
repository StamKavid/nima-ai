"""Offline analytics routing with fixed, source-value-free terminal results."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

import psycopg

from nima.analytics.export import export_readout
from nima.analytics.result import ReadoutError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("analytics_configuration")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m nima analytics", allow_abbrev=False)
    operations = parser.add_subparsers(dest="operation", required=True)
    readout = operations.add_parser(
        "supplier-buyers",
        help="Publish a private cited captured-contract count",
        allow_abbrev=False,
    )
    readout.add_argument("--request", type=Path, required=True, help="Private explicit selection")
    readout.add_argument("--output-dir", type=Path, required=True, help="Private result directory")
    return parser


def _failure(reason: str) -> int:
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    if reason in {"analytics_configuration", "analytics_input"}:
        return 2
    return 130 if reason == "analytics_interrupted" else 1


def run(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if not dsn.strip():
            raise ValueError("analytics_configuration")
        result = export_readout(dsn, args.request, args.output_dir)
    except ReadoutError as error:
        return _failure(error.reason)
    except psycopg.Error:
        return _failure("analytics_database")
    except OSError:
        return _failure("analytics_output")
    except ValueError:
        return _failure("analytics_configuration")
    except KeyboardInterrupt:
        return _failure("analytics_interrupted")
    print(json.dumps({"status": "complete", **asdict(result)}, allow_nan=False))
    return 0
