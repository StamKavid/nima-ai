"""Bounded public-source collection with machine-readable outcomes."""

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path
from uuid import UUID

import httpx
import psycopg

from nima.identity import AssessmentError
from nima.identity.report import assess_run
from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.collector import RunError, collect
from nima.ingestion.config import Limits, Query
from nima.ingestion.gemi import GemiRunError, validate_inputs
from nima.ingestion.gemi import collect as collect_gemi
from nima.ingestion.resume import resume
from nima.projections.worker import PROJECTION_VERSION, ProjectionFailure, drain
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m nima")
    commands = parser.add_subparsers(dest="command", required=True)
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
            summary = collect(query, limits, archive, client=client, database_dsn=dsn)
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
