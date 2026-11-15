"""Minimal complete contract facts and reviews in one bounded, read-only SQL snapshot.

Re-derive persisted projections with the existing codec, then compare all stored
columns. This validates SQL consistency, not archive bytes or source truth.
https://www.postgresql.org/docs/17/transaction-iso.html
"""

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from nima.graph import GraphError
from nima.identity import review_evidence, review_snapshot
from nima.identity.review_state import MAX_REVIEW_EVENTS
from nima.identity.review_types import ReviewError, ReviewReport
from nima.projections.contracts import InvalidProjection, project_contract
from nima.storage.postgres import MigrationError, _connect, check_schema

MAX_OCCURRENCES = 100
_ROWS = """WITH selected AS (
    SELECT * FROM jsonb_to_recordset(%s) AS s
    (projection_version text,source_id text,normalizer_version text,content_sha256 text)
) SELECT to_jsonb(f) || jsonb_build_object(
    'net_amount',f.net_amount::text,'gross_amount',f.gross_amount::text) AS stored,
    v.normalized AS normalized FROM selected s
    JOIN nima.projection_contracts f USING
        (projection_version,source_id,normalizer_version,content_sha256)
    JOIN nima.record_versions v USING(source_id,normalizer_version,content_sha256)"""


@dataclass(frozen=True, order=True)
class ContractKey:
    projection_version: str
    source_id: str
    normalizer_version: str
    content_sha256: str


@dataclass(frozen=True)
class ContractFacts:
    key: ContractKey
    projection_sha256: str
    title: str
    net_amount: Decimal | None
    gross_amount: Decimal | None
    currency: str | None
    bidder_count: int | None
    cancelled: bool | None
    source_submitted_at: str | None
    source_updated_at: str | None
    supplier_count: int | None


@dataclass(frozen=True)
class GraphSnapshot:
    review: review_snapshot.ResolutionSnapshot
    contracts: tuple[ContractFacts, ...]

    @property
    def input_bytes(self) -> int:
        return self.review.input_bytes


def read_snapshot(
    dsn: str, report: ReviewReport, *, max_events: int = MAX_REVIEW_EVENTS
) -> GraphSnapshot:
    if type(max_events) is not int or not 1 <= max_events <= MAX_REVIEW_EVENTS:
        raise ValueError("graph_configuration")
    try:
        subjects = review_snapshot.validate_inputs(report, max_events=max_events)
        if len(subjects) > MAX_OCCURRENCES:
            raise GraphError("graph_limit")
        keys = tuple(
            sorted(
                {
                    ContractKey(
                        item.projection_version,
                        item.source_id,
                        item.normalizer_version,
                        item.content_sha256,
                    )
                    for item in subjects
                }
            )
        )
        parameters = (Jsonb([asdict(key) for key in keys]),)
        check_schema(dsn)
        with _connect(dsn) as connection, connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            count, extra_bytes = cast(
                tuple[int, int],
                connection.execute(
                    sql.SQL(
                        "SELECT count(*),coalesce(sum(octet_length(stored::text) + "
                        "octet_length(normalized::text)),0) FROM ({}) facts"
                    ).format(sql.SQL(_ROWS)),
                    parameters,
                ).fetchone(),
            )
            if count != len(keys):
                raise GraphError("graph_evidence")
            if extra_bytes > review_evidence.MAX_INPUT_BYTES:
                raise GraphError("graph_limit")
            review = review_snapshot.read_snapshot_in_transaction(
                connection, report, max_events=max_events, reserve_bytes=extra_bytes
            )
            rows = connection.execute(_ROWS, parameters).fetchall()
            facts = tuple(sorted((_fact(row[0], row[1]) for row in rows), key=lambda f: f.key))
            if tuple(fact.key for fact in facts) != keys:
                raise GraphError("graph_evidence")
        return GraphSnapshot(review, facts)
    except ReviewError as error:
        if error.reason == "review_limit":
            raise GraphError("graph_limit") from None
        if error.reason in {"review_state", "review_conflict"}:
            raise GraphError("graph_state") from None
        raise GraphError("graph_evidence") from None
    except MigrationError:
        raise GraphError("graph_schema") from None
    except psycopg.errors.InsufficientPrivilege:
        raise GraphError("graph_permission") from None
    except (psycopg.Error, ValueError):
        raise GraphError("graph_database") from None


def _fact(stored: object, normalized: object) -> ContractFacts:
    try:
        if not isinstance(stored, dict):
            raise GraphError("graph_evidence")
        data = cast(dict[str, object], stored)
        key = ContractKey(
            *(
                cast(str, data[field])
                for field in (
                    "projection_version",
                    "source_id",
                    "normalizer_version",
                    "content_sha256",
                )
            )
        )
        projection = project_contract(normalized)
        expected = projection.payload()
        del expected["mentions"]
        # numeric::text can expand source exponent notation. Compare exact Decimal
        # values without a JSON float round trip; keep original decimals in facts.
        expected["net_amount"] = projection.net_amount
        expected["gross_amount"] = projection.gross_amount
        actual = dict(data)
        for field in ("net_amount", "gross_amount"):
            if actual[field] is not None:
                if not isinstance(actual[field], str):
                    raise GraphError("graph_evidence")
                actual[field] = Decimal(cast(str, actual[field]))
        if actual != {**asdict(key), **expected, "projection_sha256": projection.digest()}:
            raise GraphError("graph_evidence")
        return ContractFacts(
            key,
            projection.digest(),
            projection.title,
            projection.net_amount,
            projection.gross_amount,
            projection.currency,
            projection.bidder_count,
            projection.cancelled,
            projection.source_submitted_at,
            projection.source_updated_at,
            projection.supplier_count,
        )
    except (InvalidProjection, InvalidOperation, KeyError, TypeError, ValueError):
        raise GraphError("graph_evidence") from None
