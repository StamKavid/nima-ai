"""Read one immutable evidence cohort in a repeatable-read, read-only transaction.

https://www.postgresql.org/docs/17/sql-set-transaction.html
https://www.psycopg.org/psycopg3/docs/basic/transactions.html
"""

from typing import cast
from uuid import UUID

from psycopg.pq import TransactionStatus

from nima.identity import MAX_REPORT_BYTES, AssessmentError
from nima.identity.policy import Occurrence
from nima.ingestion.config import CONNECTOR_VERSION
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import NORMALIZER_VERSION, Connection, _connect, check_schema

_MEMBERS = """ FROM nima.observations o JOIN nima.run_pages p USING (run_id, page_number)
    JOIN nima.projection_mentions m USING (source_id, normalizer_version, content_sha256)
    WHERE o.run_id=%s AND m.projection_version=%s"""


def _coverage(connection: Connection, run: UUID, version: str) -> dict[str, object]:
    row = connection.execute(
        """SELECT jsonb_build_object(
        'stored_run_status', status, 'checkpoint_next_page', next_page,
        'reported_total_records', total_records, 'reported_total_pages', total_pages,
        'normalizer_version', normalizer_version, 'connector_version', connector_version,
        'page_count', (SELECT count(*) FROM nima.run_pages WHERE run_id=r.run_id),
        'quarantine_count', (SELECT count(*) FROM nima.quarantine WHERE run_id=r.run_id))
        FROM nima.ingest_runs r WHERE run_id=%s""",
        (run,),
    ).fetchone()
    if row is None:
        raise AssessmentError("run_unavailable")
    coverage = cast(dict[str, object], row[0])
    if (
        coverage["normalizer_version"] != NORMALIZER_VERSION
        or coverage["connector_version"] != CONNECTOR_VERSION
    ):
        raise AssessmentError("cohort_version")
    counts = cast(
        tuple[int, ...],
        connection.execute(
            """SELECT count(*), count(r.observation_id),
        count(f.source_id), count(*) FILTER (WHERE o.normalizer_version<>%s),
        coalesce(sum(1 + coalesce(f.supplier_count, 0)), 0),
        count(*) FILTER (WHERE f.supplier_count IS NULL),
        count(*) FILTER (WHERE f.supplier_count=0)
        FROM nima.observations o LEFT JOIN nima.projection_receipts r
            ON r.observation_id=o.observation_id AND r.projection_version=%s
        LEFT JOIN nima.projection_contracts f
            ON f.source_id=o.source_id AND f.normalizer_version=o.normalizer_version
            AND f.content_sha256=o.content_sha256 AND f.projection_version=%s
        WHERE o.run_id=%s""",
            (NORMALIZER_VERSION, version, version, run),
        ).fetchone(),
    )
    observations, receipts, facts, unsupported, expected, unknown, empty = counts
    if observations != receipts or observations != facts or unsupported:
        raise AssessmentError("projection_incomplete")
    return {
        **coverage,
        "observation_count": observations,
        "expected_mentions": expected,
        "unknown_supplier_lists": unknown,
        "empty_supplier_lists": empty,
        "collection_completeness": "not_certified",
    }


def _validate(version: str, max_mentions: int) -> None:
    if type(max_mentions) is not int or not 1 <= max_mentions <= 10000:
        raise ValueError("max_mentions must be 1–10000")
    if version != PROJECTION_VERSION:
        raise AssessmentError("projection_version")


def read_cohort(
    dsn: str, run: UUID, version: str, max_mentions: int
) -> tuple[dict[str, object], list[Occurrence]]:
    _validate(version, max_mentions)
    check_schema(dsn)
    with _connect(dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        return read_cohort_in_transaction(
            connection, run, version, max_mentions, max_input_bytes=MAX_REPORT_BYTES
        )


def read_cohort_in_transaction(
    connection: Connection,
    run: UUID,
    version: str,
    max_mentions: int,
    *,
    max_input_bytes: int = MAX_REPORT_BYTES,
) -> tuple[dict[str, object], list[Occurrence]]:
    """Read in the caller's active read-only repeatable-read transaction.

    The caller owns schema validation, UTC setup and transaction/connection
    lifetime. A lower input budget reserves room for other evidence in the same
    snapshot without changing the existing assessment wrapper's default guard.
    """
    _validate(version, max_mentions)
    if type(max_input_bytes) is not int or not 1 <= max_input_bytes <= MAX_REPORT_BYTES:
        raise ValueError("max_input_bytes")
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("cohort_transaction")
    if connection.execute(
        "SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only')"
    ).fetchone() != ("repeatable read", "on"):
        raise ValueError("cohort_transaction")
    coverage = _coverage(connection, run, version)
    if cast(int, coverage["expected_mentions"]) > max_mentions:
        raise AssessmentError("assessment_limit")
    # Bound decoded label data before transferring it into Python. JSON escaping
    # and evidence add overhead; the serialized report has its own exact bound.
    size = cast(
        tuple[int],
        connection.execute(
            "SELECT coalesce(sum(octet_length(row_to_json(m)::text) + 512), 0)" + _MEMBERS,
            (run, version),
        ).fetchone(),
    )[0]
    if size > max_input_bytes:
        raise AssessmentError("assessment_limit")
    rows = connection.execute(
        """SELECT to_jsonb(m) - 'projection_version' ||
            jsonb_build_object('observation_id', o.observation_id, 'evidence',
                jsonb_build_object('raw_sha256', p.raw_sha256,
                    'json_pointer', '/content/' || o.record_index, 'observed_at', p.observed_at))"""
        + _MEMBERS
        + " LIMIT %s",
        (run, version, max_mentions + 1),
    ).fetchall()
    members = [cast(Occurrence, row[0]) for row in rows]
    if len(members) != coverage["expected_mentions"]:
        raise AssessmentError("projection_incomplete")
    members.sort(
        key=lambda m: (
            m["source_id"],
            m["normalizer_version"],
            m["content_sha256"],
            m["role"],
            m["ordinal"],
        )
    )
    return coverage, members
