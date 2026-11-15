"""Reject/revoke preserve independent pair states and never resurrect acceptance."""

from dataclasses import replace
from pathlib import Path
from typing import Never
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.identity import review_evidence, review_store
from nima.identity.registry_cohort import read_comparison_cohort
from nima.identity.review_inputs import decode_report
from nima.identity.review_state import fold_events
from nima.identity.review_types import ReviewError, ReviewEvent, ReviewOperation, ReviewRequest
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import Connection
from tests.test_identity_review_accept import ledger, request
from tests.test_identity_review_evidence import report, seed_report
from tests.test_identity_review_inputs import report_body
from tests.test_identity_review_schema import head
from tests.test_registry_cohort import registry_import


def revoke(previous: ReviewRequest, revision: int) -> ReviewRequest:
    return ReviewRequest(
        uuid4(),
        "revoke",
        previous.subject,
        previous.candidate,
        revision,
        "Ανάκληση μετά από έλεγχο",
        reverses_event_id=previous.request_id,
    )


@pytest.mark.parametrize("operation", ["reject", "revoke"])
def test_non_accept_operations_pass_strict_request_validation(operation: str) -> None:
    valid = request(decode_report(report_body()))
    selected = (
        replace(valid, operation="reject", entity_id=None)
        if operation == "reject"
        else revoke(valid, 1)
    )
    review_store._request(selected)


def test_reject_revoke_then_explicit_acceptance_preserves_all_history(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    rejection = replace(chosen, operation="reject", entity_id=None)
    first = review_store.review(pg_dsn, rejection, report=parsed)
    assert first.operation == "reject" and first.entity_id is None and ledger(pg_dsn) == (1, 0, 1)
    reversal = revoke(rejection, 1)
    second = review_store.review(pg_dsn, reversal)
    assert (
        second.subject_revision == 2
        and second.operation == "revoke"
        and ledger(pg_dsn) == (1, 0, 2)
    )
    acceptance = replace(chosen, request_id=uuid4(), expected_revision=2)
    review_store.review(pg_dsn, acceptance, report=parsed)
    assert ledger(pg_dsn) == (1, 1, 3)
    with psycopg.connect(pg_dsn) as connection:
        folded = fold_events(chosen.subject, review_store._events(connection, chosen.subject))
        assert folded.accepted_entity_id == chosen.entity_id and folded.revision == 3
    assert review_store.review(pg_dsn, rejection).replayed
    assert review_store.review(pg_dsn, reversal).replayed
    assert ledger(pg_dsn) == (1, 1, 3)


def test_acceptance_revokes_without_report_or_new_source_validation(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    accepted = review_store.review(pg_dsn, chosen, report=parsed)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Revoke/replay must not revalidate source eligibility")

    monkeypatch.setattr(review_evidence, "validate_evidence", forbidden)
    reversal = revoke(chosen, 1)
    undone = review_store.review(pg_dsn, reversal)
    assert undone.subject_revision == 2 and undone.entity_id is None
    assert review_store.review(pg_dsn, chosen) == replace(accepted, replayed=True)
    with psycopg.connect(pg_dsn) as connection:
        folded = fold_events(chosen.subject, review_store._events(connection, chosen.subject))
        assert folded.accepted_entity_id is None and folded.pairs[0].state == "unreviewed"
    assert ledger(pg_dsn) == (1, 1, 2)


def test_other_candidate_rejection_and_revocation_keep_the_accepted_pair(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    another = registry_import(pg_dsn, tmp_path / "another")
    parsed = report(
        read_comparison_cohort(
            pg_dsn,
            parsed.cohort.run_id,
            (parsed.cohort.imports[0].import_id, another),
            PROJECTION_VERSION,
        )
    )
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    other_import = next(
        item.import_id
        for item in parsed.cohort.imports
        if item.import_id != chosen.candidate.import_id
    )
    rejection = replace(
        chosen,
        request_id=uuid4(),
        operation="reject",
        entity_id=None,
        candidate=replace(chosen.candidate, import_id=other_import),
        expected_revision=1,
    )
    review_store.review(pg_dsn, rejection, report=parsed)
    review_store.review(pg_dsn, revoke(rejection, 2))
    with psycopg.connect(pg_dsn) as connection:
        folded = fold_events(chosen.subject, review_store._events(connection, chosen.subject))
        assert folded.accepted_entity_id == chosen.entity_id
        assert {pair.state for pair in folded.pairs} == {"accepted", "unreviewed"}
    assert ledger(pg_dsn) == (1, 1, 3)


@pytest.mark.parametrize("fault", ["wrong_event", "wrong_candidate", "stale", "reject_active"])
def test_wrong_reversals_and_direct_rejection_of_active_acceptance_roll_back(
    pg_dsn: str,
    tmp_path: Path,
    fault: str,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    attempted = revoke(chosen, 1)
    if fault == "wrong_event":
        attempted = replace(attempted, reverses_event_id=uuid4())
    elif fault == "wrong_candidate":
        attempted = replace(attempted, candidate=replace(chosen.candidate, import_id=uuid4()))
    elif fault == "stale":
        attempted = replace(attempted, expected_revision=0)
    else:
        attempted = replace(
            chosen, request_id=uuid4(), operation="reject", entity_id=None, expected_revision=1
        )
    with pytest.raises(ReviewError, match="^review_conflict$"):
        review_store.review(pg_dsn, attempted, report=parsed)
    assert ledger(pg_dsn) == (1, 1, 1)


def test_superseded_or_already_revoked_decision_cannot_be_revived(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    rejection = replace(request(parsed), operation="reject", entity_id=None)
    review_store.review(pg_dsn, rejection, report=parsed)
    newer = replace(rejection, request_id=uuid4(), expected_revision=1, rationale="Νέος έλεγχος")
    review_store.review(pg_dsn, newer, report=parsed)
    with pytest.raises(ReviewError, match="^review_conflict$"):
        review_store.review(pg_dsn, revoke(rejection, 2))
    reversal = revoke(newer, 2)
    review_store.review(pg_dsn, reversal)
    assert review_store.review(pg_dsn, reversal).replayed
    with pytest.raises(ReviewError, match="^review_conflict$"):
        review_store.review(pg_dsn, replace(reversal, request_id=uuid4(), expected_revision=3))
    assert ledger(pg_dsn) == (1, 0, 3)


def test_historical_policy_issues_remain_revocable_without_current_eligibility(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = replace(request(parsed), acknowledged_issues=("legacy_issue",))
    with psycopg.connect(pg_dsn) as connection:
        head(connection, chosen.subject.run_id, role="supplier")
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) "
            "VALUES (%s,%s,'1',%s)",
            (chosen.entity_id, chosen.candidate.import_id, chosen.request_id),
        )
        connection.execute(
            """INSERT INTO nima.identity_review_events
            (event_id,observation_id,projection_version,role,ordinal,subject_revision,
             candidate_import_id,registry_number,operation,entity_id,request_sha256,
             request_payload,report_sha256,rationale,issues,policy_version)
            VALUES (%s,%s,%s,'supplier',0,1,%s,'1','accept',%s,%s,%s,%s,%s,
                    ARRAY['legacy_issue'],'reviewed-identity-v0')""",
            (
                chosen.request_id,
                chosen.subject.observation_id,
                chosen.subject.projection_version,
                chosen.candidate.import_id,
                chosen.entity_id,
                chosen.digest,
                Jsonb(chosen.payload()),
                chosen.report_sha256,
                chosen.rationale,
            ),
        )
        connection.execute(
            "UPDATE nima.identity_review_heads SET revision=1,latest_event_id=%s",
            (chosen.request_id,),
        )

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Legacy revocation must use stored history only")

    monkeypatch.setattr(review_evidence, "validate_evidence", forbidden)
    reversal = revoke(chosen, 1)
    review_store.review(pg_dsn, reversal)
    with psycopg.connect(pg_dsn) as connection:
        folded = fold_events(chosen.subject, review_store._events(connection, chosen.subject))
        assert folded.accepted_entity_id is None
        assert connection.execute(
            "SELECT issues,policy_version FROM nima.identity_review_events WHERE event_id=%s",
            (reversal.request_id,),
        ).fetchone() == (["legacy_issue"], "reviewed-identity-v1")
        assert connection.execute(
            "SELECT request_sha256,policy_version FROM nima.identity_review_events "
            "WHERE event_id=%s",
            (chosen.request_id,),
        ).fetchone() == (chosen.digest, "reviewed-identity-v0")


def test_revoke_failure_after_sql_writes_rolls_back_both_event_and_head(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    original = review_store._append

    def after_append(
        connection: Connection,
        event: ReviewEvent,
        *,
        reversed_operation: ReviewOperation | None = None,
    ) -> None:
        original(connection, event, reversed_operation=reversed_operation)
        raise psycopg.OperationalError("private-sentinel")

    with monkeypatch.context() as patch:
        patch.setattr(review_store, "_append", after_append)
        with pytest.raises(ReviewError, match="^review_database$"):
            review_store.review(pg_dsn, revoke(chosen, 1))
    assert ledger(pg_dsn) == (1, 1, 1)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT revision FROM nima.identity_review_heads").fetchone() == (
            1,
        )
