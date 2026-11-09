"""Durable fresh-run journals and read-only SQL inspection; no HTTP resume.

SQL aggregate/JSON/array semantics: https://www.postgresql.org/docs/17/functions-aggregate.html
https://www.postgresql.org/docs/17/functions-json.html
https://www.postgresql.org/docs/17/functions-array.html
"""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Query, Summary
from nima.storage.postgres import CheckpointError, Connection, PageStore, _connect, check_schema


class RunBusy(CheckpointError):
    """An active invocation holds the run's advisory lease."""


class RunStore(PageStore):
    def __init__(self, dsn: str, archive: Archive, run_id: UUID, limits: Limits):
        super().__init__(dsn, archive)
        self.run_id, self.owner, self.limits = run_id, uuid4(), limits
        self._attempt_id: int | None = None
        self._leased = False

    @contextmanager
    def lease(self) -> Iterator[None]:
        # Session locks auto-release on connection/process death. Writer UUIDs
        # still fence stale writes if that connection is lost during HTTP I/O.
        key = int.from_bytes(
            hashlib.sha256(b"nima-run-v1" + self.run_id.bytes).digest()[:8], signed=True
        )
        with _connect(self._dsn) as connection:
            if connection.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone() != (True,):
                raise RunBusy("Run is busy")
            self._leased = True
            try:
                yield
            finally:
                self._leased = False

    def takeover(self, query: Query) -> None:
        if not self._leased:
            raise CheckpointError("Takeover requires a run lease")
        with _connect(self._dsn) as connection, connection.transaction():
            row = connection.execute(
                """SELECT query, settings, connector_version,
                normalizer_version, archive_root FROM nima.ingest_runs
                WHERE run_id = %s FOR UPDATE""",
                (self.run_id,),
            ).fetchone()
            if row != (query.payload(), asdict(self.limits), *self._identity()):
                raise CheckpointError("Saved run settings or processing identity differ")
            connection.execute(
                """UPDATE nima.ingest_runs SET owner = %s, status = 'running',
                failure = NULL, updated_at = clock_timestamp() WHERE run_id = %s""",
                (self.owner, self.run_id),
            )

    def snapshot(self) -> tuple[int, int, list[tuple[int, str, datetime]]]:
        with _connect(self._dsn) as connection:
            row = connection.execute(
                """SELECT next_page,
                (SELECT count(*) FROM nima.http_attempts WHERE run_id = %s)
                FROM nima.ingest_runs WHERE run_id = %s""",
                (self.run_id, self.run_id),
            ).fetchone()
            pages = connection.execute(
                """SELECT page_number, raw_sha256, observed_at
                FROM nima.run_pages WHERE run_id = %s ORDER BY page_number LIMIT %s""",
                (self.run_id, self.limits.max_pages + 1),
            ).fetchall()
        if row is None or type(row[0]) is not int or type(row[1]) is not int:
            raise CheckpointError("Run checkpoint is unavailable")
        return row[0], row[1], cast(list[tuple[int, str, datetime]], pages)

    def pending(self, number: int) -> tuple[str, datetime] | None:
        with _connect(self._dsn) as connection:
            row = connection.execute(
                """SELECT raw_sha256, started_at FROM nima.http_attempts
                WHERE run_id = %s AND page_number = %s AND state = 'finished'
                  AND raw_sha256 IS NOT NULL AND receipt->>'status' = '200'
                  AND receipt->>'body_complete' = 'true'
                  AND coalesce(receipt->>'phase', 'collect') = 'collect'
                ORDER BY attempt_id LIMIT 1""",
                (self.run_id, number),
            ).fetchone()
        return cast(tuple[str, datetime] | None, row)

    def begin(self, query: Query) -> None:
        with _connect(self._dsn) as connection, connection.transaction():
            connection.execute(
                """INSERT INTO nima.ingest_runs
                (run_id, query, connector_version, normalizer_version, archive_root,
                 owner, settings, status) VALUES (%s, %s, %s, %s, %s, %s, %s, 'running')""",
                (
                    self.run_id,
                    Jsonb(query.payload()),
                    *self._identity(),
                    self.owner,
                    Jsonb(asdict(self.limits)),
                ),
            )

    def _owned(self, connection: Connection) -> None:
        row = connection.execute(
            "SELECT owner FROM nima.ingest_runs WHERE run_id = %s FOR UPDATE", (self.run_id,)
        ).fetchone()
        if row != (self.owner,):
            raise CheckpointError("Run writer identity differs")

    def started(self, receipt: dict[str, object]) -> None:
        with _connect(self._dsn) as connection, connection.transaction():
            self._owned(connection)
            row = connection.execute(
                """INSERT INTO nima.http_attempts
                (run_id, owner, page_number, retry_number, started_at, receipt)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING attempt_id""",
                (
                    self.run_id,
                    self.owner,
                    receipt["page"],
                    receipt["attempt"],
                    receipt["observed_at"],
                    Jsonb(receipt),
                ),
            ).fetchone()
            if row is None or type(row[0]) is not int:
                raise CheckpointError("No durable attempt identity returned")
            self._attempt_id = row[0]

    def finished(self, receipt: dict[str, object]) -> None:
        if self._attempt_id is None:
            raise CheckpointError("No started attempt to finish")
        with _connect(self._dsn) as connection, connection.transaction():
            self._owned(connection)
            digest = receipt.get("sha256") if receipt["body_complete"] else None
            if digest is not None:
                connection.execute(
                    """INSERT INTO nima.raw_objects VALUES (%s, %s)
                    ON CONFLICT DO NOTHING""",
                    (digest, receipt["bytes"]),
                )
            updated = connection.execute(
                """UPDATE nima.http_attempts
                SET state = 'finished', finished_at = clock_timestamp(),
                    raw_sha256 = %s, receipt = %s
                WHERE attempt_id = %s AND run_id = %s AND owner = %s AND state = 'started'""",
                (digest, Jsonb(receipt), self._attempt_id, self.run_id, self.owner),
            )
            if updated.rowcount != 1:
                raise CheckpointError("Durable attempt could not be finished")
        self._attempt_id = None

    def finish(self, summary: Summary) -> None:
        with _connect(self._dsn) as connection, connection.transaction():
            self._owned(connection)
            connection.execute(
                """UPDATE nima.ingest_runs SET status = %s, failure = %s,
                updated_at = clock_timestamp() WHERE run_id = %s""",
                (summary.status, summary.failure, self.run_id),
            )


def inspect_run(dsn: str, run_id: UUID) -> dict[str, object]:
    """Reconstruct committed counts; saved running state says nothing about liveness."""
    check_schema(dsn)
    with _connect(dsn) as connection:
        row = connection.execute(
            """SELECT jsonb_build_object(
            'run_id', replace(r.run_id::text, '-', ''), 'status', r.status, 'failure', r.failure,
            'query', r.query, 'limits', r.settings, 'next_page', r.next_page,
            'worker_liveness', 'unknown', 'expected_records', r.total_records,
            'expected_pages', r.total_pages, 'pages', p.pages, 'records', p.records,
            'normalized', (SELECT count(*) FROM nima.observations WHERE run_id = r.run_id),
            'quarantined', p.quarantined, 'unidentified', p.records - ids.seen,
            'duplicate_ids', ids.seen - ids.distinct_seen,
            'attempts', (SELECT count(*) FROM nima.http_attempts WHERE run_id = r.run_id),
            'pending_attempts', (SELECT count(*) FROM nima.http_attempts
                                WHERE run_id = r.run_id AND state = 'started'),
            'active_pending_attempts', (SELECT count(*) FROM nima.http_attempts
                WHERE run_id = r.run_id AND owner = r.owner AND state = 'started'),
            'collection_complete', coalesce(r.status IN ('complete', 'quarantined')
                AND p.pages = greatest(1, r.total_pages) AND p.records = r.total_records
                AND ids.seen = p.records AND ids.seen = ids.distinct_seen, false),
            'normalization_complete', coalesce(r.status = 'complete'
                AND p.pages = greatest(1, r.total_pages) AND p.records = r.total_records
                AND ids.seen = p.records AND ids.seen = ids.distinct_seen
                AND p.quarantined = 0, false))
            FROM nima.ingest_runs r
            CROSS JOIN LATERAL (SELECT count(*) pages, coalesce(sum(record_count), 0) records,
                coalesce(sum(quarantined_count), 0) quarantined FROM nima.run_pages
                WHERE run_id = r.run_id) p
            CROSS JOIN LATERAL (SELECT count(*) seen, count(DISTINCT id) distinct_seen
                FROM nima.run_pages, unnest(source_ids) id WHERE run_id = r.run_id) ids
            WHERE r.run_id = %s AND r.settings IS NOT NULL""",
            (run_id,),
        ).fetchone()
    if row is None:
        raise CheckpointError("Managed run not found")
    return cast(dict[str, object], row[0])


def load_options(dsn: str, run_id: UUID) -> tuple[Query, Limits, Path]:
    """Validate saved JSON options before using them for another invocation."""
    check_schema(dsn)
    with _connect(dsn) as connection:
        row = connection.execute(
            """SELECT query, settings, archive_root FROM nima.ingest_runs
            WHERE run_id = %s AND settings IS NOT NULL""",
            (run_id,),
        ).fetchone()
    if row is None or not isinstance(row[0], dict) or not isinstance(row[1], dict):
        raise CheckpointError("Managed run not found")
    query, settings = cast(dict[str, object], row[0]), cast(dict[str, object], row[1])

    def text(value: object) -> str:
        if not isinstance(value, str):
            raise CheckpointError("Invalid saved text option")
        return value

    def integer(key: str) -> int:
        value = settings.get(key)
        if type(value) is not int:
            raise CheckpointError("Invalid saved integer limit")
        return value

    def number(key: str) -> float:
        value = settings.get(key)
        if type(value) not in (int, float):
            raise CheckpointError("Invalid saved numeric limit")
        return float(cast(int | float, value))

    buyers = query.get("organizations", [])
    if not isinstance(buyers, list):
        raise CheckpointError("Invalid saved buyer filter")
    return (
        Query(
            date.fromisoformat(text(query.get("dateFrom"))),
            date.fromisoformat(text(query.get("dateTo"))),
            tuple(text(b) for b in buyers),
        ),
        Limits(
            integer("max_pages"),
            integer("max_attempts"),
            integer("max_bytes"),
            number("requests_per_minute"),
            number("request_timeout"),
            number("run_timeout"),
            number("max_retry_delay"),
        ),
        Path(text(row[2])),
    )
