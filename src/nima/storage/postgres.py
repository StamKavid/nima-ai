"""Explicit migrations and atomic page storage; no implicit HTTP resume.

Transaction/parameter patterns: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
and https://www.psycopg.org/psycopg3/docs/basic/params.html .
"""

import hashlib
from dataclasses import asdict
from datetime import datetime
from importlib.resources import files
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from nima.ingestion.archive import Archive
from nima.ingestion.config import CONNECTOR_VERSION, Query
from nima.sources.kimdis import normalize_page

type Connection = psycopg.Connection[tuple[object, ...]]
NORMALIZER_VERSION = "kimdis-normalized-v1"


class MigrationError(ValueError):
    """Migration history or database major version is unsupported."""


class CheckpointError(ValueError):
    """A page conflicts with immutable run identity or committed evidence."""


def _connect(dsn: str) -> Connection:
    return psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=5,
        options="-c statement_timeout=30000 -c lock_timeout=5000",
    )


def _migrations() -> list[tuple[int, str, str]]:
    result = []
    for version in (1, 2, 3, 4):
        body = files("nima.storage").joinpath(f"migrations/{version:04d}.sql").read_text()
        result.append((version, body, hashlib.sha256(body.encode()).hexdigest()))
    return result


def _applied(connection: Connection, migrations: list[tuple[int, str, str]]) -> int:
    if connection.info.server_version // 10000 != 17:
        raise MigrationError("This schema is tested on PostgreSQL 17")
    history = connection.execute(
        "SELECT version, sha256 FROM nima.schema_migrations ORDER BY version"
    ).fetchall()
    expected = [(version, digest) for version, _, digest in migrations]
    if history != expected[: len(history)]:
        raise MigrationError("Unknown migration version or changed checksum")
    return len(history)


def check_schema(dsn: str) -> None:
    """Validate current migration history without applying DDL."""
    migrations = _migrations()
    try:
        with _connect(dsn) as connection:
            if _applied(connection, migrations) != len(migrations):
                raise MigrationError("Run the explicit database migration first")
    except psycopg.errors.UndefinedTable:
        raise MigrationError("Run the explicit database migration first") from None


def migrate(dsn: str) -> None:
    """Apply pending packaged migrations atomically, rejecting altered history."""
    migrations = _migrations()
    with _connect(dsn) as connection, connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(812344001, 1)")
        connection.execute("CREATE SCHEMA IF NOT EXISTS nima")
        connection.execute("""CREATE TABLE IF NOT EXISTS nima.schema_migrations (
            version integer PRIMARY KEY, sha256 text NOT NULL)""")
        applied = _applied(connection, migrations)
        for version, body, digest in migrations[applied:]:
            connection.execute(body)
            connection.execute(
                "INSERT INTO nima.schema_migrations VALUES (%s, %s)", (version, digest)
            )


class PageStore:
    """Each operation owns its connection and commits exactly one transaction."""

    def __init__(self, dsn: str, archive: Archive) -> None:
        self._dsn, self.archive = dsn, archive

    def _identity(self) -> tuple[str, str, str]:
        return CONNECTOR_VERSION, NORMALIZER_VERSION, str(self.archive.root)

    def start_run(self, run_id: UUID, query: Query) -> None:
        with _connect(self._dsn) as connection, connection.transaction():
            connection.execute(
                """INSERT INTO nima.ingest_runs
                (run_id, query, connector_version, normalizer_version, archive_root)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (run_id, Jsonb(query.payload()), *self._identity()),
            )
            row = connection.execute(
                """SELECT query, connector_version,
                normalizer_version, archive_root FROM nima.ingest_runs WHERE run_id = %s""",
                (run_id,),
            ).fetchone()
            if row != (query.payload(), *self._identity()):
                raise CheckpointError("Run query, connector, normalizer, or archive differs")

    def commit_page(
        self,
        run_id: UUID,
        raw_body: bytes,
        *,
        observed_at: datetime,
        owner: UUID | None = None,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> bool:
        """Archive first, then atomically persist a page or verify identical replay."""
        if observed_at.utcoffset() is None:
            raise ValueError("Observation time must include a timezone")
        digest = self.archive.store(raw_body)
        page = normalize_page(raw_body, max_bytes=max_bytes)
        shape = (page.total_records, page.total_pages, page.size)
        with _connect(self._dsn) as connection, connection.transaction():
            row = connection.execute(
                """SELECT next_page, total_records, total_pages,
                page_size, connector_version, normalizer_version, archive_root, owner
                FROM nima.ingest_runs WHERE run_id = %s FOR UPDATE""",
                (run_id,),
            ).fetchone()
            if row is None or row[4:7] != self._identity() or row[7] != owner:
                raise CheckpointError("Unknown run or mismatched processing identity")
            previous = connection.execute(
                """SELECT raw_sha256 FROM nima.run_pages
                WHERE run_id = %s AND page_number = %s""",
                (run_id, page.number),
            ).fetchone()
            if previous is not None:
                if previous[0] != digest:
                    raise CheckpointError("Committed page evidence cannot change")
                return False
            if row[0] != page.number or (row[1] is not None and row[1:4] != shape):
                raise CheckpointError("Page gap or changed pagination")
            connection.execute(
                """INSERT INTO nima.raw_objects VALUES (%s, %s)
                ON CONFLICT DO NOTHING""",
                (digest, len(raw_body)),
            )
            connection.execute(
                """INSERT INTO nima.run_pages
                (run_id, page_number, raw_sha256, observed_at, record_count,
                 quarantined_count, source_ids) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    run_id,
                    page.number,
                    digest,
                    observed_at,
                    page.record_count,
                    len(page.issues),
                    list(page.source_ids),
                ),
            )
            for contract in page.contracts:
                index = int(contract.evidence.json_pointer.rsplit("/", 1)[1])
                version = (contract.source_id, NORMALIZER_VERSION, page.record_hashes[index])
                normalized = asdict(contract)
                del normalized["evidence"]
                for field in ("net_amount", "gross_amount"):
                    if normalized[field] is not None:
                        normalized[field] = str(normalized[field])
                connection.execute(
                    """INSERT INTO nima.source_records VALUES (%s)
                    ON CONFLICT DO NOTHING""",
                    (contract.source_id,),
                )
                connection.execute(
                    """INSERT INTO nima.record_versions VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING""",
                    (*version, Jsonb(normalized)),
                )
                connection.execute(
                    """WITH observed AS (INSERT INTO nima.observations
                    (run_id, page_number, record_index, source_id,
                     normalizer_version, content_sha256)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING observation_id)
                    INSERT INTO nima.outbox (observation_id) SELECT observation_id FROM observed""",
                    (run_id, page.number, index, *version),
                )
            for issue in page.issues:
                index = int(issue.evidence.json_pointer.rsplit("/", 1)[1])
                connection.execute(
                    "INSERT INTO nima.quarantine VALUES (%s, %s, %s, %s)",
                    (run_id, page.number, index, issue.reason),
                )
            connection.execute(
                """UPDATE nima.ingest_runs SET next_page = %s,
                total_records = %s, total_pages = %s, page_size = %s WHERE run_id = %s""",
                (page.number + 1, *shape, run_id),
            )
        return True
