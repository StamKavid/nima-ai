"""Offline graph command configuration and fixed, source-value-free outcomes."""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg

from nima.graph import GraphError
from nima.graph.export import export_graph
from nima.identity.review_inputs import read_report
from nima.identity.review_state import MAX_REVIEW_EVENTS
from nima.identity.review_types import ReviewError
from nima.storage.postgres import MigrationError


def configure(parser: argparse.ArgumentParser) -> None:
    parser.allow_abbrev = False
    operations = parser.add_subparsers(dest="operation", required=True)
    snapshot = operations.add_parser(
        "snapshot",
        help="Export one private graph from a frozen comparison selection",
        allow_abbrev=False,
    )
    snapshot.add_argument(
        "--report-file", type=Path, required=True, help="Private registry-comparison report"
    )
    snapshot.add_argument(
        "--output-dir", type=Path, required=True, help="Owner-only artifact directory"
    )
    snapshot.add_argument("--entity-id", type=UUID, help="Focus within selected review history")
    snapshot.add_argument(
        "--max-events",
        type=int,
        default=MAX_REVIEW_EVENTS,
        help=f"Selected review-event limit (1..{MAX_REVIEW_EVENTS}; default: {MAX_REVIEW_EVENTS})",
    )


def _failure(reason: str) -> int:
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    if reason in {"graph_configuration", "graph_input"}:
        return 2
    return 130 if reason == "graph_interrupted" else 1


def run(args: argparse.Namespace) -> int:
    try:
        if type(args.max_events) is not int or not 1 <= args.max_events <= MAX_REVIEW_EVENTS:
            raise ValueError("graph_configuration")
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if not dsn.strip():
            raise ValueError("graph_configuration")
        report = read_report(args.report_file)
        result = export_graph(
            dsn, report, args.output_dir, entity_id=args.entity_id, max_events=args.max_events
        )
    except GraphError as error:
        return _failure(error.reason)
    except ReviewError as error:
        return _failure(
            {
                "review_input": "graph_input",
                "review_input_io": "graph_input_io",
                "review_limit": "graph_limit",
            }.get(error.reason, "graph_evidence")
        )
    except MigrationError:
        return _failure("graph_schema")
    except psycopg.Error:
        return _failure("graph_database")
    except OSError:
        return _failure("graph_output")
    except ValueError:
        return _failure("graph_configuration")
    except KeyboardInterrupt:
        return _failure("graph_interrupted")
    print(json.dumps(result, allow_nan=False))
    return 0
