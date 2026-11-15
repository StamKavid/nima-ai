"""Atomic review acceptance and replay on disposable real PostgreSQL."""

from dataclasses import replace
from pathlib import Path
from typing import Never
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.identity import review_evidence, review_store
from nima.identity.review_types import ReviewCandidate, ReviewError, ReviewReport, ReviewRequest
from nima.storage.postgres import Connection
from tests.test_gemi_import import counts as registry_counts
from tests.test_identity_review_evidence import report, seed_report, subject
from tests.test_page_store import counts as source_counts


def request(parsed: ReviewReport, *, entity: UUID | None = None) -> ReviewRequest:
    return ReviewRequest(
        uuid4(),
        "accept",
        subject(parsed, 1),
        ReviewCandidate(parsed.cohort.imports[0].import_id, "1"),
        0,
        "  Ελεγμένο από πηγές\n",
        parsed.sha256,
        entity or uuid4(),
    )


def ledger(dsn: str) -> tuple[int, int, int]:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("""SELECT
            (SELECT count(*) FROM nima.identity_review_heads),
            (SELECT count(*) FROM nima.identity_entities),
            (SELECT count(*) FROM nima.identity_review_events)""").fetchone()
        assert row is not None
        return int(str(row[0])), int(str(row[1])), int(str(row[2]))


def test_invalid_request_is_rejected_before_schema_or_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.identity.review_inputs import decode_report
    from tests.test_identity_review_inputs import report_body

    parsed = decode_report(report_body())
    valid = request(parsed)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Malformed requests must not reach SQL")

    monkeypatch.setattr(review_store, "check_schema", forbidden)
    for changed in (
        replace(valid, rationale=" "),
        replace(valid, expected_revision=True),
        replace(valid, subject=replace(valid.subject, observation_id=True)),
        replace(valid, reverses_event_id=uuid4()),
    ):
        with pytest.raises(ReviewError, match="^review_input$"):
            review_store.review("private-sentinel", changed, report=parsed)


def test_review_requires_explicit_schema_migration(pg_dsn: str) -> None:
    from nima.identity.review_inputs import decode_report
    from tests.test_identity_review_inputs import report_body

    parsed = decode_report(report_body())
    with pytest.raises(ReviewError, match="^review_schema$"):
        review_store.review(pg_dsn, request(parsed), report=parsed)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('nima.identity_review_events')"
        ).fetchone() == (None,)


def test_acceptance_commits_one_event_handle_and_revision_without_source_writes(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    before = source_counts(pg_dsn), registry_counts(pg_dsn)
    ack = review_store.review(pg_dsn, chosen, report=parsed)
    assert ack.event_id == chosen.request_id and ack.entity_id == chosen.entity_id
    assert ack.operation == "accept" and ack.subject_revision == 1 and not ack.replayed
    assert ack.attribution_assurance == "database_principal_only"
    assert ledger(pg_dsn) == (1, 1, 1)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT revision,latest_event_id FROM nima.identity_review_heads"
        ).fetchone() == (1, chosen.request_id)
        assert connection.execute(
            "SELECT entity_id,kind,creating_event_id FROM nima.identity_entities"
        ).fetchone() == (chosen.entity_id, "unclassified", chosen.request_id)
        assert connection.execute(
            "SELECT database_principal=session_user,recorded_at IS NOT NULL,"
            "request_sha256,rationale FROM nima.identity_review_events"
        ).fetchone() == (True, True, chosen.digest, chosen.rationale)
    assert (source_counts(pg_dsn), registry_counts(pg_dsn)) == before


def test_identical_replay_needs_no_report_and_does_not_advance_head(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    first = review_store.review(pg_dsn, chosen, report=parsed)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Committed replay must not revalidate evidence")

    monkeypatch.setattr(review_evidence, "validate_evidence", forbidden)
    again = review_store.review(pg_dsn, chosen)
    assert again == replace(first, replayed=True)
    assert ledger(pg_dsn) == (1, 1, 1)


def append_revoke(connection: Connection, original: ReviewRequest) -> ReviewRequest:
    reversal = ReviewRequest(
        uuid4(),
        "revoke",
        original.subject,
        original.candidate,
        1,
        "Ανάκληση",
        reverses_event_id=original.request_id,
    )
    connection.execute(
        """INSERT INTO nima.identity_review_events
        (event_id,observation_id,projection_version,role,ordinal,subject_revision,
         candidate_import_id,registry_number,operation,reverses_event_id,reversed_operation,
         request_sha256,request_payload,rationale,issues,policy_version)
        VALUES (%s,%s,%s,%s,%s,2,%s,%s,'revoke',%s,'accept',%s,%s,%s,
                ARRAY[]::text[],'reviewed-identity-v1')""",
        (
            reversal.request_id,
            original.subject.observation_id,
            original.subject.projection_version,
            original.subject.role,
            original.subject.ordinal,
            original.candidate.import_id,
            original.candidate.registry_number,
            original.request_id,
            reversal.digest,
            Jsonb(reversal.payload()),
            reversal.rationale,
        ),
    )
    connection.execute(
        "UPDATE nima.identity_review_heads SET revision=2,latest_event_id=%s",
        (reversal.request_id,),
    )
    return reversal


def test_old_acceptance_replay_after_revocation_returns_original_ack_only(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    original = review_store.review(pg_dsn, chosen, report=parsed)
    with psycopg.connect(pg_dsn) as connection:
        reversal = append_revoke(connection, chosen)
    assert review_store.review(pg_dsn, chosen) == replace(original, replayed=True)
    assert ledger(pg_dsn) == (1, 1, 2)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT revision,latest_event_id FROM nima.identity_review_heads"
        ).fetchone() == (2, reversal.request_id)


@pytest.mark.parametrize("fault", ["rationale", "entity", "subject", "report"])
def test_committed_uuid_cannot_be_reused_with_altered_payload(
    pg_dsn: str,
    tmp_path: Path,
    fault: str,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    changed = {
        "rationale": replace(chosen, rationale="Άλλη αιτία"),
        "entity": replace(chosen, entity_id=uuid4()),
        "subject": replace(chosen, subject=subject(parsed, 0)),
        "report": replace(chosen, report_sha256="a" * 64),
    }[fault]
    with pytest.raises(ReviewError, match="^review_conflict$"):
        review_store.review(pg_dsn, changed)
    assert ledger(pg_dsn) == (1, 1, 1)


@pytest.mark.parametrize(
    "fault",
    [
        "stale",
        "missing_report",
        "report_hash",
        "not_found",
        "missing_import",
        "forged_label",
        "subject_hash",
    ],
)
def test_failed_acceptance_leaves_no_head_handle_or_event(
    pg_dsn: str,
    tmp_path: Path,
    fault: str,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    supplied: ReviewReport | None = parsed
    if fault == "stale":
        chosen = replace(chosen, expected_revision=1)
    elif fault == "missing_report":
        supplied = None
    elif fault == "report_hash":
        chosen = replace(chosen, report_sha256="a" * 64)
    elif fault == "not_found":
        chosen = replace(chosen, candidate=replace(chosen.candidate, registry_number="2"))
    elif fault == "missing_import":
        chosen = replace(chosen, candidate=replace(chosen.candidate, import_id=uuid4()))
    elif fault == "subject_hash":
        chosen = replace(chosen, subject=replace(chosen.subject, content_sha256="a" * 64))
    else:
        parties = (
            *parsed.cohort.parties[:1],
            replace(parsed.cohort.parties[1], name="private-sentinel"),
        )
        supplied = report(replace(parsed.cohort, parties=parties))
        chosen = replace(chosen, report_sha256=supplied.sha256)
    with pytest.raises(
        ReviewError, match="^review_conflict$" if fault == "stale" else "^review_evidence$"
    ):
        review_store.review(pg_dsn, chosen, report=supplied)
    assert ledger(pg_dsn) == (0, 0, 0)


def test_active_acceptance_cannot_be_replaced_and_failure_does_not_reserve_uuid(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    other = replace(chosen, request_id=uuid4(), entity_id=uuid4(), expected_revision=1)
    with pytest.raises(ReviewError, match="^review_conflict$"):
        review_store.review(pg_dsn, other, report=parsed)
    assert ledger(pg_dsn) == (1, 1, 1)
    with psycopg.connect(pg_dsn) as connection:
        append_revoke(connection, chosen)
    accepted = review_store.review(
        pg_dsn, replace(other, expected_revision=2, entity_id=chosen.entity_id), report=parsed
    )
    assert accepted.event_id == other.request_id and accepted.subject_revision == 3


def test_exact_anchor_uniqueness_and_explicit_existing_handle_reuse(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    first = seed_report(pg_dsn, tmp_path / "first")
    chosen = request(first)
    review_store.review(pg_dsn, chosen, report=first)
    second = seed_report(pg_dsn, tmp_path / "second")
    shared = report(
        replace(second.cohort, imports=first.cohort.imports, registry=first.cohort.registry)
    )
    another = request(shared)
    with pytest.raises(ReviewError, match="^review_conflict$"):
        review_store.review(pg_dsn, another, report=shared)
    assert ledger(pg_dsn) == (1, 1, 1)
    ack = review_store.review(pg_dsn, replace(another, entity_id=chosen.entity_id), report=shared)
    assert ack.entity_id == chosen.entity_id and ledger(pg_dsn) == (2, 1, 2)


def test_failure_after_entity_insert_rolls_back_and_redacts_driver_details(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)

    def fail(*args: object, **kwargs: object) -> Never:
        raise psycopg.OperationalError("private-sentinel")

    with monkeypatch.context() as patch:
        patch.setattr(review_store, "_append", fail)
        with pytest.raises(ReviewError, match="^review_database$") as error:
            review_store.review(pg_dsn, chosen, report=parsed)
        assert str(error.value) == "review_database"
    assert ledger(pg_dsn) == (0, 0, 0)
    assert not review_store.review(pg_dsn, chosen, report=parsed).replayed
