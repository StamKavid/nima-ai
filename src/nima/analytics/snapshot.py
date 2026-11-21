"""Freeze bounded SQL facts, not verified originals, on one SELECT-only connection."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from nima.projections.contracts import InvalidProjection, project_contract
from nima.semantics.participation import (
    MetricResult,
    Observation,
    SemanticError,
    Supplier,
    definition,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.storage.connection import Connection, connect
from nima.storage.postgres import MigrationError, validate_schema

REQUIRED_TABLES = (
    "schema_migrations",
    "ingest_runs",
    "run_pages",
    "raw_objects",
    "observations",
    "record_versions",
    "quarantine",
    "projection_contracts",
    "projection_mentions",
    "projection_receipts",
)
MAX_INPUT_BYTES = 8 * 1024 * 1024


class SnapshotError(ValueError):
    """Fixed reason only, without database/source values or filesystem paths."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ReadoutSnapshot:
    document_json: str
    observations: tuple[Observation, ...]
    metric: MetricResult
    input_sha256: str


@dataclass(frozen=True)
class Cohort:
    """Metric-agnostic frozen evidence: SQL facts validated for coverage and versions."""

    document: dict[str, object]
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class _Calculation:
    connector: str
    normalizer: str
    projection: str
    definition_hash: str
    sql: str


def _calculation() -> _Calculation:
    policy, query = definition(), reference_sql()
    if hashlib.sha256(query.encode()).hexdigest() != policy["sql_sha256"]:
        raise SnapshotError("analytics_metric")
    digest = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return _Calculation(
        cast(str, policy["connector"]),
        cast(str, policy["normalizer"]),
        cast(str, policy["projection"]),
        digest,
        query,
    )


_DOCUMENT = """SELECT jsonb_build_object(
    'runs', coalesce((SELECT jsonb_agg(jsonb_build_object(
        'run_id',r.run_id,'query',r.query,'connector_version',r.connector_version,
        'normalizer_version',r.normalizer_version,'status',r.status,
        'managed',r.owner IS NOT NULL AND r.settings IS NOT NULL,
        'next_page',r.next_page,'total_records',r.total_records,
        'total_pages',r.total_pages,'page_size',r.page_size,
        'quarantine_count',(SELECT count(*) FROM nima.quarantine q WHERE q.run_id=r.run_id)
    ) ORDER BY r.run_id) FROM nima.ingest_runs r WHERE r.run_id=ANY(%(runs)s)), '[]'),
    'pages', coalesce((SELECT jsonb_agg(to_jsonb(p) ||
        jsonb_build_object('byte_length',b.byte_length) ORDER BY p.run_id,p.page_number)
        FROM nima.run_pages p LEFT JOIN nima.raw_objects b ON b.sha256=p.raw_sha256
        WHERE p.run_id=ANY(%(runs)s)), '[]'),
    'records', coalesce((SELECT jsonb_agg(to_jsonb(o) || jsonb_build_object(
        'normalized',v.normalized,
        'projection',to_jsonb(f) || jsonb_build_object(
            'net_amount',f.net_amount::text,'gross_amount',f.gross_amount::text),
        'receipt',EXISTS(SELECT 1 FROM nima.projection_receipts pr
            WHERE pr.observation_id=o.observation_id AND pr.projection_version=%(projection)s),
        'mentions',coalesce((SELECT jsonb_agg(to_jsonb(m) ORDER BY m.role COLLATE "C",m.ordinal)
            FROM nima.projection_mentions m WHERE m.projection_version=%(projection)s
            AND m.source_id=o.source_id AND m.normalizer_version=o.normalizer_version
            AND m.content_sha256=o.content_sha256), '[]')
    ) ORDER BY o.observation_id)
        FROM nima.observations o LEFT JOIN nima.record_versions v
            USING(source_id,normalizer_version,content_sha256)
        LEFT JOIN nima.projection_contracts f ON f.source_id=o.source_id
            AND f.normalizer_version=o.normalizer_version AND f.content_sha256=o.content_sha256
            AND f.projection_version=%(projection)s
        WHERE o.run_id=ANY(%(runs)s)), '[]'))"""


def _encode(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    )


def _preflight(connection: Connection, parameters: dict[str, object]) -> None:
    counts = connection.execute(
        """SELECT
        (SELECT count(*) FROM nima.observations WHERE run_id=ANY(%(runs)s)),
        (SELECT count(*) FROM nima.run_pages WHERE run_id=ANY(%(runs)s)),
        (SELECT coalesce(max(b.byte_length),0) FROM nima.run_pages p
            JOIN nima.raw_objects b ON b.sha256=p.raw_sha256 WHERE p.run_id=ANY(%(runs)s))
        """,
        parameters,
    ).fetchone()
    if (
        counts is None
        or cast(int, counts[0]) > 500
        or cast(int, counts[1]) > 32
        or cast(int, counts[2]) > 8 * 1024 * 1024
    ):
        raise SnapshotError("analytics_limit")
    size = connection.execute(
        "SELECT octet_length((" + _DOCUMENT + ")::text)", parameters
    ).fetchone()
    if size is None or cast(int, size[0]) > MAX_INPUT_BYTES:
        raise SnapshotError("analytics_limit")


def _projection(record: dict[str, object], projection_version: str) -> Observation:
    try:
        if record["receipt"] is not True or not isinstance(record["projection"], dict):
            raise SnapshotError("analytics_projection")
        projection = project_contract(record["normalized"])
        key = {name: record[name] for name in ("source_id", "normalizer_version", "content_sha256")}
        key["projection_version"] = projection_version
        expected = {**key, **projection.payload(), "projection_sha256": projection.digest()}
        mentions = expected.pop("mentions")
        stored = dict(cast(dict[str, object], record["projection"]))
        for field in ("net_amount", "gross_amount"):
            for value in (stored, expected):
                if value[field] is not None:
                    if not isinstance(value[field], str):
                        raise SnapshotError("analytics_projection")
                    number = Decimal(cast(str, value[field]))
                    if not number.is_finite():
                        raise SnapshotError("analytics_projection")
                    value[field] = number
        expected_mentions = [
            {**key, **mention} for mention in cast(list[dict[str, object]], mentions)
        ]
        if (
            stored != expected
            or record["mentions"] != expected_mentions
            or projection.source_id != record["source_id"]
        ):
            raise SnapshotError("analytics_projection")
        return Observation(
            cast(int, record["observation_id"]),
            projection.source_id,
            cast(str, record["normalizer_version"]),
            cast(str, record["content_sha256"]),
            datetime.fromisoformat(cast(str, record["observed_at"])),
            projection.mentions[0].source_key,
            projection.cancelled,
            None
            if projection.supplier_count is None
            else tuple(
                Supplier(mention.ordinal, mention.tax_id, mention.country_code)
                for mention in projection.mentions
                if mention.role == "supplier"
            ),
        )
    except (InvalidProjection, InvalidOperation, KeyError, TypeError, ValueError) as error:
        if isinstance(error, SnapshotError):
            raise
        raise SnapshotError("analytics_projection") from None


def _validate_document(
    document: dict[str, object],
    run_ids: tuple[UUID, ...],
    calculation: _Calculation,
) -> tuple[Observation, ...]:
    runs = cast(list[dict[str, object]], document["runs"])
    pages = cast(list[dict[str, object]], document["pages"])
    records = cast(list[dict[str, object]], document["records"])
    if [run["run_id"] for run in runs] != [str(run) for run in run_ids]:
        raise SnapshotError("analytics_coverage")
    page_map = {(page["run_id"], page["page_number"]): page for page in pages}
    if len(page_map) != len(pages):
        raise SnapshotError("analytics_coverage")
    for run in runs:
        if (
            run["connector_version"] != calculation.connector
            or run["normalizer_version"] != calculation.normalizer
        ):
            raise SnapshotError("analytics_version")
        if (
            run["status"] != "complete"
            or run["managed"] is not True
            or run["quarantine_count"] != 0
        ):
            raise SnapshotError("analytics_coverage")
        total, size, total_pages = run["total_records"], run["page_size"], run["total_pages"]
        if (
            type(total) is not int
            or type(size) is not int
            or type(total_pages) is not int
            or total < 0
            or size <= 0
            or total_pages != (total + size - 1) // size
        ):
            raise SnapshotError("analytics_coverage")
        selected = [page for page in pages if page["run_id"] == run["run_id"]]
        count = max(1, total_pages)
        if run["next_page"] != count or [page["page_number"] for page in selected] != list(
            range(count)
        ):
            raise SnapshotError("analytics_coverage")
        for page in selected:
            expected = min(size, max(0, total - cast(int, page["page_number"]) * size))
            members = sorted(
                (
                    record
                    for record in records
                    if (record["run_id"], record["page_number"])
                    == (page["run_id"], page["page_number"])
                ),
                key=lambda record: cast(int, record["record_index"]),
            )
            if (
                page["record_count"] != expected
                or page["quarantined_count"] != 0
                or [record["record_index"] for record in members] != list(range(expected))
                or [record["source_id"] for record in members] != page["source_ids"]
                or type(page["byte_length"]) is not int
                or page["byte_length"] < 0
            ):
                raise SnapshotError("analytics_coverage")
        _query(run["query"])
    observations = []
    for record in records:
        stored_page = page_map.get((record["run_id"], record["page_number"]))
        if stored_page is None:
            raise SnapshotError("analytics_coverage")
        observations.append(
            _projection(
                {**record, "observed_at": stored_page["observed_at"]}, calculation.projection
            )
        )
    return tuple(observations)


def _query(value: object) -> None:
    try:
        if not isinstance(value, dict) or set(value) not in (
            {"dateFrom", "dateTo"},
            {"dateFrom", "dateTo", "organizations"},
        ):
            raise ValueError
        start, end = date.fromisoformat(value["dateFrom"]), date.fromisoformat(value["dateTo"])
        if (
            start.isoformat() != value["dateFrom"]
            or end.isoformat() != value["dateTo"]
            or not 0 <= (end - start).days < 180
        ):
            raise ValueError
        buyers = value.get("organizations", [])
        if not isinstance(buyers, list) or any(
            not isinstance(buyer, str)
            or not buyer.isascii()
            or not buyer.isdecimal()
            or int(buyer) <= 0
            for buyer in buyers
        ):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise SnapshotError("analytics_coverage") from None


def _read_cohort(
    connection: Connection, run_ids: tuple[UUID, ...], calculation: _Calculation
) -> Cohort:
    parameters: dict[str, object] = {
        "runs": list(run_ids),
        "projection": calculation.projection,
    }
    _preflight(connection, parameters)
    row = connection.execute(_DOCUMENT, parameters).fetchone()
    if row is None:
        raise SnapshotError("analytics_coverage")
    document = cast(dict[str, object], row[0])
    return Cohort(document, _validate_document(document, run_ids, calculation))


def _load(
    connection: Connection,
    run_ids: tuple[UUID, ...],
    tax_id: str,
    cutoff: datetime,
    calculation: _Calculation,
) -> ReadoutSnapshot:
    cohort = _read_cohort(connection, run_ids, calculation)
    document, observations = cohort.document, cohort.observations
    metric = evaluate(observations, tax_id=tax_id, cutoff=cutoff)
    calculated = connection.execute(
        calculation.sql, (Jsonb(sql_rows(observations)), cutoff, tax_id)
    ).fetchone()
    if calculated is None or calculated[0] != metric.payload():
        raise SnapshotError("analytics_metric")
    return _freeze(document, observations, metric, run_ids, tax_id, cutoff, calculation)


def _freeze(
    document: dict[str, object],
    observations: tuple[Observation, ...],
    metric: MetricResult,
    run_ids: tuple[UUID, ...],
    tax_id: str,
    cutoff: datetime,
    calculation: _Calculation,
) -> ReadoutSnapshot:
    encoded = _encode(document)
    if len(encoded.encode()) > MAX_INPUT_BYTES:
        raise SnapshotError("analytics_limit")
    identity = _encode(
        {
            "document": document,
            "run_ids": [str(run) for run in run_ids],
            "tax_id": tax_id,
            "country": "GR",
            "cutoff": cutoff.isoformat(),
            "definition_sha256": calculation.definition_hash,
        }
    )
    return ReadoutSnapshot(
        encoded, observations, metric, hashlib.sha256(identity.encode()).hexdigest()
    )


def validate_snapshot(
    snapshot: ReadoutSnapshot,
    run_ids: tuple[UUID, ...],
    *,
    tax_id: str,
    cutoff: datetime,
    expected_definition_sha256: str | None = None,
) -> dict[str, object]:
    """Rebind frozen SQL facts to a selection without reopening SQL or any archive."""
    try:
        if not isinstance(snapshot, ReadoutSnapshot) or not isinstance(snapshot.document_json, str):
            raise SnapshotError("analytics_evidence")
        if len(snapshot.document_json.encode()) > MAX_INPUT_BYTES:
            raise SnapshotError("analytics_limit")
        selected = _selection(run_ids, tax_id, cutoff)
        value: object = json.loads(snapshot.document_json)
        if not isinstance(value, dict) or set(value) != {"runs", "pages", "records"}:
            raise SnapshotError("analytics_evidence")
        document = cast(dict[str, object], value)
        for name, limit in (("runs", 10), ("pages", 32), ("records", 500)):
            rows = document[name]
            if (
                not isinstance(rows, list)
                or len(rows) > limit
                or any(not isinstance(row, dict) for row in rows)
            ):
                raise SnapshotError("analytics_evidence")
        calculation = _calculation()
        if (
            expected_definition_sha256 is not None
            and expected_definition_sha256 != calculation.definition_hash
        ):
            raise SnapshotError("analytics_metric")
        observations = _validate_document(document, selected, calculation)
        metric = evaluate(observations, tax_id=tax_id, cutoff=cutoff)
        if (
            _freeze(document, observations, metric, selected, tax_id, cutoff, calculation)
            != snapshot
        ):
            raise SnapshotError("analytics_evidence")
        return document
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        if isinstance(error, SnapshotError):
            raise
        raise SnapshotError("analytics_evidence") from None


def _role(connection: Connection) -> None:
    row = connection.execute("""SELECT
        (SELECT rolsuper FROM pg_roles WHERE rolname=current_user),
        has_schema_privilege(current_user,'nima','CREATE'),
        EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='nima' AND (
                (c.relkind IN ('r','p','v','m','f') AND (
                    has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                    OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE,REFERENCES')))
                OR (c.relkind='S' AND has_sequence_privilege(current_user,c.oid,'USAGE,UPDATE')))),
        (SELECT pg_has_role(current_user,datdba,'USAGE') FROM pg_database
            WHERE datname=current_database())
        """).fetchone()
    if row is None or any(row):
        raise SnapshotError("analytics_role")
    missing = connection.execute(
        """SELECT count(*) FROM unnest(%s::text[]) name
        WHERE NOT has_table_privilege(current_user,'nima.' || name,'SELECT')""",
        (list(REQUIRED_TABLES),),
    ).fetchone()
    if missing != (0,):
        raise SnapshotError("analytics_role")


def _run_selection(run_ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
    if (
        not isinstance(run_ids, tuple)
        or not 1 <= len(run_ids) <= 10
        or any(not isinstance(run, UUID) for run in run_ids)
        or len(set(run_ids)) != len(run_ids)
    ):
        raise SnapshotError("analytics_input")
    return tuple(sorted(run_ids))


def _selection(run_ids: tuple[UUID, ...], tax_id: str, cutoff: datetime) -> tuple[UUID, ...]:
    selected = _run_selection(run_ids)
    evaluate((), tax_id=tax_id, cutoff=cutoff)
    return selected


def connected[T](dsn: str, work: Callable[[Connection], T]) -> T:
    """One SELECT-only, repeatable-read connection with schema and role checks."""
    try:
        with connect(dsn) as connection, connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            validate_schema(connection)
            _role(connection)
            return work(connection)
    except MigrationError:
        raise SnapshotError("analytics_schema") from None
    except SemanticError:
        raise SnapshotError("analytics_input") from None
    except psycopg.errors.InsufficientPrivilege:
        raise SnapshotError("analytics_role") from None
    except psycopg.Error:
        raise SnapshotError("analytics_database") from None
    except (ValueError, TypeError, KeyError) as error:
        if isinstance(error, SnapshotError):
            raise
        raise SnapshotError("analytics_evidence") from None


def read_cohort(dsn: str, run_ids: tuple[UUID, ...]) -> Cohort:
    """Frozen, coverage-checked evidence of the selected runs for any metric."""
    selected = _run_selection(run_ids)
    calculation = _calculation()
    return connected(dsn, lambda connection: _read_cohort(connection, selected, calculation))


def read_snapshot(
    dsn: str,
    run_ids: tuple[UUID, ...],
    *,
    tax_id: str,
    cutoff: datetime,
) -> ReadoutSnapshot:
    """Return frozen SQL evidence; caller must reconcile archives before publication."""
    try:
        selected = _selection(run_ids, tax_id, cutoff)
    except SemanticError:
        raise SnapshotError("analytics_input") from None
    calculation = _calculation()
    return connected(
        dsn, lambda connection: _load(connection, selected, tax_id, cutoff, calculation)
    )
