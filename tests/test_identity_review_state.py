"""Human review transitions are explicit, reversible and local to one occurrence."""

import hashlib
from dataclasses import replace
from uuid import UUID

import pytest

from nima.identity import review_state
from nima.identity.artifacts import encode
from nima.identity.registry_cohort import ComparisonCohort
from nima.identity.registry_report import build_report
from nima.identity.review_inputs import decode_report, decode_request
from nima.identity.review_types import ReviewError, ReviewRequest
from tests.test_identity_review_inputs import report_body, request


def context() -> ComparisonCohort:
    return decode_report(report_body()).cohort


def command(
    operation: str = "accept",
    revision: int = 0,
    identifier: int = 30,
    selected: int = 1,
    *,
    evidence: ComparisonCohort | None = None,
) -> ReviewRequest:
    source = context() if evidence is None else evidence
    party = source.parties[0]
    data = request(operation)
    data["subject"] = {
        "run_id": str(source.run_id),
        "observation_id": party.observation_id,
        "projection_version": source.projection_version,
        "source_id": party.source_id,
        "normalizer_version": party.normalizer_version,
        "content_sha256": party.content_sha256,
        "role": party.role,
        "ordinal": party.ordinal,
    }
    data["candidate"] = {"import_id": str(UUID(int=selected)), "registry_number": "1"}
    data["expected_revision"] = revision
    if operation != "revoke":
        data["report_sha256"] = hashlib.sha256(encode(build_report(source))).hexdigest()
    if operation == "accept":
        data["acknowledged_issues"] = ["reported_afm_changed_for_registry_number"]
    return decode_request(UUID(int=identifier), encode(data))


def test_accept_reject_other_candidate_revoke_and_no_resurrection() -> None:
    first = command()
    accepted = review_state.propose(first, (), cohort=context())
    assert accepted.event_id == first.request_id and accepted.subject_revision == 1
    assert accepted.issues == ("reported_afm_changed_for_registry_number",)
    rejected = review_state.propose(command("reject", 1, 31, 3), (accepted,), cohort=context())
    head = review_state.fold_events(first.subject, (accepted, rejected))
    assert head.accepted_entity_id == first.entity_id and head.revision == 2
    revoke = replace(command("revoke", 2, 32), reverses_event_id=accepted.event_id)
    revoked = review_state.propose(revoke, (accepted, rejected))
    history = accepted, rejected, revoked
    head = review_state.fold_events(first.subject, history)
    assert head.accepted_entity_id is None and head.automatic_identity_links == 0
    assert [(pair.state, pair.entity_id) for pair in head.pairs] == [
        ("unreviewed", None),
        ("rejected", None),
    ]
    assert revoked.issues == accepted.issues and rejected.request.entity_id is None
    with pytest.raises(ReviewError):
        review_state.propose(replace(revoke, request_id=UUID(int=33), expected_revision=3), history)
    assert accepted.request == first


@pytest.mark.parametrize("operation,selected", [("accept", 1), ("reject", 1), ("accept", 3)])
def test_active_acceptance_cannot_be_replaced_or_rejected(operation: str, selected: int) -> None:
    accepted = review_state.propose(command(), (), cohort=context())
    with pytest.raises(ReviewError, match="^review_conflict$"):
        review_state.propose(command(operation, 1, 31, selected), (accepted,), cohort=context())


def test_stale_revision_wrong_pair_and_duplicate_request_do_not_apply() -> None:
    accepted = review_state.propose(command(), (), cohort=context())
    for candidate in (
        command("reject", 0, 31, 3),
        command("revoke", 1, 31, 3),
        replace(command("revoke", 1, 32), reverses_event_id=UUID(int=999)),
    ):
        with pytest.raises(ReviewError, match="^review_conflict$"):
            review_state.propose(candidate, (accepted,), cohort=context())
    with pytest.raises(ReviewError):
        review_state.propose(command(), (accepted,), cohort=context())


def test_existing_outside_anchor_cannot_hide_changed_afm() -> None:
    from nima.identity.registry_policy import RegistryObservation
    from nima.identity.review_types import ReviewAnchor

    base = context()
    one = replace(base, imports=base.imports[:1], registry=base.registry[:1])
    new = replace(command(evidence=one), acknowledged_issues=())
    assert review_state.propose(new, (), cohort=one).issues == ()
    anchor = ReviewAnchor(
        new.entity_id or UUID(int=3), RegistryObservation(UUID(int=99), "1", "found", "123456789")
    )
    with pytest.raises(ReviewError, match="^review_evidence$"):
        review_state.propose(new, (), cohort=one, anchor=anchor)
    acknowledged = replace(new, acknowledged_issues=("reported_afm_changed_for_registry_number",))
    assert (
        review_state.propose(acknowledged, (), cohort=one, anchor=anchor).issues
        == acknowledged.acknowledged_issues
    )
    same = replace(anchor, observation=one.registry[0].claim)
    assert review_state.propose(new, (), cohort=one, anchor=same).issues == ()
    for invalid in (
        replace(anchor, entity_id=UUID(int=500)),
        replace(anchor, observation=replace(anchor.observation, registry_number="2")),
        replace(
            anchor,
            observation=replace(
                anchor.observation, outcome="not_found_at_observation", reported_afm=None
            ),
        ),
        replace(anchor, observation=replace(one.registry[0].claim, reported_afm="123456789")),
    ):
        with pytest.raises(ReviewError, match="^review_evidence$"):
            review_state.propose(acknowledged, (), cohort=one, anchor=invalid)
    # An outside anchor cannot become a candidate absent from the report selection.
    outside = replace(
        acknowledged, candidate=replace(acknowledged.candidate, import_id=UUID(int=99))
    )
    with pytest.raises(ReviewError, match="^review_evidence$"):
        review_state.propose(outside, (), cohort=one, anchor=anchor)


def test_legacy_policy_can_be_revoked_without_report_or_current_eligibility() -> None:
    accepted = review_state.propose(command(), (), cohort=context())
    legacy = replace(
        accepted,
        policy_version="historical-policy",
        issues=("legacy_issue",),
        request=replace(accepted.request, acknowledged_issues=()),
    )
    revoke = replace(command("revoke", 1, 31), reverses_event_id=legacy.event_id)
    event = review_state.propose(revoke, (legacy,))
    assert event.issues == ("legacy_issue",)
    assert review_state.fold_events(revoke.subject, (legacy, event)).accepted_entity_id is None


def test_rejection_supersession_and_revocation_never_restore_an_old_decision() -> None:
    first = review_state.propose(command("reject"), (), cohort=context())
    second = review_state.propose(command("reject", 1, 31), (first,), cohort=context())
    accepted = review_state.propose(command("accept", 2, 32), (first, second), cohort=context())
    prefix = first, second, accepted
    old = review_state.fold_events(first.request.subject, prefix)
    revoke = replace(command("revoke", 3, 33), reverses_event_id=accepted.event_id)
    event = review_state.propose(revoke, prefix)
    assert review_state.fold_events(revoke.subject, (*prefix, event)).pairs[0].state == "unreviewed"
    assert old.accepted_entity_id == accepted.request.entity_id and old.revision == 3
    assert first.request.operation == second.request.operation == "reject"


def test_revoke_other_rejection_preserves_acceptance_and_scope() -> None:
    first = review_state.propose(command(), (), cohort=context())
    second = review_state.propose(command("reject", 1, 31, 3), (first,), cohort=context())
    revoke = replace(command("revoke", 2, 32, 3), reverses_event_id=second.event_id)
    event = review_state.propose(revoke, (first, second))
    head = review_state.fold_events(revoke.subject, (first, second, event))
    assert head.accepted_entity_id == first.request.entity_id
    other = replace(revoke.subject, observation_id=2)
    assert review_state.fold_events(other, ()).accepted_entity_id is None
    with pytest.raises(ReviewError, match="^review_state$"):
        review_state.fold_events(other, (first,))


@pytest.mark.parametrize(
    "fault",
    [
        "run",
        "projection",
        "no_party",
        "duplicate_party",
        "no_country",
        "no_tax_match",
        "404",
        "malformed_registry",
    ],
)
def test_only_the_selected_eligible_agreement_can_be_reviewed(fault: str) -> None:
    base = context()
    candidate = command()
    if fault == "run":
        base = replace(base, run_id=UUID(int=999))
    elif fault == "projection":
        base = replace(base, projection_version="private-sentinel")
    elif fault == "no_party":
        base = replace(base, parties=())
    elif fault == "duplicate_party":
        base = replace(base, parties=(*base.parties, base.parties[0]))
    elif fault in ("no_country", "no_tax_match"):
        party = (
            replace(base.parties[0], country_code=None)
            if fault == "no_country"
            else replace(base.parties[0], tax_id="999999999")
        )
        base = replace(base, parties=(party,))
    elif fault == "404":
        base = replace(
            base,
            registry=(
                replace(
                    base.registry[0],
                    claim=replace(
                        base.registry[0].claim,
                        outcome="not_found_at_observation",
                        reported_afm=None,
                    ),
                ),
            ),
        )
    else:
        base = replace(
            base,
            registry=(
                replace(
                    base.registry[0], claim=replace(base.registry[0].claim, registry_number="0001")
                ),
            ),
        )
    with pytest.raises(ReviewError, match="^review_evidence$") as error:
        review_state.propose(candidate, (), cohort=base)
    assert "private-sentinel" not in str(error.value)
    with pytest.raises(ReviewError, match="^review_evidence$"):
        review_state.propose(command("reject"), (), cohort=base)


def test_no_evidence_and_inexact_acknowledgments_fail() -> None:
    with pytest.raises(ReviewError, match="^review_evidence$"):
        review_state.propose(command(), ())
    for issues in (
        (),
        ("multiple_registry_numbers_for_reported_afm",),
        ("reported_afm_changed_for_registry_number",) * 2,
    ):
        with pytest.raises(ReviewError, match="^review_evidence$"):
            review_state.propose(
                replace(command(), acknowledged_issues=issues), (), cohort=context()
            )


def test_corrupted_history_has_no_usable_head() -> None:
    from nima.identity.review_types import ReviewEvent

    accepted = review_state.propose(command(), (), cohort=context())
    for event in (
        replace(accepted, subject_revision=2),
        replace(accepted, subject_revision=True),
        replace(accepted, policy_version=""),
        replace(accepted, issues=()),
        replace(accepted, request=replace(accepted.request, expected_revision=True)),
    ):
        with pytest.raises(ReviewError, match="^review_state$"):
            review_state.fold_events(accepted.request.subject, (event,))
    duplicate = replace(
        accepted, subject_revision=2, request=replace(accepted.request, expected_revision=1)
    )
    with pytest.raises(ReviewError, match="^review_state$"):
        review_state.fold_events(accepted.request.subject, (accepted, duplicate))
    competing = ReviewEvent(command("accept", 1, 31, 3), 2, accepted.issues)
    with pytest.raises(ReviewError, match="^review_state$"):
        review_state.fold_events(accepted.request.subject, (accepted, competing))
    revoke = replace(command("revoke", 1, 32), reverses_event_id=accepted.event_id)
    forged_issues = ReviewEvent(revoke, 2, ())
    with pytest.raises(ReviewError, match="^review_state$"):
        review_state.fold_events(accepted.request.subject, (accepted, forged_issues))


def test_event_and_context_budgets_fail_without_partial_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.identity.registry_policy import RegistryObservation
    from nima.identity.review_types import ReviewAnchor

    first = review_state.propose(command(), (), cohort=context())
    second = review_state.propose(command("reject", 1, 31, 3), (first,), cohort=context())
    with monkeypatch.context() as limited:
        limited.setattr(review_state, "MAX_REVIEW_EVENTS", 1)
        assert review_state.fold_events(first.request.subject, (first,)).revision == 1
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_state.fold_events(first.request.subject, (first, second))
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_state.propose(command("reject", 1, 32, 3), (first,), cohort=context())
    with monkeypatch.context() as limited:
        limited.setattr(review_state, "MAX_COMPARISON_MENTIONS", 1)
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_state.propose(command(), (), cohort=context())
    base = context()
    one = replace(base, imports=base.imports[:1], registry=base.registry[:1])
    anchor = ReviewAnchor(
        command().entity_id or UUID(int=3),
        RegistryObservation(UUID(int=99), "1", "found", "123456789"),
    )
    monkeypatch.setattr("nima.identity.registry_policy.MAX_REGISTRY_OBSERVATIONS", 1)
    with pytest.raises(ReviewError, match="^review_limit$"):
        review_state.propose(command(evidence=one), (), cohort=one, anchor=anchor)


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation", "private-sentinel"),
        ("expected_revision", True),
        ("request_id", None),
        ("entity_id", None),
        ("report_sha256", None),
        ("report_sha256", True),
        ("reverses_event_id", UUID(int=99)),
        ("acknowledged_issues", ["not-immutable"]),
        ("acknowledged_issues", (3,)),
    ],
)
def test_malformed_in_memory_request_does_not_create_an_event(field: str, value: object) -> None:
    from dataclasses import asdict

    from nima.identity.review_types import ReviewRequest

    # Keep nested immutable values; replace one field without ignoring type checks.
    data = {
        **asdict(command()),
        field: value,
        "subject": command().subject,
        "candidate": command().candidate,
    }
    malformed = ReviewRequest(**data)
    with pytest.raises(ReviewError, match="^review_state$") as error:
        review_state.propose(malformed, (), cohort=context())
    assert "private-sentinel" not in str(error.value)


def test_noncanonical_candidate_and_invalid_operation_fields_fail_closed() -> None:
    from nima.identity.review_types import ReviewCandidate

    for malformed in (
        replace(command(), candidate=ReviewCandidate(UUID(int=1), "0001")),
        replace(command("reject"), entity_id=UUID(int=99)),
        replace(command("revoke"), report_sha256="a" * 64),
    ):
        with pytest.raises(ReviewError, match="^review_state$"):
            review_state.propose(malformed, (), cohort=context())
