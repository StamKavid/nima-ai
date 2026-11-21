"""Steps every cohort readout shares: SQL parity, hashes, selection labels and the size limit."""

import hashlib
import json
from collections.abc import Mapping

from psycopg.types.json import Jsonb

from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.analytics.snapshot import connected
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.storage.connection import Connection


def require_sql_parity(
    dsn: str,
    sql: str,
    rows: list[dict[str, object]],
    parameters: tuple[object, ...],
    payload: object,
) -> None:
    """The reference SQL, run on the same rows, must return exactly the provider's document."""

    def calculated(connection: Connection) -> object:
        row = connection.execute(sql, (Jsonb(rows), *parameters)).fetchone()
        return None if row is None else row[0]

    if connected(dsn, calculated) != payload:
        raise ReadoutError("analytics_metric")


def definition_hash(policy: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def cohort_hash(document: dict[str, object]) -> str:
    body = json.dumps(
        document, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    )
    return hashlib.sha256(body.encode()).hexdigest()


def selection_label(observation_id: int, decision: tuple[tuple[int, ...], bool] | None) -> str:
    """How a stored observation relates to the metric's record selection."""
    if decision is None:
        return "after_cutoff"
    observation_ids, ambiguous = decision
    if observation_id not in observation_ids:
        return "earlier_observation"
    return "ambiguous_revision" if ambiguous else "selected"


def encode_artifact(body: Mapping[str, object]) -> bytes:
    try:
        encoded = encode(body)
    except AssessmentError:
        raise ReadoutError("analytics_limit") from None
    if len(encoded) > MAX_RESULT_BYTES:
        raise ReadoutError("analytics_limit")
    return encoded
