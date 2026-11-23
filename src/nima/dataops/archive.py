"""Verify one frozen set of committed KIMDIS page bodies, without repair or HTTP."""

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn, cast
from uuid import UUID

import psycopg

from nima.dataops import promotion
from nima.dataops import replay as normalization
from nima.graph.pilot_archive import (
    MAX_OBJECT_BYTES,
    MAX_OBJECTS,
    MAX_TOTAL_BYTES,
    ArchiveBinding,
    PilotArchiveError,
    RawReference,
    recover,
)
from nima.sources.registry import adapter_for
from nima.storage.connection import connect
from nima.storage.postgres import MigrationError, validate_schema


class VerificationError(ValueError):
    """Fixed reasons only; no paths, source values or database driver details."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Verification:
    outcome: str
    scope: str
    run_status: str
    page_count: int
    object_count: int
    verified_bytes: int


def _snapshot(dsn: str, run_id: UUID) -> tuple[str, tuple[tuple[str, int], ...]]:
    with connect(dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        validate_schema(connection)
        run = connection.execute(
            "SELECT status,next_page FROM nima.ingest_runs WHERE run_id=%s", (run_id,)
        ).fetchone()
        if run is None:
            raise VerificationError("archive_scope")
        count = connection.execute(
            "SELECT count(*) FROM nima.run_pages WHERE run_id=%s", (run_id,)
        ).fetchone()
        if count is None or cast(int, count[0]) > MAX_OBJECTS:
            raise VerificationError("archive_limit")
        if count[0] != run[1]:
            raise VerificationError("archive_scope")
        rows = connection.execute(
            """SELECT p.page_number,p.raw_sha256,b.byte_length
            FROM nima.run_pages p LEFT JOIN nima.raw_objects b ON b.sha256=p.raw_sha256
            WHERE p.run_id=%s ORDER BY p.page_number""",
            (run_id,),
        ).fetchall()
        if [row[0] for row in rows] != list(range(cast(int, count[0]))):
            raise VerificationError("archive_scope")
        pages = []
        for _, digest, size in rows:
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or type(size) is not int
                or size < 0
            ):
                raise VerificationError("archive_scope")
            if size > MAX_OBJECT_BYTES:
                raise VerificationError("archive_limit")
            pages.append((digest, size))
        return cast(str, run[0]), tuple(pages)


def verify_run(dsn: str, run_id: UUID, archive_root: Path) -> Verification:
    """SQL closes before filesystem recovery; only committed-page locations count.

    A relocated archive is explicit operator input. No absolute stored path is
    required, and later commits are outside this frozen snapshot's scope.
    """
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not isinstance(run_id, UUID)
        or not isinstance(archive_root, Path)
        or not archive_root.is_absolute()
        or any(part in {"..", ".git"} for part in archive_root.parts)
        or "\x00" in str(archive_root)
    ):
        raise VerificationError("archive_input")
    try:
        status, pages = _snapshot(dsn, run_id)
        expected = dict(pages)
        if sum(expected.values()) > MAX_TOTAL_BYTES:
            raise VerificationError("archive_limit")
        if not pages:
            return Verification(
                "no_committed_pages", "kimdis_committed_pages_only", status, 0, 0, 0
            )
        result = recover(
            tuple(RawReference("kimdis", run_id, digest) for digest, _ in pages),
            (ArchiveBinding("kimdis", run_id, archive_root),),
        )
        if {obj.raw_sha256: len(obj.body) for obj in result.objects} != expected:
            raise VerificationError("archive_evidence")
        return Verification(
            "verified_committed_pages",
            "kimdis_committed_pages_only",
            status,
            len(pages),
            len(result.objects),
            result.total_bytes,
        )
    except MigrationError:
        raise VerificationError("archive_schema") from None
    except psycopg.Error:
        raise VerificationError("archive_database") from None
    except PilotArchiveError as error:
        reason = "archive_limit" if error.reason == "pilot_limit" else "archive_evidence"
        raise VerificationError(reason) from None


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("archive_configuration")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m nima archive", allow_abbrev=False)
    commands = parser.add_subparsers(dest="operation", required=True)
    verify = commands.add_parser(
        "verify", help="Check committed SQL page bodies offline", allow_abbrev=False
    )
    verify.add_argument("--run-id", type=UUID, required=True)
    verify.add_argument("--archive-dir", type=Path, required=True)
    replay = commands.add_parser(
        "replay", help="Re-normalize committed originals into a private dataset", allow_abbrev=False
    )
    replay.add_argument("--run-id", type=UUID, required=True)
    replay.add_argument("--archive-dir", type=Path, required=True)
    replay.add_argument("--normalizer-version", required=True)
    replay.add_argument("--output-dir", type=Path, required=True)
    replay.add_argument("--source", default="kimdis")
    promote = commands.add_parser(
        "promote", help="Store a selected replay as derived SQL data", allow_abbrev=False
    )
    promote.add_argument("--run-id", type=UUID, required=True)
    promote.add_argument("--archive-dir", type=Path, required=True)
    promote.add_argument("--normalizer-version", required=True)
    promote.add_argument("--replay-sha256", required=True)
    promote.add_argument("--source", default="kimdis")
    return parser


def run(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if not dsn.strip():
            raise ValueError("archive_configuration")
        if args.operation == "promote":
            promoted = promotion.promote_run(
                dsn,
                args.run_id,
                args.archive_dir,
                args.normalizer_version,
                args.replay_sha256,
                adapter_for(args.source),
            )
            print(
                json.dumps({"status": "complete", "outcome": "promoted_replay", **asdict(promoted)})
            )
            return 0
        if args.operation == "replay":
            replay = normalization.replay_run(
                dsn,
                args.run_id,
                args.archive_dir,
                args.output_dir,
                args.normalizer_version,
                adapter_for(args.source),
            )
            summary = asdict(replay)
            del summary["artifact_sha256"]
            print(
                json.dumps({"status": "complete", "outcome": "replayed_committed_pages", **summary})
            )
            return 0
        result = verify_run(dsn, args.run_id, args.archive_dir)
    except (VerificationError, normalization.ReplayError, promotion.PromotionError) as error:
        reason = error.reason
    except OSError:
        reason = "archive_evidence"
    except ValueError:
        reason = "archive_configuration"
    except KeyboardInterrupt:
        reason = "archive_interrupted"
    else:
        print(json.dumps({"status": "complete", **asdict(result)}, allow_nan=False))
        return 3 if result.outcome == "no_committed_pages" else 0
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    if reason == "replay_empty":
        return 3
    if reason in {
        "archive_configuration",
        "archive_input",
        "replay_input",
        "replay_version",
        "promotion_input",
    }:
        return 2
    return 130 if reason == "archive_interrupted" else 1
