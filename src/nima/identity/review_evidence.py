"""Reconcile frozen report claims with selected immutable SQL in the caller's transaction.

No connection ownership, current-run coverage substitution, source request or write.
Writers must call this boundary inside their own transaction, never accept a supplied
ReviewEvidence as permission to commit. SQL counts/bytes precede label transfer.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import cast
from uuid import UUID

from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from nima.identity import (
    MAX_COMPARISON_MENTIONS,
    MAX_REGISTRY_OBSERVATIONS,
    AssessmentError,
    ComparisonError,
)
from nima.identity.artifacts import encode
from nima.identity.registry_cohort import (
    _IMPORT_PARAMETERS,
    _IMPORT_ROWS,
    _REGISTRY_ROWS,
    ComparisonCohort,
    PartyEvidence,
    _imports,
)
from nima.identity.registry_report import build_report
from nima.identity.review_inputs import _party, _registry, decode_report
from nima.identity.review_inputs import _subject as _decode_subject
from nima.identity.review_types import ReviewError, ReviewEvidence, ReviewReport, ReviewSubject
from nima.ingestion.config import CONNECTOR_VERSION
from nima.projections.worker import PROJECTION_VERSION
from nima.sources.gemi import NORMALIZER_VERSION as GEMI_VERSION
from nima.storage.postgres import NORMALIZER_VERSION, Connection

MAX_INPUT_BYTES = 8 * 1024 * 1024
_KEYS = """SELECT * FROM jsonb_to_recordset(%s) AS s
    (observation_id bigint, role text, ordinal integer)"""
_PARTIES = """SELECT jsonb_build_object(
    'source_id',o.source_id,'normalizer_version',o.normalizer_version,
    'content_sha256',o.content_sha256,'observation_id',o.observation_id,
    'role',m.role,'ordinal',m.ordinal,'name',m.name,'tax_id',m.tax_id,
    'source_key',m.source_key,'country_code',m.country_code,
    'raw_sha256',p.raw_sha256,'json_pointer','/content/' || o.record_index,
    'observed_at',p.observed_at,'source_submitted_at',f.source_submitted_at,
    'source_updated_at',f.source_updated_at) AS payload
    FROM selected s JOIN nima.observations o USING(observation_id)
    JOIN nima.run_pages p USING(run_id,page_number)
    JOIN nima.ingest_runs r ON r.run_id=o.run_id
    JOIN nima.projection_receipts receipt ON receipt.observation_id=o.observation_id
        AND receipt.projection_version=%s
    JOIN nima.projection_mentions m ON m.source_id=o.source_id
        AND m.normalizer_version=o.normalizer_version AND m.content_sha256=o.content_sha256
        AND m.projection_version=receipt.projection_version
        AND m.role=s.role AND m.ordinal=s.ordinal
    JOIN nima.projection_contracts f ON f.projection_version=m.projection_version
        AND f.source_id=m.source_id AND f.normalizer_version=m.normalizer_version
        AND f.content_sha256=m.content_sha256
    WHERE o.run_id=%s AND r.connector_version=%s AND r.normalizer_version=%s
        AND o.normalizer_version=%s"""
_REGISTRY_SELECTED = """SELECT * FROM ({}) registry WHERE
    (payload->>'import_id')::uuid=ANY(%s) OR EXISTS (
        SELECT 1 FROM jsonb_to_recordset(%s) AS a(import_id uuid,registry_number text)
        WHERE a.import_id=(payload->>'import_id')::uuid
            AND a.registry_number=payload->>'registry_number')"""


def _subject(data: ComparisonCohort, party: PartyEvidence) -> ReviewSubject:
    return ReviewSubject(
        data.run_id,
        party.observation_id,
        data.projection_version,
        party.source_id,
        party.normalizer_version,
        party.content_sha256,
        party.role,
        party.ordinal,
    )


def _selection(
    report: ReviewReport, subjects: Sequence[ReviewSubject] | None, entity_ids: Sequence[UUID]
) -> tuple[ReviewSubject, ...]:
    # Recheck typed callers as well as file callers; no boolean 'validated' bypass.
    body = encode(build_report(report.cohort))
    if hashlib.sha256(body).hexdigest() != report.sha256:
        raise ReviewError("review_evidence")
    parsed = decode_report(body)
    if parsed.cohort != report.cohort or parsed.cohort.projection_version != PROJECTION_VERSION:
        raise ReviewError("review_evidence")
    available = {_subject(report.cohort, party) for party in report.cohort.parties}
    chosen = (
        tuple(sorted(available, key=lambda item: (item.observation_id, item.role, item.ordinal)))
        if subjects is None
        else tuple(subjects)
    )
    if len(chosen) > MAX_COMPARISON_MENTIONS or len(entity_ids) > MAX_REGISTRY_OBSERVATIONS:
        raise ReviewError("review_limit")
    if (
        (subjects is not None and not chosen and bool(available))
        or len(set(chosen)) != len(chosen)
        or any(item not in available for item in chosen)
        or any(_decode_subject(item.payload()) != item for item in chosen)
        or any(not isinstance(item, UUID) for item in entity_ids)
        or len(set(entity_ids)) != len(entity_ids)
    ):
        raise ReviewError("review_evidence")
    return chosen


def validate_evidence(
    connection: Connection,
    report: ReviewReport,
    *,
    subjects: Sequence[ReviewSubject] | None = None,
    entity_ids: Sequence[UUID] = (),
) -> ReviewEvidence:
    """Read selected occurrences (all by default), full catalog and exact existing anchors.

    Caller owns schema validation, transaction lifetime and UTC setup. Read committed
    supports a locked writer; repeatable read supports a consistent resolution export.
    Mutable run coverage is retained from the file as unverified context only.
    """
    try:
        selected = _selection(report, subjects, entity_ids)
        return _validate(connection, report, selected, tuple(entity_ids))
    except ComparisonError as error:
        raise ReviewError(
            "review_limit" if error.reason == "comparison_limit" else "review_evidence"
        ) from None
    except AssessmentError:
        raise ReviewError("review_limit") from None
    except ReviewError as error:
        if error.reason in {"review_input", "review_input_io"}:
            raise ReviewError("review_evidence") from None
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, RecursionError):
        raise ReviewError("review_evidence") from None


def _validate(
    connection: Connection,
    report: ReviewReport,
    subjects: tuple[ReviewSubject, ...],
    entity_ids: tuple[UUID, ...],
) -> ReviewEvidence:
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise ReviewError("review_state")
    if connection.execute(
        "SELECT current_setting('transaction_isolation'), current_setting('TimeZone')"
    ).fetchone() not in {("read committed", "UTC"), ("repeatable read", "UTC")}:
        raise ReviewError("review_state")
    if (
        connection.execute(
            "SELECT 1 FROM nima.ingest_runs WHERE run_id=%s AND connector_version=%s "
            "AND normalizer_version=%s",
            (report.cohort.run_id, CONNECTOR_VERSION, NORMALIZER_VERSION),
        ).fetchone()
        is None
    ):
        raise ReviewError("review_evidence")
    anchor_rows = connection.execute(
        """SELECT entity_id,anchor_import_id,registry_number,
        octet_length(to_jsonb(e)::text) FROM nima.identity_entities e
        WHERE entity_id=ANY(%s)""",
        (list(entity_ids),),
    ).fetchall()
    if len(anchor_rows) != len(entity_ids):
        raise ReviewError("review_evidence")
    anchor_keys = [{"import_id": str(row[1]), "registry_number": row[2]} for row in anchor_rows]
    original_imports = tuple(row.import_id for row in report.cohort.imports)
    imports = tuple(
        sorted(
            set(original_imports) | {cast(UUID, row[1]) for row in anchor_rows},
            key=lambda item: item.int,
        )
    )
    selected_registry = sql.SQL(_REGISTRY_SELECTED).format(sql.SQL(_REGISTRY_ROWS))
    registry_parameters = (GEMI_VERSION, list(imports), list(original_imports), Jsonb(anchor_keys))
    count, supported, complete, import_bytes = cast(
        tuple[int, bool, bool, int],
        connection.execute(
            sql.SQL(
                "SELECT count(*),coalesce(bool_and(supported),false),"
                "coalesce(bool_and(complete),false),"
                "coalesce(sum(octet_length(payload::text)),0) FROM ({}) imports"
            ).format(sql.SQL(_IMPORT_ROWS)),
            (*_IMPORT_PARAMETERS, list(imports)),
        ).fetchone(),
    )
    if count != len(imports) or not supported or not complete:
        raise ReviewError("review_evidence")
    count, invalid, registry_bytes = cast(
        tuple[int, int, int],
        connection.execute(
            sql.SQL(
                "SELECT count(*),count(*) FILTER(WHERE valid IS NOT TRUE),"
                "coalesce(sum(octet_length(payload::text)),0) FROM ({}) catalog"
            ).format(selected_registry),
            registry_parameters,
        ).fetchone(),
    )
    if count > MAX_REGISTRY_OBSERVATIONS:
        raise ReviewError("review_limit")
    if invalid:
        raise ReviewError("review_evidence")
    keys = Jsonb(
        [
            {"observation_id": item.observation_id, "role": item.role, "ordinal": item.ordinal}
            for item in subjects
        ]
    )
    party_parameters = (
        keys,
        report.cohort.projection_version,
        report.cohort.run_id,
        CONNECTOR_VERSION,
        NORMALIZER_VERSION,
        NORMALIZER_VERSION,
    )
    parties_query = sql.SQL("WITH selected AS ({}) {}").format(sql.SQL(_KEYS), sql.SQL(_PARTIES))
    count, party_bytes = cast(
        tuple[int, int],
        connection.execute(
            sql.SQL(
                "SELECT count(*),coalesce(sum(octet_length(payload::text)),0) FROM ({}) parties"
            ).format(parties_query),
            party_parameters,
        ).fetchone(),
    )
    if count != len(subjects):
        raise ReviewError("review_evidence")
    ledger_bytes = cast(
        tuple[int],
        connection.execute(
            sql.SQL("""WITH selected AS ({}) SELECT
            (SELECT coalesce(sum(octet_length(to_jsonb(e)::text)),0)
             FROM nima.identity_review_events e JOIN selected s USING(observation_id,role,ordinal)
             WHERE e.projection_version=%s) +
            (SELECT coalesce(sum(octet_length(to_jsonb(h)::text)),0)
             FROM nima.identity_review_heads h JOIN selected s USING(observation_id,role,ordinal)
             WHERE h.projection_version=%s)""").format(sql.SQL(_KEYS)),
            (keys, report.cohort.projection_version, report.cohort.projection_version),
        ).fetchone(),
    )[0]
    total = (
        import_bytes
        + registry_bytes
        + party_bytes
        + ledger_bytes
        + sum(cast(int, row[3]) for row in anchor_rows)
        + 4096
    )
    if total > MAX_INPUT_BYTES:
        raise ReviewError("review_limit")
    # Only bounded source labels/notes can cross the database boundary now.
    raw = connection.execute(parties_query, party_parameters).fetchall()
    actual_parties = tuple(
        _party(cast(dict[str, object], row[0]), report.cohort.run_id) for row in raw
    )
    subject_keys = set(subjects)
    expected = tuple(
        party for party in report.cohort.parties if _subject(report.cohort, party) in subject_keys
    )
    if set(actual_parties) != set(expected):
        raise ReviewError("review_evidence")
    actual_imports = _imports(connection, imports)
    if (
        tuple(item for item in actual_imports if item.import_id in original_imports)
        != report.cohort.imports
    ):
        raise ReviewError("review_evidence")
    # Reuse the strict scalar/date/pointer codec. SQL represents absent 404
    # fields as NULL; the file codec uses an empty map for that same absence.
    registry_rows = connection.execute(
        sql.SQL("SELECT payload FROM ({}) catalog").format(selected_registry), registry_parameters
    ).fetchall()
    actual_registry = tuple(
        sorted(
            (
                _registry(
                    {
                        **cast(dict[str, object], row[0]),
                        "fields": cast(dict[str, object], row[0])["fields"] or {},
                    }
                )
                for row in registry_rows
            ),
            key=lambda item: (item.claim.import_id.int, item.claim.registry_number),
        )
    )
    catalog = tuple(item for item in actual_registry if item.claim.import_id in original_imports)
    if catalog != report.cohort.registry:
        raise ReviewError("review_evidence")
    by_key = {(item.claim.import_id, item.claim.registry_number): item for item in actual_registry}
    anchors = {}
    for row in anchor_rows:
        anchor = by_key.get((cast(UUID, row[1]), cast(str, row[2])))
        if anchor is None or anchor.claim.outcome != "found":
            raise ReviewError("review_evidence")
        anchors[cast(UUID, row[0])] = anchor
    # Policy views are reconstructed from SQL-matched claims; eligibility remains
    # the pure transition layer's job, with anchor union and exact acknowledgment.
    cohort = replace(
        report.cohort,
        parties=tuple(
            sorted(
                actual_parties,
                key=lambda item: (
                    item.source_id,
                    item.normalizer_version,
                    item.content_sha256,
                    item.observation_id,
                    item.role,
                    item.ordinal,
                ),
            )
        ),
        registry=catalog,
    )
    return ReviewEvidence(cohort, MappingProxyType(anchors), total)
