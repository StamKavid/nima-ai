"""Durable fresh-run journals and read-only SQL inspection; no HTTP resume.

SQL aggregate/JSON/array semantics: https://www.postgresql.org/docs/17/functions-aggregate.html
https://www.postgresql.org/docs/17/functions-json.html
https://www.postgresql.org/docs/17/functions-array.html
"""

from dataclasses import asdict
from typing import cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Query, Summary
from nima.storage.postgres import CheckpointError, Connection, PageStore, _connect, check_schema


class RunStore(PageStore):
    def __init__(self, dsn: str, archive: Archive, run_id: UUID, limits: Limits):
        super().__init__(dsn, archive)
        self.run_id, self.owner, self.limits = run_id, uuid4(), limits
        self._attempt_id: int | None = None

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
