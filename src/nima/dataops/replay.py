"""Reprocess committed originals into a private dataset without creating observations."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

import psycopg

from nima.graph.pilot_archive import (
    MAX_OBJECT_BYTES,
    MAX_OBJECTS,
    MAX_TOTAL_BYTES,
    ArchiveBinding,
    PilotArchiveError,
    RawReference,
    recover,
)
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.sources.base import SourceAdapter, SourcePageError
from nima.sources.registry import default_adapter
from nima.storage.connection import connect
from nima.storage.postgres import MigrationError, validate_schema

MAX_RECORDS = 5000
# The pilot-archive recovery is typed by archive layout, not by source. Every adapter that
# writes through the page store shares the layout it labels "kimdis"; widening it is later.
PAGE_ARCHIVE: Literal["kimdis"] = "kimdis"


class ReplayError(ValueError):
    """Fixed private-safe failure reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Replay:
    artifact_sha256: str
    page_count: int
    record_count: int
    normalized_count: int
    quarantined_count: int


@dataclass(frozen=True)
class CapturedPage:
    number: int
    raw_sha256: str
    byte_length: int
    observed_at: str
    record_count: int


def _snapshot(
    dsn: str, run_id: UUID, adapter: SourceAdapter
) -> tuple[dict[str, object], tuple[CapturedPage, ...]]:
    with connect(dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        validate_schema(connection)
        row = connection.execute(
            """SELECT status,connector_version,normalizer_version,next_page,
            total_records,total_pages,page_size,query FROM nima.ingest_runs WHERE run_id=%s""",
            (run_id,),
        ).fetchone()
        if row is None:
            raise ReplayError("replay_scope")
        if row[1] != adapter.connector_version:
            raise ReplayError("replay_source")
        if not isinstance(row[2], str) or not row[2].strip():
            raise ReplayError("replay_scope")
        count = connection.execute(
            "SELECT count(*) FROM nima.run_pages WHERE run_id=%s", (run_id,)
        ).fetchone()
        if count is None or cast(int, count[0]) > MAX_OBJECTS:
            raise ReplayError("replay_limit")
        if count[0] != row[3]:
            raise ReplayError("replay_scope")
        rows = connection.execute(
            """SELECT p.page_number,p.raw_sha256,b.byte_length,p.observed_at,p.record_count
            FROM nima.run_pages p LEFT JOIN nima.raw_objects b ON b.sha256=p.raw_sha256
            WHERE p.run_id=%s ORDER BY p.page_number""",
            (run_id,),
        ).fetchall()
        if [r[0] for r in rows] != list(range(cast(int, count[0]))):
            raise ReplayError("replay_scope")
        pages = []
        for number, digest, size, observed, records in rows:
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or type(size) is not int
                or size < 0
                or type(records) is not int
                or records < 0
                or not isinstance(observed, datetime)
                or observed.utcoffset() is None
            ):
                raise ReplayError("replay_scope")
            if size > MAX_OBJECT_BYTES:
                raise ReplayError("replay_limit")
            pages.append(
                CapturedPage(
                    cast(int, number), digest, size, observed.astimezone(UTC).isoformat(), records
                )
            )
        if (
            sum(p.record_count for p in pages) > MAX_RECORDS
            or sum({p.raw_sha256: p.byte_length for p in pages}.values()) > MAX_TOTAL_BYTES
        ):
            raise ReplayError("replay_limit")
        names = (
            "status",
            "connector_version",
            "normalizer_version",
            "next_page",
            "total_records",
            "total_pages",
            "page_size",
            "query",
        )
        return {"run_id": str(run_id), **dict(zip(names, row, strict=True))}, tuple(pages)


def _dataset(
    run: dict[str, object],
    pages: tuple[CapturedPage, ...],
    bodies: dict[str, bytes],
    adapter: SourceAdapter,
) -> tuple[dict[str, object], int, int]:
    results = []
    normalized_count = quarantined_count = 0
    for stored in pages:
        page = adapter.normalize_page(bodies[stored.raw_sha256])
        if (
            page.number != stored.number
            or page.record_count != stored.record_count
            or (page.total_records, page.total_pages, page.size)
            != (run["total_records"], run["total_pages"], run["page_size"])
        ):
            raise ReplayError("replay_scope")
        records: list[dict[str, object]] = []
        for record in page.records:
            records.append(
                {
                    "record_index": record.index,
                    "json_pointer": record.evidence_pointer,
                    "content_sha256": page.record_hashes[record.index],
                    "status": "normalized",
                    "normalized": dict(record.normalized),
                }
            )
        for issue in page.issues:
            records.append(
                {
                    "record_index": issue.index,
                    "json_pointer": issue.evidence_pointer,
                    "content_sha256": page.record_hashes[issue.index],
                    "status": "quarantined",
                    "reason": issue.reason,
                }
            )
        normalized_count += len(page.records)
        quarantined_count += len(page.issues)
        results.append(
            {
                "page_number": stored.number,
                "raw_sha256": stored.raw_sha256,
                "byte_length": stored.byte_length,
                "observed_at": stored.observed_at,
                "records": sorted(records, key=lambda r: cast(int, r["record_index"])),
            }
        )
    return (
        {
            "artifact_version": f"{adapter.name}-archive-replay-v1",
            "source": f"{adapter.name}.contract",
            "scope": "committed_pages_only",
            "source_run": run,
            "normalizer_version": adapter.normalizer_version,
            "pages": results,
        },
        normalized_count,
        quarantined_count,
    )


@dataclass(frozen=True)
class CapturedSource:
    """Frozen SQL metadata and hash-verified bytes; no open SQL handle or paths."""

    run: dict[str, object]
    pages: tuple[CapturedPage, ...]
    bodies: dict[str, bytes]


def read_capture(
    dsn: str, run_id: UUID, archive_root: Path, adapter: SourceAdapter | None = None
) -> CapturedSource:
    """Read one bounded committed capture for replay or independent projections."""
    source = adapter if adapter is not None else default_adapter()
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not isinstance(run_id, UUID)
        or not isinstance(archive_root, Path)
        or not archive_root.is_absolute()
        or any(part in {"..", ".git"} for part in archive_root.parts)
        or "\x00" in str(archive_root)
    ):
        raise ReplayError("replay_input")
    try:
        run, pages = _snapshot(dsn, run_id, source)
        if not pages:
            raise ReplayError("replay_empty")
        recovered = recover(
            tuple(RawReference(PAGE_ARCHIVE, run_id, p.raw_sha256) for p in pages),
            (ArchiveBinding(PAGE_ARCHIVE, run_id, archive_root),),
        )
        bodies = {obj.raw_sha256: obj.body for obj in recovered.objects}
        if {digest: len(raw) for digest, raw in bodies.items()} != {
            p.raw_sha256: p.byte_length for p in pages
        }:
            raise ReplayError("replay_evidence")
        return CapturedSource(run, pages, bodies)
    except MigrationError:
        raise ReplayError("replay_schema") from None
    except psycopg.Error:
        raise ReplayError("replay_database") from None
    except PilotArchiveError as error:
        raise ReplayError(
            "replay_limit" if error.reason == "pilot_limit" else "replay_evidence"
        ) from None
    except (OSError, SourcePageError):
        raise ReplayError("replay_evidence") from None


def prepare_replay(
    dsn: str,
    run_id: UUID,
    archive_root: Path,
    normalizer_version: str,
    adapter: SourceAdapter | None = None,
) -> tuple[bytes, Replay]:
    """Freeze and verify a canonical replay without publishing or writing SQL."""
    source = adapter if adapter is not None else default_adapter()
    if not isinstance(normalizer_version, str) or normalizer_version != source.normalizer_version:
        raise ReplayError("replay_version")
    capture = read_capture(dsn, run_id, archive_root, source)
    try:
        value, normalized, quarantined = _dataset(
            capture.run, capture.pages, capture.bodies, source
        )
    except SourcePageError:
        raise ReplayError("replay_evidence") from None
    pages = capture.pages
    try:
        body = encode(value)
        digest = hashlib.sha256(body).hexdigest()
    except AssessmentError as error:
        raise ReplayError(
            "replay_limit" if error.reason == "assessment_limit" else "replay_output"
        ) from None
    except OSError:
        raise ReplayError("replay_output") from None
    return body, Replay(digest, len(pages), normalized + quarantined, normalized, quarantined)


def replay_run(
    dsn: str, run_id: UUID, archive_root: Path, output: Path, normalizer_version: str
) -> Replay:
    """Publish the same prepared bytes used by explicit SQL replay promotion."""
    if (
        not isinstance(output, Path)
        or not output.is_absolute()
        or any(part in {"..", ".git"} for part in output.parts)
        or "\x00" in str(output)
        or (isinstance(archive_root, Path) and output.is_relative_to(archive_root))
    ):
        raise ReplayError("replay_input")
    body, result = prepare_replay(dsn, run_id, archive_root, normalizer_version)
    try:
        publish(output, body)
    except AssessmentError:
        raise ReplayError("replay_output") from None
    except OSError:
        raise ReplayError("replay_output") from None
    return result
