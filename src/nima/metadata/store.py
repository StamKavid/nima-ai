"""Explicit derived snapshots; cached SQL reads do not re-attest archived originals."""

import hashlib
import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.metadata.export import prepare_metadata
from nima.sources.metadata_extract import (
    VERSION,
    Assertion,
    MetadataError,
    select_assertions,
    validate_query,
)
from nima.storage.connection import connect
from nima.storage.postgres import MigrationError, validate_schema
from nima.storage.runs import run_lock_key


@dataclass(frozen=True)
class MetadataPromotion:
    record_count: int
    assertion_count: int
    reused: bool


def _selection(digest: str) -> None:
    if not isinstance(digest, str) or re.fullmatch("[0-9a-f]{64}", digest) is None:
        raise MetadataError("metadata_input")


def promote_metadata(
    dsn: str,
    source: str,
    run_id: UUID,
    archive_root: Path,
    snapshot_sha256: str,
) -> MetadataPromotion:
    """Recompute selected canonical bytes; never ingest a caller's metadata file."""
    _selection(snapshot_sha256)
    raw, prepared = prepare_metadata(source, run_id, archive_root, dsn=dsn)
    if prepared.artifact_sha256 != snapshot_sha256:
        raise MetadataError("metadata_selection")
    document = cast(dict[str, object], json.loads(raw))
    capture = cast(dict[str, object], document["capture"])
    if capture["status"] not in ("complete", "quarantined"):
        raise MetadataError("metadata_capture")
    expected = (
        source,
        run_id if source == "kimdis" else None,
        run_id if source == "gemi" else None,
        document,
    )
    try:
        with connect(dsn) as c, c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            validate_schema(c)
            if source == "kimdis":
                if c.execute(
                    "SELECT pg_try_advisory_xact_lock_shared(%s)", (run_lock_key(run_id),)
                ).fetchone() != (True,):
                    raise MetadataError("metadata_busy")
                row = c.execute(
                    """SELECT jsonb_build_object(
                    'run_id',run_id::text,'status',status,'connector_version',connector_version,
                    'normalizer_version',normalizer_version,'next_page',next_page,
                    'total_records',total_records,'total_pages',total_pages,'page_size',page_size,
                    'query',query) FROM nima.ingest_runs WHERE run_id=%s""",
                    (run_id,),
                ).fetchone()
                if row is None or row[0] != capture:
                    raise MetadataError("metadata_scope")
            else:
                row = c.execute(
                    "SELECT manifest_sha256,normalizer_version,source_url,license,publisher "
                    "FROM nima.gemi_imports WHERE run_id=%s",
                    (run_id,),
                ).fetchone()
                if row != tuple(
                    capture[key]
                    for key in (
                        "manifest_sha256",
                        "normalizer_version",
                        "source",
                        "license",
                        "publisher",
                    )
                ):
                    raise MetadataError("metadata_scope")
            inserted = c.execute(
                "INSERT INTO nima_processing.metadata_snapshots "
                "(snapshot_sha256,source,kimdis_run_id,gemi_run_id,document) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING snapshot_sha256",
                (snapshot_sha256, *expected[:3], Jsonb(document)),
            ).fetchone()
            if inserted is None:
                stored = c.execute(
                    "SELECT source,kimdis_run_id,gemi_run_id,document "
                    "FROM nima_processing.metadata_snapshots WHERE snapshot_sha256=%s",
                    (snapshot_sha256,),
                ).fetchone()
                if stored != expected:
                    raise MetadataError("metadata_conflict")
    except MigrationError:
        raise MetadataError("metadata_schema") from None
    except psycopg.Error:
        raise MetadataError("metadata_database") from None
    return MetadataPromotion(prepared.record_count, prepared.assertion_count, inserted is None)


def _reference(
    document: dict[str, object], dimension: str | None, code: str | None
) -> tuple[list[dict[str, object]], int]:
    records = []
    count = 0
    for record in cast(list[dict[str, object]], document["records"]):
        rows = select_assertions(cast(list[Assertion], record["assertions"]), dimension, code)
        count += len(rows)
        if rows or (dimension is None and code is None):
            records.append({**record, "assertions": rows})
    return records, count


def query_metadata(
    dsn: str,
    snapshot_sha256: str,
    *,
    dimension: str | None = None,
    code: str | None = None,
) -> bytes:
    """Read one explicit stored snapshot; verify hash and SQL/shared-policy parity."""
    _selection(snapshot_sha256)
    select_assertions([], dimension, code)
    try:
        query = files("nima.metadata").joinpath("query.sql").read_text()
        with connect(dsn) as c, c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            c.execute("SET LOCAL TIME ZONE 'UTC'")
            validate_schema(c)
            row = c.execute(
                "SELECT document FROM nima_processing.metadata_snapshots WHERE snapshot_sha256=%s",
                (snapshot_sha256,),
            ).fetchone()
            if row is None:
                raise MetadataError("metadata_unavailable")
            document = cast(dict[str, object], row[0])
            if hashlib.sha256(encode(document)).hexdigest() != snapshot_sha256:
                raise MetadataError("metadata_evidence")
            if document.get("artifact_version") != VERSION or document.get("query") != {
                "dimension": None,
                "code": None,
            }:
                raise MetadataError("metadata_version")
            validate_query(cast(str, document["source"]), dimension, code)
            expected, count = _reference(document, dimension, code)
            calculated = c.execute(
                query, (dimension, code, snapshot_sha256, snapshot_sha256)
            ).fetchone()
            if calculated is None or calculated != (expected, count):
                raise MetadataError("metadata_query")
            return encode(
                {
                    **document,
                    "query": {"dimension": dimension, "code": code},
                    "matched_assertion_count": count,
                    "records": expected,
                }
            )
    except MigrationError:
        raise MetadataError("metadata_schema") from None
    except psycopg.Error:
        raise MetadataError("metadata_database") from None
    except AssessmentError:
        raise MetadataError("metadata_limit") from None
    except OSError:
        raise MetadataError("metadata_query") from None
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        if isinstance(error, MetadataError):
            raise
        raise MetadataError("metadata_evidence") from None
