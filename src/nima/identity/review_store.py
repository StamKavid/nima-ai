"""Owned atomic review transactions; no implicit migration, file or source access.

https://www.postgresql.org/docs/17/transaction-iso.html#XACT-READ-COMMITTED
https://www.psycopg.org/psycopg3/docs/basic/transactions.html
"""

from dataclasses import replace
from typing import cast
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from nima.identity import AssessmentError, review_evidence
from nima.identity.artifacts import encode
from nima.identity.review_inputs import decode_request
from nima.identity.review_state import MAX_REVIEW_EVENTS, fold_events, propose
from nima.identity.review_types import (
    MAX_REQUEST_BYTES,
    REVIEW_POLICY_VERSION,
    ReviewAcknowledgment,
    ReviewAnchor,
    ReviewError,
    ReviewEvent,
    ReviewOperation,
    ReviewReport,
    ReviewRequest,
    ReviewSubject,
)
from nima.storage.postgres import Connection, MigrationError, _connect, check_schema

_WHERE = sql.SQL("observation_id=%s AND projection_version=%s AND role=%s AND ordinal=%s")


def _key(subject: ReviewSubject) -> tuple[int, str, str, int]:
    return subject.observation_id, subject.projection_version, subject.role, subject.ordinal


def _request(request: ReviewRequest) -> None:
    try:
        if decode_request(request.request_id, encode(request.payload())) != request:
            raise ReviewError("review_input")
    except AssessmentError:
        raise ReviewError("review_limit") from None
    except (AttributeError, TypeError, ValueError, RecursionError):
        raise ReviewError("review_input") from None


def review(
    dsn: str, request: ReviewRequest, *, report: ReviewReport | None = None
) -> ReviewAcknowledgment:
    """Commit an explicit accept/reject/revoke or replay its original receipt.

    Evidence views are never accepted as authorization. This function always
    validates new evidence inside its own locked read-committed transaction.
    No acknowledgment is returned until COMMIT has completed successfully.
    """
    _request(request)
    try:
        check_schema(dsn)
        with _connect(dsn) as connection, connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            acknowledgment = _replay(connection, request)
            if acknowledgment is None:
                head = _lock(connection, request.subject)
                # A waiting same-request writer needs a fresh statement after
                # the winner's lock/commit, before checking the stale revision.
                acknowledgment = _replay(connection, request)
                if acknowledgment is None:
                    acknowledgment = _apply(connection, request, report, head)
        return acknowledgment
    except MigrationError:
        raise ReviewError("review_schema") from None
    except psycopg.errors.InsufficientPrivilege:
        raise ReviewError("review_permission") from None
    except (psycopg.IntegrityError, psycopg.errors.LockNotAvailable):
        raise ReviewError("review_conflict") from None
    except (psycopg.Error, ValueError):
        raise ReviewError("review_database") from None


def _replay(connection: Connection, request: ReviewRequest) -> ReviewAcknowledgment | None:
    row = connection.execute(
        """SELECT request_sha256=%s AND request_payload=%s
            AND database_principal=session_user,
        observation_id,projection_version,role,ordinal,subject_revision,operation,entity_id
        FROM nima.identity_review_events WHERE event_id=%s""",
        (request.digest, Jsonb(request.payload()), request.request_id),
    ).fetchone()
    if row is None:
        return None
    if row[0] is not True:
        raise ReviewError("review_conflict")
    if (
        row[1:5] != _key(request.subject)
        or row[5] != request.expected_revision + 1
        or row[6] != request.operation
        or row[7] != request.entity_id
    ):
        raise ReviewError("review_state")
    return ReviewAcknowledgment(
        request.request_id, row[5], request.operation, request.entity_id, True
    )


def _lock(connection: Connection, subject: ReviewSubject) -> tuple[int, UUID | None]:
    try:
        connection.execute(
            """INSERT INTO nima.identity_review_heads
        (observation_id,projection_version,role,ordinal,run_id,source_id,
         normalizer_version,content_sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (observation_id,projection_version,role,ordinal) DO NOTHING""",
            (
                *_key(subject),
                subject.run_id,
                subject.source_id,
                subject.normalizer_version,
                subject.content_sha256,
            ),
        )
    except (psycopg.errors.ForeignKeyViolation, psycopg.errors.CheckViolation):
        raise ReviewError("review_evidence") from None
    row = connection.execute(
        sql.SQL(
            "SELECT run_id,source_id,normalizer_version,content_sha256,"
            "revision,latest_event_id FROM nima.identity_review_heads WHERE {} FOR UPDATE"
        ).format(_WHERE),
        _key(subject),
    ).fetchone()
    if row is None or row[:4] != (
        subject.run_id,
        subject.source_id,
        subject.normalizer_version,
        subject.content_sha256,
    ):
        raise ReviewError("review_evidence")
    return cast(int, row[4]), cast(UUID | None, row[5])


def _historical_request(event_id: UUID, payload: object, policy: str) -> ReviewRequest:
    if not isinstance(payload, dict):
        raise ReviewError("review_state")
    body = encode(payload)
    if len(body) > MAX_REQUEST_BYTES:
        raise ReviewError("review_state")
    # Historical issue labels remain revocable without today's eligibility
    # policy. Validate their envelope, preserving the original ordered codes.
    issues = payload.get("acknowledged_issues")
    legacy = policy != REVIEW_POLICY_VERSION and payload.get("operation") == "accept"
    request = decode_request(
        event_id, encode({**payload, "acknowledged_issues": []} if legacy else payload)
    )
    if legacy:
        if not isinstance(issues, list) or any(not isinstance(item, str) for item in issues):
            raise ReviewError("review_state")
        request = replace(request, acknowledged_issues=tuple(cast(list[str], issues)))
    if encode(request.payload()) != body:
        raise ReviewError("review_state")
    return request


def _events(connection: Connection, subject: ReviewSubject) -> tuple[ReviewEvent, ...]:
    count, size = cast(
        tuple[int, int],
        connection.execute(
            sql.SQL(
                "SELECT count(*),coalesce(sum(octet_length(to_jsonb(e)::text)),0) "
                "FROM nima.identity_review_events e WHERE {}"
            ).format(_WHERE),
            _key(subject),
        ).fetchone(),
    )
    if count > MAX_REVIEW_EVENTS or size + 4096 > review_evidence.MAX_INPUT_BYTES:
        raise ReviewError("review_limit")
    rows = connection.execute(
        sql.SQL("""SELECT event_id,request_payload,request_sha256,
        subject_revision,operation,entity_id,candidate_import_id,registry_number,
        report_sha256,rationale,reverses_event_id,issues,policy_version
        FROM nima.identity_review_events WHERE {} ORDER BY subject_revision LIMIT %s""").format(
            _WHERE
        ),
        (*_key(subject), MAX_REVIEW_EVENTS + 1),
    ).fetchall()
    if len(rows) != count:
        raise ReviewError("review_state")
    events = []
    try:
        for row in rows:
            event_id, policy = cast(UUID, row[0]), cast(str, row[12])
            request = _historical_request(event_id, row[1], policy)
            if (
                request.subject != subject
                or request.digest != row[2]
                or (
                    request.operation,
                    request.entity_id,
                    request.candidate.import_id,
                    request.candidate.registry_number,
                    request.report_sha256,
                    request.rationale,
                    request.reverses_event_id,
                )
                != row[4:11]
            ):
                raise ReviewError("review_state")
            events.append(
                ReviewEvent(request, cast(int, row[3]), tuple(cast(list[str], row[11])), policy)
            )
    except (ReviewError, AssessmentError, TypeError, ValueError, KeyError):
        raise ReviewError("review_state") from None
    return tuple(events)


def _apply(
    connection: Connection,
    request: ReviewRequest,
    report: ReviewReport | None,
    head: tuple[int, UUID | None],
) -> ReviewAcknowledgment:
    if request.expected_revision != head[0]:
        raise ReviewError("review_conflict")
    existing = False
    checked = None
    if request.operation != "revoke":
        if report is None or report.sha256 != request.report_sha256:
            raise ReviewError("review_evidence")
        if request.operation == "accept":
            existing = (
                connection.execute(
                    "SELECT 1 FROM nima.identity_entities WHERE entity_id=%s", (request.entity_id,)
                ).fetchone()
                is not None
            )
        checked = review_evidence.validate_evidence(
            connection,
            report,
            subjects=(request.subject,),
            entity_ids=(cast(UUID, request.entity_id),) if existing else (),
        )
    events = _events(connection, request.subject)
    folded = fold_events(request.subject, events)
    if (folded.revision, events[-1].event_id if events else None) != head:
        raise ReviewError("review_state")
    anchor = (
        ReviewAnchor(
            cast(UUID, request.entity_id), checked.anchors[cast(UUID, request.entity_id)].claim
        )
        if existing and checked is not None
        else None
    )
    event = propose(
        request, events, cohort=checked.cohort if checked is not None else None, anchor=anchor
    )
    if request.operation == "accept" and not existing:
        connection.execute(
            """INSERT INTO nima.identity_entities
            (entity_id,anchor_import_id,registry_number,creating_event_id)
            VALUES (%s,%s,%s,%s)""",
            (
                request.entity_id,
                request.candidate.import_id,
                request.candidate.registry_number,
                request.request_id,
            ),
        )
    reversed_operation = (
        next(
            (
                prior.request.operation
                for prior in events
                if prior.event_id == request.reverses_event_id
            ),
            None,
        )
        if request.operation == "revoke"
        else None
    )
    _append(connection, event, reversed_operation=reversed_operation)
    return ReviewAcknowledgment(
        event.event_id, event.subject_revision, request.operation, request.entity_id, False
    )


def _append(
    connection: Connection,
    event: ReviewEvent,
    *,
    reversed_operation: ReviewOperation | None = None,
) -> None:
    request = event.request
    connection.execute(
        """INSERT INTO nima.identity_review_events
        (event_id,observation_id,projection_version,role,ordinal,subject_revision,
         candidate_import_id,registry_number,operation,entity_id,request_sha256,
         request_payload,report_sha256,rationale,issues,policy_version,
         reverses_event_id,reversed_operation,database_principal)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,session_user)""",
        (
            request.request_id,
            *_key(request.subject),
            event.subject_revision,
            request.candidate.import_id,
            request.candidate.registry_number,
            request.operation,
            request.entity_id,
            request.digest,
            Jsonb(request.payload()),
            request.report_sha256,
            request.rationale,
            list(event.issues),
            event.policy_version,
            request.reverses_event_id,
            reversed_operation,
        ),
    )
    row = connection.execute(
        sql.SQL(
            "UPDATE nima.identity_review_heads SET revision=%s,latest_event_id=%s "
            "WHERE {} AND revision=%s RETURNING revision"
        ).format(_WHERE),
        (event.subject_revision, event.event_id, *_key(request.subject), request.expected_revision),
    ).fetchone()
    if row != (event.subject_revision,):
        raise ReviewError("review_conflict")
