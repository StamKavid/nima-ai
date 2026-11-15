"""Bounded review views in owned or caller-owned repeatable-read, read-only SQL.

https://www.postgresql.org/docs/17/sql-set-transaction.html
https://www.psycopg.org/psycopg3/docs/basic/transactions.html
"""

from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from nima.identity import AssessmentError, ComparisonError, review_evidence
from nima.identity.registry_cohort import RegistryEvidence, _when
from nima.identity.review_state import MAX_REVIEW_EVENTS, fold_events
from nima.identity.review_store import _historical_request
from nima.identity.review_types import (
    ReviewError,
    ReviewEvent,
    ReviewHead,
    ReviewReport,
    ReviewSubject,
)
from nima.storage.postgres import Connection, MigrationError, _connect, check_schema


@dataclass(frozen=True)
class RecordedEvent:
    event: ReviewEvent
    principal: str
    recorded_at: str
    candidate_provenance: MappingProxyType[str, object]


@dataclass(frozen=True)
class EntityAnchor:
    entity_id: UUID
    creating_event_id: UUID
    evidence: RegistryEvidence


@dataclass(frozen=True)
class ResolutionSnapshot:
    report: ReviewReport
    heads: tuple[ReviewHead, ...]
    events: tuple[RecordedEvent, ...]
    entities: tuple[EntityAnchor, ...]
    input_bytes: int


def read_snapshot(
    dsn: str, report: ReviewReport, *, max_events: int = MAX_REVIEW_EVENTS
) -> ResolutionSnapshot:
    subjects = _subjects(report, max_events)
    try:
        check_schema(dsn)
        with _connect(dsn) as connection, connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            result = _read(connection, report, subjects, max_events)
        return result
    except MigrationError:
        raise ReviewError("review_schema") from None
    except psycopg.errors.InsufficientPrivilege:
        raise ReviewError("review_permission") from None
    except (psycopg.Error, ValueError):
        raise ReviewError("review_database") from None
    except AssessmentError:
        raise ReviewError("review_limit") from None


def read_snapshot_in_transaction(
    connection: Connection, report: ReviewReport, *, max_events: int = MAX_REVIEW_EVENTS
) -> ResolutionSnapshot:
    """Read without owning the caller's connection or active SQL transaction.

    The caller owns schema checks, RR/read-only/UTC setup, connection lifetime
    and database-exception translation. Invalid input is rejected before SQL;
    an unsupported transaction raises the fixed review_state failure.
    """
    return _read(connection, report, _subjects(report, max_events), max_events)


def _subjects(report: ReviewReport, max_events: int) -> tuple[ReviewSubject, ...]:
    if type(max_events) is not int or not 1 <= max_events <= MAX_REVIEW_EVENTS:
        raise ValueError("review_configuration")
    try:
        return review_evidence._selection(report, None, ())
    except AssessmentError:
        raise ReviewError("review_limit") from None
    except ReviewError as error:
        if error.reason in {"review_input", "review_input_io"}:
            raise ReviewError("review_evidence") from None
        raise
    except (ComparisonError, TypeError, ValueError, KeyError, AttributeError):
        raise ReviewError("review_evidence") from None


def _read(
    connection: Connection,
    report: ReviewReport,
    subjects: tuple[ReviewSubject, ...],
    max_events: int,
) -> ResolutionSnapshot:
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise ReviewError("review_state")
    if connection.execute(
        "SELECT current_setting('transaction_isolation'),"
        "current_setting('transaction_read_only'),current_setting('TimeZone')"
    ).fetchone() != ("repeatable read", "on", "UTC"):
        raise ReviewError("review_state")
    keys = Jsonb(
        [
            {"observation_id": item.observation_id, "role": item.role, "ordinal": item.ordinal}
            for item in subjects
        ]
    )
    parameters = (keys, report.cohort.projection_version)
    # Attribute/time fields are already included in the validator's full event
    # row budget. Reserve the additional terminal provenance before any labels.
    count, found, extra = cast(
        tuple[int, int, int],
        connection.execute(
            sql.SQL("""
        WITH selected AS ({}) SELECT count(*),count(o.run_id),
            coalesce(sum(octet_length(jsonb_build_object('candidate_evidence',to_jsonb(o))::text)),0)
        FROM nima.identity_review_events e JOIN selected s USING(observation_id,role,ordinal)
        LEFT JOIN nima.gemi_observations o ON o.run_id=e.candidate_import_id
            AND o.registry_number=e.registry_number WHERE e.projection_version=%s""").format(
                sql.SQL(review_evidence._KEYS)
            ),
            parameters,
        ).fetchone(),
    )
    if count > max_events:
        raise ReviewError("review_limit")
    if found != count:
        raise ReviewError("review_evidence")
    rows = connection.execute(
        sql.SQL("""WITH selected AS ({}) SELECT DISTINCT e.entity_id
        FROM nima.identity_review_events e JOIN selected s USING(observation_id,role,ordinal)
        WHERE e.projection_version=%s AND e.entity_id IS NOT NULL LIMIT 101""").format(
            sql.SQL(review_evidence._KEYS)
        ),
        parameters,
    ).fetchall()
    entities = tuple(cast(UUID, row[0]) for row in rows)
    checked = review_evidence.validate_evidence(
        connection, report, entity_ids=entities, reserve_bytes=extra
    )
    rows = connection.execute(
        sql.SQL("""WITH selected AS ({}) SELECT to_jsonb(e),to_jsonb(o)
        FROM nima.identity_review_events e JOIN selected s USING(observation_id,role,ordinal)
        JOIN nima.gemi_observations o ON o.run_id=e.candidate_import_id
            AND o.registry_number=e.registry_number WHERE e.projection_version=%s
        ORDER BY e.observation_id,e.role,e.ordinal,e.subject_revision LIMIT %s""").format(
            sql.SQL(review_evidence._KEYS)
        ),
        (*parameters, max_events + 1),
    ).fetchall()
    if len(rows) != count:
        raise ReviewError("review_state")
    known = frozenset(subjects)
    events = tuple(_record(row[0], row[1], known) for row in rows)
    by_subject: dict[ReviewSubject, list[ReviewEvent]] = defaultdict(list)
    for recorded in events:
        by_subject[recorded.event.request.subject].append(recorded.event)
    rows = connection.execute(
        sql.SQL("""WITH selected AS ({}) SELECT to_jsonb(h)
        FROM nima.identity_review_heads h JOIN selected s USING(observation_id,role,ordinal)
        WHERE h.projection_version=%s""").format(sql.SQL(review_evidence._KEYS)),
        parameters,
    ).fetchall()
    stored = {}
    for row in rows:
        data = cast(dict[str, object], row[0])
        key = data["observation_id"], data["role"], data["ordinal"]
        stored[key] = data
    heads = []
    for subject in subjects:
        history = by_subject[subject]
        head = fold_events(subject, history)
        stored_head = stored.get((subject.observation_id, subject.role, subject.ordinal))
        if stored_head is None:
            if history:
                raise ReviewError("review_state")
        else:
            expected = {
                **subject.payload(),
                "revision": head.revision,
                "latest_event_id": str(history[-1].event_id) if history else None,
            }
            if stored_head != expected:
                raise ReviewError("review_state")
        heads.append(head)
    rows = connection.execute(
        "SELECT entity_id,creating_event_id,kind FROM nima.identity_entities "
        "WHERE entity_id=ANY(%s)",
        (list(entities),),
    ).fetchall()
    if len(rows) != len(entities) or any(row[2] != "unclassified" for row in rows):
        raise ReviewError("review_state")
    anchors = tuple(
        sorted(
            (
                EntityAnchor(
                    cast(UUID, row[0]), cast(UUID, row[1]), checked.anchors[cast(UUID, row[0])]
                )
                for row in rows
            ),
            key=lambda item: item.entity_id.int,
        )
    )
    heads.sort(
        key=lambda item: (
            item.subject.source_id,
            item.subject.normalizer_version,
            item.subject.content_sha256,
            item.subject.observation_id,
            item.subject.role,
            item.subject.ordinal,
        )
    )
    order = {head.subject: index for index, head in enumerate(heads)}
    ordered = tuple(
        sorted(
            events,
            key=lambda item: (order[item.event.request.subject], item.event.subject_revision),
        )
    )
    return ResolutionSnapshot(report, tuple(heads), ordered, anchors, checked.input_bytes)


def _record(value: object, provenance: object, subjects: frozenset[ReviewSubject]) -> RecordedEvent:
    try:
        if not isinstance(value, dict) or not isinstance(provenance, dict):
            raise ReviewError("review_state")
        data = cast(dict[str, object], value)
        event_id = UUID(cast(str, data["event_id"]))
        policy = cast(str, data["policy_version"])
        request = _historical_request(event_id, data["request_payload"], policy)
        expected = {
            "operation": request.operation,
            "entity_id": str(request.entity_id) if request.entity_id else None,
            "observation_id": request.subject.observation_id,
            "projection_version": request.subject.projection_version,
            "role": request.subject.role,
            "ordinal": request.subject.ordinal,
            "candidate_import_id": str(request.candidate.import_id),
            "registry_number": request.candidate.registry_number,
            "report_sha256": request.report_sha256,
            "rationale": request.rationale,
            "request_sha256": request.digest,
            "reverses_event_id": str(request.reverses_event_id)
            if request.reverses_event_id
            else None,
        }
        if request.subject not in subjects or any(
            data[key] != item for key, item in expected.items()
        ):
            raise ReviewError("review_state")
        if (
            provenance["run_id"] != str(request.candidate.import_id)
            or provenance["registry_number"] != request.candidate.registry_number
            or provenance["outcome"] != "found"
            or provenance["status"] != 200
        ):
            raise ReviewError("review_evidence")
        principal = data["database_principal"]
        if not isinstance(principal, str) or not principal:
            raise ReviewError("review_state")
        event = ReviewEvent(
            request,
            cast(int, data["subject_revision"]),
            tuple(cast(list[str], data["issues"])),
            policy,
        )
        return RecordedEvent(
            event,
            principal,
            _when(data["recorded_at"]),
            MappingProxyType(cast(dict[str, object], provenance)),
        )
    except (KeyError, TypeError, ValueError, AssessmentError, ComparisonError):
        raise ReviewError("review_state") from None
    except ReviewError as error:
        if error.reason in {"review_input", "review_input_io"}:
            raise ReviewError("review_state") from None
        raise
