"""Bounded public-source collection with machine-readable outcomes."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import NoReturn
from uuid import UUID

import httpx
import psycopg

from nima.graph.commands import configure as configure_graph
from nima.graph.commands import run as run_graph
from nima.identity import AssessmentError, ComparisonError
from nima.identity.registry_report import compare_run
from nima.identity.report import assess_run
from nima.identity.review_export import export_resolution
from nima.identity.review_inputs import read_report, read_request
from nima.identity.review_store import review as record_review
from nima.identity.review_types import ReviewError
from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.collector import RunError, collect
from nima.ingestion.config import Limits, Query
from nima.ingestion.diavgeia_lookup import LookupSource
from nima.ingestion.diavgeia_lookup import lookup as lookup_decisions
from nima.ingestion.gemi import GemiRunError, validate_inputs
from nima.ingestion.gemi import collect as collect_gemi
from nima.ingestion.resume import resume
from nima.projections.worker import PROJECTION_VERSION, ProjectionFailure, drain
from nima.sources.diavgeia import (
    CONNECTOR_VERSION,
    DECISION_ENDPOINT,
    DOCUMENTATION_URL,
    LICENSE,
    DiavgeiaAdapter,
    DiavgeiaQuery,
    InvalidDecision,
    decision_summary,
    decision_url,
)
from nima.sources.diavgeia_commitments import CommitmentAdapter, CommitmentQuery
from nima.storage.gemi import IMPORT_VERSION
from nima.storage.gemi import import_run as import_gemi
from nima.storage.gemi_archive import ImportFailure
from nima.storage.postgres import CheckpointError, MigrationError, migrate
from nima.storage.runs import inspect_run


def _date(text: str) -> date:
    try:
        parsed = date.fromisoformat(text)
        if parsed.isoformat() == text:
            return parsed
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Use an explicit YYYY-MM-DD date")


class _ComparisonParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("configuration")


def _parser(*, comparison: bool = False) -> argparse.ArgumentParser:
    parser_type = _ComparisonParser if comparison else argparse.ArgumentParser
    parser = parser_type(prog="python -m nima")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("evidence", help="Offline manual evidence intake and verification")
    commands.add_parser("analytics", help="Offline private supplier/buyer readouts")
    commands.add_parser("metadata", help="Query reported market metadata offline")
    commands.add_parser("dataops", help="Selected-run health and explicit validation history")
    commands.add_parser("archive", help="Offline committed-page integrity checks")
    configure_graph(commands.add_parser("graph", help="Offline private investigation graph"))
    refresh = commands.add_parser("refresh").add_subparsers(dest="operation", required=True)
    create = refresh.add_parser("create").add_subparsers(dest="source", required=True)
    policy = create.add_parser("kimdis")
    policy.add_argument("--policy-id", type=UUID, required=True)
    policy.add_argument("--start-date", type=_date, required=True)
    policy.add_argument("--buyer-id", action="append", required=True)
    for operation in ("plan", "show", "enable", "pause", "tick", "recover", "retire", "supersede"):
        command = refresh.add_parser(operation)
        command.add_argument("policy_id", type=UUID)
        if operation == "plan":
            command.add_argument("--as-of", type=_date, required=True)
        elif operation == "recover":
            command.add_argument("--request-id", type=UUID, required=True)
        elif operation == "retire":
            from nima.storage.refresh_lifecycle import REASONS

            command.add_argument("--reason", choices=REASONS, required=True)
        elif operation == "supersede":
            command.add_argument("--successor-id", type=UUID, required=True)
            command.add_argument("--authorize-new-budgets", action="store_true", required=True)
    workflows = commands.add_parser("workflows").add_subparsers(dest="operation", required=True)
    submit = workflows.add_parser("submit", help="Persist and dispatch one explicit local workflow")
    submit.add_argument("source", choices=["kimdis"])
    submit.add_argument("--request-id", type=UUID, required=True)
    submit.add_argument("--from-date", type=_date, required=True)
    submit.add_argument("--to-date", type=_date, required=True)
    submit.add_argument("--buyer-id", action="append", default=[])
    for operation in ("dispatch", "show"):
        workflows.add_parser(operation).add_argument("request_id", type=UUID)
    registry = commands.add_parser("gemi").add_subparsers(dest="operation", required=True)
    archived = registry.add_parser(
        "import", help="Verify and persist one completed archive offline"
    )
    archived.add_argument("run_id", type=UUID)
    archived.add_argument("--archive-dir", type=Path, required=True)
    identities = commands.add_parser("identities").add_subparsers(dest="operation", required=True)
    assess = identities.add_parser("assess", help="Assess one projected run offline")
    assess.add_argument("run_id", type=UUID)
    assess.add_argument("--projection-version", required=True)
    assess.add_argument("--output-dir", type=Path, required=True)
    assess.add_argument("--max-mentions", type=int, default=10000)
    compare = identities.add_parser("compare", help="Compare reported identifiers offline")
    compare.add_argument("run_id", type=UUID)
    compare.add_argument("--gemi-import", action="append", type=UUID, required=True)
    compare.add_argument("--projection-version", required=True)
    compare.add_argument("--output-dir", type=Path, required=True)
    compare.add_argument("--max-mentions", type=int, default=10000)
    review = identities.add_parser("review", help="Record or replay one explicit private review")
    review.add_argument("request_id", type=UUID)
    review.add_argument("--request-file", type=Path, required=True)
    review.add_argument(
        "--report-file",
        type=Path,
        help="Comparison file for new accept/reject; omit for revoke or committed replay",
    )
    resolution = identities.add_parser(
        "resolution", help="Export one private reviewed-resolution snapshot"
    )
    resolution.add_argument("--report-file", type=Path, required=True)
    resolution.add_argument("--output-dir", type=Path, required=True)
    resolution.add_argument("--max-events", type=int, default=10000)
    project = commands.add_parser("outbox").add_subparsers(dest="operation", required=True)
    project.add_parser(
        "project", help="Project reported participation in one bounded batch"
    ).add_argument("--max-events", type=int, default=100)
    ingest = commands.add_parser("ingest")
    database = commands.add_parser("db").add_subparsers(dest="operation", required=True)
    database.add_parser("migrate", help="Explicitly apply database migrations")
    runs = commands.add_parser("runs").add_subparsers(dest="operation", required=True)
    for operation, help_text in (
        ("show", "Inspect durable counts; worker liveness is unknown"),
        ("resume", "Resume with original options and source verification"),
    ):
        runs.add_parser(operation, help=help_text).add_argument("run_id", type=UUID)
    sources = ingest.add_subparsers(dest="source", required=True)
    gemi = sources.add_parser("gemi", help="Look up explicit GEMI numbers into a private archive")
    gemi.add_argument("--gemi-id", action="append", required=True)
    gemi.add_argument("--archive-dir", type=Path, required=True)
    diavgeia = sources.add_parser(
        "diavgeia",
        help="Collect Diavgeia decisions of one type, one organisation and one window of 30 days",
    )
    diavgeia.add_argument("--database", action="store_true", help="Persist via NIMA_DATABASE_URL")
    diavgeia.add_argument(
        "--decision-type",
        choices=("award", "commitment"),
        default="award",
        help="award (Δ.2.2, default) or commitment (Β.1.3)",
    )
    diavgeia.add_argument("--organization", required=True)
    diavgeia.add_argument("--from-date", type=_date, required=True)
    diavgeia.add_argument("--to-date", type=_date, required=True)
    diavgeia.add_argument("--archive-dir", type=Path, required=True)
    decisions = sources.add_parser(
        "diavgeia-decisions",
        help="Look up the decision type of 1 to 15 explicit Diavgeia ADAs; counts only",
    )
    decisions.add_argument("--ada", action="append", required=True)
    decisions.add_argument("--archive-dir", type=Path, required=True)
    kimdis = sources.add_parser(
        "kimdis",
        help="Collect one explicit KIMDIS date window; no automatic resume",
    )
    kimdis.add_argument("--database", action="store_true", help="Persist via NIMA_DATABASE_URL")
    kimdis.add_argument("--from-date", type=_date, required=True)
    kimdis.add_argument("--to-date", type=_date, required=True)
    kimdis.add_argument("--archive-dir", type=Path, required=True)
    kimdis.add_argument(
        "--buyer-id", action="append", default=[], help="Repeat for multiple buyers"
    )
    kimdis.add_argument("--max-pages", type=int, default=100)
    kimdis.add_argument("--max-attempts", type=int, default=3, help="Attempts per page")
    kimdis.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    kimdis.add_argument("--requests-per-minute", type=float, default=20)
    kimdis.add_argument("--request-timeout", type=float, default=20, help="HTTP inactivity seconds")
    kimdis.add_argument(
        "--run-timeout", type=float, default=300, help="Cooperative run budget seconds"
    )
    kimdis.add_argument("--max-retry-delay", type=float, default=60)
    return parser


_DIAVGEIA_DECISIONS = LookupSource(
    url_for=decision_url,
    summarize=decision_summary,
    invalid=InvalidDecision,
    manifest={
        "connector_version": CONNECTOR_VERSION,
        "endpoint": DECISION_ENDPOINT,
        "source": DOCUMENTATION_URL,
        "license": LICENSE,
    },
)


def _failure(code: str, *, run_id: str | None = None) -> None:
    print(
        json.dumps(
            {
                **({"run_id": run_id} if run_id is not None else {}),
                "status": "failed",
                "failure": code,
                "collection_complete": False,
                "normalization_complete": False,
            }
        )
    )


def _database_url() -> str:
    dsn = os.environ.get("NIMA_DATABASE_URL", "")
    if not dsn.strip():
        raise ValueError("NIMA_DATABASE_URL is required")
    return dsn


def _import_gemi(run_id: UUID, archive_root: Path) -> int:
    code = 0
    try:
        result = asdict(import_gemi(_database_url(), archive_root, run_id))
    except (ImportFailure, KeyboardInterrupt, ValueError) as exc:
        if isinstance(exc, ImportFailure):
            reason, code = exc.reason, 1
        elif isinstance(exc, KeyboardInterrupt):
            reason, code = "interrupted", 130
        else:
            reason, code = "configuration", 2
        result = {
            "run_id": run_id.hex,
            "import_version": IMPORT_VERSION,
            "status": "failed",
            "failure": reason,
        }
    print(json.dumps(result, allow_nan=False))
    return code


def _compare(args: argparse.Namespace) -> int:
    code = 0
    try:
        result = compare_run(
            _database_url(),
            args.run_id,
            args.gemi_import,
            args.projection_version,
            args.output_dir,
            max_mentions=args.max_mentions,
        )
    except (AssessmentError, ComparisonError) as exc:
        result, code = {"status": "failed", "failure": exc.reason}, 1
    except MigrationError:
        result, code = {"status": "failed", "failure": "database_schema"}, 1
    except psycopg.Error:
        result, code = {"status": "failed", "failure": "database"}, 1
    except OSError:
        result, code = {"status": "failed", "failure": "output_io"}, 1
    except ValueError:
        result, code = {"status": "failed", "failure": "configuration"}, 2
    except KeyboardInterrupt:
        result, code = {"status": "failed", "failure": "interrupted"}, 130
    print(json.dumps(result, allow_nan=False))
    return code


def _reviewed_identity(args: argparse.Namespace) -> int:
    code = 0
    try:
        if args.operation == "review":
            request = read_request(args.request_id, args.request_file)
            report = (
                read_report(args.report_file, expected_sha256=request.report_sha256)
                if request.operation != "revoke" and args.report_file is not None
                else None
            )
            ack = record_review(_database_url(), request, report=report)
            result: dict[str, object] = {
                "status": "committed",
                "request_id": str(ack.event_id),
                "event_id": str(ack.event_id),
                "entity_id": str(ack.entity_id) if ack.entity_id else None,
                "subject_revision": ack.subject_revision,
                "operation": ack.operation,
                "replayed": ack.replayed,
                "attribution_assurance": ack.attribution_assurance,
            }
        else:
            if not 1 <= args.max_events <= 10000:
                raise ValueError("configuration")
            report = read_report(args.report_file)
            result = export_resolution(
                _database_url(), report, args.output_dir, max_events=args.max_events
            )
    except ReviewError as error:
        result = {"status": "failed", "failure": error.reason}
        code = 2 if error.reason == "review_input" else 1
    except MigrationError:
        result, code = {"status": "failed", "failure": "review_schema"}, 1
    except psycopg.Error:
        result, code = {"status": "failed", "failure": "review_database"}, 1
    except OSError:
        result, code = (
            {
                "status": "failed",
                "failure": "review_output" if args.operation == "resolution" else "review_input_io",
            },
            1,
        )
    except ValueError:
        result, code = {"status": "failed", "failure": "configuration"}, 2
    except KeyboardInterrupt:
        result, code = {"status": "failed", "failure": "interrupted"}, 130
    print(json.dumps(result, allow_nan=False))
    return code


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "dataops":
        from nima.dataops.cli import run as dataops_run

        return dataops_run(arguments[1:])
    if arguments and arguments[0] == "metadata":
        from nima.metadata.cli import run as metadata_run

        return metadata_run(arguments[1:])
    if arguments and arguments[0] == "archive":
        from nima.dataops.archive import run as archive_run

        return archive_run(arguments[1:])
    if arguments and arguments[0] == "analytics":
        from nima.analytics.commands import run as analytics_run

        return analytics_run(arguments[1:])
    if arguments and arguments[0] == "evidence":
        from nima.evidence.cli import run as evidence_run

        return evidence_run(arguments[1:])
    private_graph = bool(arguments and arguments[0] == "graph")
    try:
        private_identity = bool(
            arguments and arguments[0] == "identities" and arguments[1:2] != ["assess"]
        )
        args = _parser(comparison=private_identity or private_graph).parse_args(arguments)
    except ValueError:
        reason = "graph_configuration" if private_graph else "configuration"
        print(json.dumps({"status": "failed", "failure": reason}))
        return 2
    if args.command == "graph":
        return run_graph(args)
    if args.command == "identities" and args.operation == "compare":
        return _compare(args)
    if args.command == "identities" and args.operation in {"review", "resolution"}:
        return _reviewed_identity(args)
    if args.command == "refresh":
        from nima.orchestration.refresh_cli import run as refresh_run

        return refresh_run(
            args.operation,
            args.policy_id,
            start=getattr(args, "start_date", None),
            buyers=tuple(getattr(args, "buyer_id", [])),
            as_of=getattr(args, "as_of", None),
            request=getattr(args, "request_id", None),
            reason=getattr(args, "reason", None),
            successor=getattr(args, "successor_id", None),
            authorize_new_budgets=getattr(args, "authorize_new_budgets", False),
        )
    if args.command == "workflows":
        from nima.orchestration.cli import run

        return run(
            args.operation,
            args.request_id,
            start=getattr(args, "from_date", None),
            end=getattr(args, "to_date", None),
            buyers=tuple(getattr(args, "buyer_id", [])),
        )
    if args.command == "gemi":
        return _import_gemi(args.run_id, args.archive_dir)
    try:
        if args.command == "identities":
            print(
                json.dumps(
                    assess_run(
                        _database_url(),
                        args.run_id,
                        args.projection_version,
                        args.output_dir,
                        max_mentions=args.max_mentions,
                    )
                )
            )
            return 0
        if args.command == "outbox":
            print(json.dumps(drain(_database_url(), max_events=args.max_events)))
            return 0
        if args.command == "db":
            migrate(_database_url())
            print(json.dumps({"status": "migrated"}))
            return 0
        if args.command == "runs":
            if args.operation == "show":
                print(json.dumps(inspect_run(_database_url(), args.run_id), ensure_ascii=False))
                return 0
            resume_dsn = _database_url()
            with httpx.Client() as client:
                summary = resume(resume_dsn, args.run_id, client=client)
            print(json.dumps(asdict(summary), ensure_ascii=False, allow_nan=False))
            return {"complete": 0, "quarantined": 3, "interrupted": 130}.get(summary.status, 1)
        if args.source == "gemi":
            key = os.environ.get("NIMA_GEMI_API_KEY", "")
            ids = tuple(args.gemi_id)
            validate_inputs(ids, key)
            with httpx.Client() as client:
                gemi_summary = collect_gemi(ids, args.archive_dir, api_key=key, client=client)
            print(json.dumps(asdict(gemi_summary), allow_nan=False))
            return {"complete": 0, "quarantined": 3, "interrupted": 130}.get(gemi_summary.status, 1)
        if args.source == "diavgeia-decisions":
            lookup_ids = tuple(args.ada)
            for ada in lookup_ids:
                decision_url(ada)
            with httpx.Client() as client:
                found = lookup_decisions(
                    lookup_ids, args.archive_dir, source=_DIAVGEIA_DECISIONS, client=client
                )
            print(json.dumps(asdict(found), ensure_ascii=False, allow_nan=False))
            return {"complete": 0, "quarantined": 3, "interrupted": 130}.get(found.status, 1)
        query: Query | None
        adapter: DiavgeiaAdapter | None
        if args.source == "diavgeia":
            query, limits = None, Limits()
            adapter_type, query_type = (
                (CommitmentAdapter, CommitmentQuery)
                if args.decision_type == "commitment"
                else (DiavgeiaAdapter, DiavgeiaQuery)
            )
            adapter = adapter_type(
                query_type(args.organization, args.from_date.isoformat(), args.to_date.isoformat())
            )
        else:
            adapter = None
            query = Query(args.from_date, args.to_date, tuple(args.buyer_id))
            limits = Limits(
                args.max_pages,
                args.max_attempts,
                args.max_bytes,
                args.requests_per_minute,
                args.request_timeout,
                args.run_timeout,
                args.max_retry_delay,
            )
        dsn = _database_url() if args.database else None
        archive = Archive(args.archive_dir)
        with httpx.Client() as client:
            summary = collect(
                query, limits, archive, client=client, database_dsn=dsn, adapter=adapter
            )
    except AssessmentError as exc:
        print(json.dumps({"status": "failed", "failure": exc.reason}))
        return 1
    except ProjectionFailure as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "projection_version": PROJECTION_VERSION,
                    "processed_events": exc.processed,
                    "event_id": exc.event_id,
                    "failure": exc.reason,
                }
            )
        )
        return 1
    except GemiRunError as exc:
        _failure(exc.reason, run_id=exc.run_id)
        return 1
    except RunError as exc:
        _failure(exc.reason, run_id=exc.run_id)
        return 1
    except MigrationError:
        _failure("database_schema")
        return 1
    except CheckpointError:
        _failure("run_unavailable")
        return 1
    except psycopg.Error:
        _failure("database")
        return 1
    except ArchiveError:
        _failure("archive_invalid")
        return 1
    except OSError:
        # Even failure to persist the final manifest must prevent a successful exit.
        _failure("archive_io")
        return 1
    except ValueError:
        _failure("configuration")
        return 2
    print(json.dumps(asdict(summary), ensure_ascii=False, allow_nan=False))
    return {"complete": 0, "quarantined": 3, "interrupted": 130}.get(summary.status, 1)


if __name__ == "__main__":
    raise SystemExit(main())
