"""One local projection transaction per event, including receipt and acknowledgement.

Queue locking: https://www.postgresql.org/docs/17/sql-select.html#SQL-FOR-UPDATE-SHARE
Bulk conversion: https://www.postgresql.org/docs/17/functions-json.html
"""

from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from nima.projections.contracts import InvalidProjection, project_contract
from nima.sources.registry import DEFAULT_SOURCE
from nima.storage.postgres import NORMALIZER_VERSION, Connection, _connect, check_schema

PROJECTION_VERSION = "kimdis-participation-v1"
# Source ids are namespaced by their adapter (`kimdis:<reference>`); this projection reads one
# source.
SOURCE_PREFIX = f"{DEFAULT_SOURCE}:"


class ProjectionFailure(Exception):
    """Public failure metadata excludes source assertions and driver messages."""

    def __init__(self, processed: int, event_id: int | None, reason: str) -> None:
        self.processed, self.event_id, self.reason = processed, event_id, reason
        super().__init__(reason)


def _project(connection: Connection, row: tuple[object, ...]) -> bool:
    event_id, event_type, source_id, normalizer, content_hash, normalized = row
    # Under the outbox row lock, use a fresh READ COMMITTED snapshot. Another
    # consumer may have committed after the claiming SELECT took its snapshot.
    if (
        connection.execute(
            "SELECT 1 FROM nima.projection_receipts "
            "WHERE projection_version=%s AND observation_id=%s",
            (PROJECTION_VERSION, event_id),
        ).fetchone()
        is not None
    ):
        return False
    if event_type != "record.observed" or normalizer != NORMALIZER_VERSION:
        raise InvalidProjection("Unsupported event or normalizer")
    projection = project_contract(normalized)
    if projection.source_id != source_id:
        raise InvalidProjection("Mismatched source identity")
    key = (PROJECTION_VERSION, source_id, normalizer, content_hash)
    digest = projection.digest()
    connection.execute(
        """INSERT INTO nima.projection_contracts
        (projection_version, source_id, normalizer_version, content_sha256, projection_sha256,
         title, net_amount, gross_amount, currency, bidder_count, cancelled,
         source_submitted_at, source_updated_at, supplier_count)
        SELECT %s, %s, %s, %s, %s, f.* FROM jsonb_to_record(%s) AS f(
        title text, net_amount numeric, gross_amount numeric, currency text,
        bidder_count bigint, cancelled boolean, source_submitted_at text,
        source_updated_at text, supplier_count integer) ON CONFLICT DO NOTHING""",
        (*key, digest, Jsonb(projection.payload())),
    )
    existing = connection.execute(
        """SELECT projection_sha256 FROM nima.projection_contracts
        WHERE projection_version=%s AND source_id=%s AND normalizer_version=%s
        AND content_sha256=%s""",
        key,
    ).fetchone()
    if existing != (digest,):
        raise InvalidProjection("Projection changed without version bump")
    connection.execute(
        """INSERT INTO nima.projection_mentions
        (projection_version, source_id, normalizer_version, content_sha256,
         role, ordinal, name, tax_id, source_key, country_code)
        SELECT %s, %s, %s, %s, m.* FROM jsonb_to_recordset(%s) AS m(
        role text, ordinal integer, name text, tax_id text, source_key text, country_code text)
        ON CONFLICT DO NOTHING""",
        (*key, Jsonb(projection.payload()["mentions"])),
    )
    connection.execute(
        "INSERT INTO nima.projection_receipts (projection_version, observation_id) VALUES (%s, %s)",
        (PROJECTION_VERSION, event_id),
    )
    connection.execute(
        """UPDATE nima.outbox SET delivered_at=COALESCE(delivered_at, clock_timestamp())
        WHERE observation_id=%s""",
        (event_id,),
    )
    return True


def drain(dsn: str, *, max_events: int = 100, run_id: UUID | None = None) -> dict[str, object]:
    """Process a bounded batch; retry locked/later-committing IDs next invocation.

    The outbox holds the events of every source. Without a run, only this projection's own source
    is claimed and counted, so another source's events neither stop the queue nor keep the backlog
    above zero; they stay undelivered for their own consumer. An event of this source that cannot be
    projected (an unknown normalizer version, a bad shape) still stops visibly. Naming a run
    projects exactly that run, and a run of another source fails visibly.
    """
    if type(max_events) is not int or not 1 <= max_events <= 1000:
        raise ValueError("max_events must be 1–1000")
    check_schema(dsn)
    processed, after_id = 0, 0
    event_id: int | None = None
    try:
        with _connect(dsn) as connection:
            for _ in range(max_events):
                event_id = None
                with connection.transaction():
                    row = connection.execute(
                        """SELECT q.observation_id, q.event_type,
                        v.source_id, v.normalizer_version, v.content_sha256, v.normalized
                        FROM nima.outbox q JOIN nima.observations o USING (observation_id)
                        JOIN nima.record_versions v
                            USING (source_id, normalizer_version, content_sha256)
                        WHERE q.observation_id > %s
                        AND (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM nima.observations selected
                            WHERE selected.observation_id=q.observation_id AND selected.run_id=%s))
                        AND (%s::uuid IS NOT NULL OR starts_with(v.source_id, %s))
                        AND NOT EXISTS (
                            SELECT 1 FROM nima.projection_receipts r
                            WHERE r.projection_version=%s AND r.observation_id=q.observation_id)
                        ORDER BY q.observation_id LIMIT 1 FOR UPDATE OF q SKIP LOCKED""",
                        (after_id, run_id, run_id, run_id, SOURCE_PREFIX, PROJECTION_VERSION),
                    ).fetchone()
                    if row is None:
                        break
                    event_id = cast(int, row[0])
                    projected = _project(connection, row)
                after_id = event_id  # Invocation-local only; never a durable watermark.
                processed += int(projected)
            event_id = None  # A summary-query failure does not identify a poison event.
            remaining_row = connection.execute(
                """SELECT count(*) FROM nima.outbox q
                WHERE (%s::uuid IS NULL OR EXISTS (SELECT 1 FROM nima.observations selected
                    WHERE selected.observation_id=q.observation_id AND selected.run_id=%s))
                AND (%s::uuid IS NOT NULL OR EXISTS (SELECT 1 FROM nima.observations o
                    WHERE o.observation_id=q.observation_id AND starts_with(o.source_id, %s)))
                AND NOT EXISTS (SELECT 1 FROM nima.projection_receipts r
                    WHERE r.projection_version=%s AND r.observation_id=q.observation_id)""",
                (run_id, run_id, run_id, SOURCE_PREFIX, PROJECTION_VERSION),
            ).fetchone()
            remaining = cast(tuple[int], remaining_row)[0]  # COUNT always returns one row.
    except (InvalidProjection, psycopg.Error) as exc:
        reason = "invalid_projection" if isinstance(exc, InvalidProjection) else "database"
        raise ProjectionFailure(processed, event_id, reason) from None
    return {
        "projection_version": PROJECTION_VERSION,
        "processed_events": processed,
        "remaining_events": remaining,
        "status": "complete" if remaining == 0 else "pending",
    }
