"""Offline analytics routing with fixed, source-value-free terminal results."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, NoReturn

import psycopg

from nima.analytics.buyer_readout import export_buyer_readout
from nima.analytics.buyer_view import export_buyer_evidence_view
from nima.analytics.buyer_view_request import ViewError
from nima.analytics.change_readout import export_change_readout
from nima.analytics.citation_readout import export_citation_readout
from nima.analytics.cpv_readout import export_cpv_readout
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
    cpv = operations.add_parser(
        "cpv-period",
        help="Publish a private cited captured-record count by CPV code and month",
        allow_abbrev=False,
    )
    cpv.add_argument("--request", type=Path, required=True, help="Private explicit selection")
    cpv.add_argument("--output-dir", type=Path, required=True, help="Private result directory")
    buyer = operations.add_parser(
        "buyer-concentration",
        help="Publish a private cited buyer-to-supplier record concentration",
        allow_abbrev=False,
    )
    buyer.add_argument("--request", type=Path, required=True, help="Private explicit selection")
    buyer.add_argument("--output-dir", type=Path, required=True, help="Private result directory")
    view = operations.add_parser(
        "buyer-evidence-view",
        help="Export a private offline buyer-to-original HTML view",
        allow_abbrev=False,
    )
    view.add_argument(
        "--config", type=Path, required=True, help="Private saved-cohort configuration"
    )
    view.add_argument("--output-dir", type=Path, required=True, help="Private HTML directory")
    change = operations.add_parser(
        "observed-change",
        help="Publish a private cited comparison of two captures of one query",
        allow_abbrev=False,
    )
    change.add_argument("--request", type=Path, required=True, help="Private explicit selection")
    change.add_argument("--output-dir", type=Path, required=True, help="Private result directory")
    citations = operations.add_parser(
        "source-citations",
        help="Publish verified explicit KIMDIS–Diavgeia citations",
        allow_abbrev=False,
    )
    citations.add_argument("--request", type=Path, required=True, help="Private explicit selection")
    citations.add_argument(
        "--output-dir", type=Path, required=True, help="Private result directory"
    )
    return parser


def _failure(reason: str) -> int:
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    if reason in {"analytics_configuration", "analytics_input", "citation_input", "view_input"}:
        return 2
    return 130 if reason in {"analytics_interrupted", "view_interrupted"} else 1


def run(argv: list[str]) -> int:
    citation = argv[:1] == ["source-citations"]
    view = argv[:1] == ["buyer-evidence-view"]
    try:
        args = _parser().parse_args(argv)
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if not dsn.strip():
            raise ValueError("analytics_configuration")
        exporter = {
            "cpv-period": export_cpv_readout,
            "buyer-concentration": export_buyer_readout,
            "observed-change": export_change_readout,
            "source-citations": export_citation_readout,
        }.get(args.operation, export_readout)
        result: Any
        if view:
            result = export_buyer_evidence_view(dsn, args.config, args.output_dir)
        else:
            result = exporter(dsn, args.request, args.output_dir)
    except ViewError as error:
        return _failure(str(error))
    except ReadoutError as error:
        return _failure(error.reason)
    except psycopg.Error:
        return _failure(
            "view_database" if view else "citation_database" if citation else "analytics_database"
        )
    except OSError:
        return _failure(
            "view_output" if view else "citation_output" if citation else "analytics_output"
        )
    except ValueError:
        return _failure(
            "view_input" if view else "citation_input" if citation else "analytics_configuration"
        )
    except KeyboardInterrupt:
        if view:
            return _failure("view_interrupted")
        if citation:
            _failure("citation_output")
            return 130
        return _failure("analytics_interrupted")
    except SystemExit as error:
        if not view:
            raise
        return 0 if error.code == 0 else 2
    print(json.dumps({"status": "complete", **asdict(result)}, allow_nan=False))
    return 0
