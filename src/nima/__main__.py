"""Bounded public-source collection with machine-readable outcomes."""

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import httpx

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits, Query


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
    ingest = parser.add_subparsers(dest="command", required=True).add_parser("ingest")
    kimdis = ingest.add_subparsers(dest="source", required=True).add_parser(
        "kimdis",
        help="Collect one explicit KIMDIS date window; no automatic resume",
    )
    kimdis.add_argument("--from-date", type=_date, required=True)
    kimdis.add_argument("--to-date", type=_date, required=True)
    kimdis.add_argument("--archive-dir", type=Path, required=True)
    kimdis.add_argument(
        "--buyer-id", action="append", default=[], help="Repeat for multiple buyers"
    )
    kimdis.add_argument("--max-pages", type=int, default=100)
    kimdis.add_argument("--max-attempts", type=int, default=3, help="Attempts per page")
    kimdis.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    kimdis.add_argument("--requests-per-minute", type=float, default=60)
    kimdis.add_argument("--request-timeout", type=float, default=20, help="HTTP inactivity seconds")
    kimdis.add_argument(
        "--run-timeout", type=float, default=300, help="Cooperative run budget seconds"
    )
    kimdis.add_argument("--max-retry-delay", type=float, default=60)
    return parser


def _failure(code: str) -> None:
    print(
        json.dumps(
            {
                "status": "failed",
                "failure": code,
                "collection_complete": False,
                "normalization_complete": False,
            }
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
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
    except ValueError:
        _failure("configuration")
        return 2
    try:
        archive = Archive(args.archive_dir)
        with httpx.Client() as client:
            summary = collect(query, limits, archive, client=client)
    except ArchiveError:
        _failure("archive_invalid")
        return 1
    except OSError:
        # Even failure to persist the final manifest must prevent a successful exit.
        _failure("archive_io")
        return 1
    print(json.dumps(asdict(summary), ensure_ascii=False, allow_nan=False))
    return {"complete": 0, "quarantined": 3, "interrupted": 130}.get(summary.status, 1)


if __name__ == "__main__":
    raise SystemExit(main())
