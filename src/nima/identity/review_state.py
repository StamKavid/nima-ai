"""Pure, occurrence-scoped review transitions; no SQL or filesystem effects.

A proposal is not an authorized write. The store must validate source evidence
and database principal in its own transaction before committing any event.
"""

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from nima.identity import MAX_COMPARISON_MENTIONS, MAX_REGISTRY_OBSERVATIONS, ComparisonError
from nima.identity.registry_policy import compare
from nima.identity.review_types import (
    CONFLICT_CODES,
    REVIEW_POLICY_VERSION,
    ReviewAnchor,
    ReviewCandidate,
    ReviewError,
    ReviewEvent,
    ReviewHead,
    ReviewPairState,
    ReviewRequest,
    ReviewSubject,
)
from nima.sources.gemi import registry_number

if TYPE_CHECKING:
    from nima.identity.registry_cohort import ComparisonCohort

MAX_REVIEW_EVENTS = 10000


def _shape(request: ReviewRequest) -> None:
    if (
        type(request.expected_revision) is not int
        or not 0 <= request.expected_revision < 2**63
        or not isinstance(request.request_id, UUID)
        or not isinstance(request.candidate.import_id, UUID)
        or not isinstance(request.acknowledged_issues, tuple)
        or any(not isinstance(issue, str) for issue in request.acknowledged_issues)
    ):
        raise ReviewError("review_state")
    try:
        if registry_number(request.candidate.registry_number) != request.candidate.registry_number:
            raise ValueError
    except ValueError:
        raise ReviewError("review_state") from None
    report_valid = (
        isinstance(request.report_sha256, str)
        and re.fullmatch("[0-9a-f]{64}", request.report_sha256) is not None
    )
    if request.operation == "accept":
        valid = (
            isinstance(request.entity_id, UUID)
            and report_valid
            and request.reverses_event_id is None
        )
    elif request.operation == "reject":
        valid = (
            request.entity_id is None
            and report_valid
            and request.reverses_event_id is None
            and not request.acknowledged_issues
        )
    elif request.operation == "revoke":
        valid = (
            request.entity_id is None
            and request.report_sha256 is None
            and isinstance(request.reverses_event_id, UUID)
            and not request.acknowledged_issues
        )
    else:
        valid = False
    if not valid:
        raise ReviewError("review_state")


def _change(
    pairs: dict[ReviewCandidate, ReviewPairState],
    accepted: ReviewCandidate | None,
    request: ReviewRequest,
    issues: tuple[str, ...],
) -> ReviewCandidate | None:
    prior = pairs.get(request.candidate)
    if request.operation == "revoke":
        if (
            prior is None
            or prior.state == "unreviewed"
            or prior.event_id != request.reverses_event_id
        ):
            raise ReviewError("review_conflict")
        if issues != prior.issues:
            raise ReviewError("review_state")
        pairs[request.candidate] = ReviewPairState(
            request.candidate, "unreviewed", request.request_id, None, issues
        )
        return None if accepted == request.candidate else accepted
    if prior is not None and prior.state == "accepted":
        raise ReviewError("review_conflict")
    if request.operation == "accept":
        if accepted is not None:
            raise ReviewError("review_conflict")
        pairs[request.candidate] = ReviewPairState(
            request.candidate, "accepted", request.request_id, request.entity_id, issues
        )
        return request.candidate
    pairs[request.candidate] = ReviewPairState(
        request.candidate, "rejected", request.request_id, None, issues
    )
    return accepted


def fold_events(subject: ReviewSubject, events: Sequence[ReviewEvent]) -> ReviewHead:
    if len(events) > MAX_REVIEW_EVENTS:
        raise ReviewError("review_limit")
    pairs: dict[ReviewCandidate, ReviewPairState] = {}
    accepted = None
    seen: set[UUID] = set()
    for revision, event in enumerate(events, 1):
        request = event.request
        _shape(request)
        if (
            request.subject != subject
            or type(event.subject_revision) is not int
            or event.subject_revision != revision
            or request.expected_revision != revision - 1
            or event.event_id in seen
            or not isinstance(event.policy_version, str)
            or not event.policy_version
            or not isinstance(event.issues, tuple)
            or any(not isinstance(issue, str) for issue in event.issues)
        ):
            raise ReviewError("review_state")
        if (
            event.policy_version == REVIEW_POLICY_VERSION
            and request.operation != "revoke"
            and (
                tuple(sorted(set(event.issues))) != event.issues
                or any(issue not in CONFLICT_CODES for issue in event.issues)
                or (request.operation == "accept" and request.acknowledged_issues != event.issues)
            )
        ):
            raise ReviewError("review_state")
        seen.add(event.event_id)
        try:
            accepted = _change(pairs, accepted, request, event.issues)
        except ReviewError:
            raise ReviewError("review_state") from None
    return ReviewHead(
        subject,
        len(events),
        tuple(
            sorted(
                pairs.values(),
                key=lambda row: (row.candidate.import_id.int, row.candidate.registry_number),
            )
        ),
    )


def _issues(
    request: ReviewRequest, cohort: "ComparisonCohort", anchor: ReviewAnchor | None
) -> tuple[str, ...]:
    if (
        len(cohort.parties) > MAX_COMPARISON_MENTIONS
        or len(cohort.registry) > MAX_REGISTRY_OBSERVATIONS
    ):
        raise ReviewError("review_limit")
    subject = request.subject
    if cohort.run_id != subject.run_id or cohort.projection_version != subject.projection_version:
        raise ReviewError("review_evidence")
    parties = [
        row
        for row in cohort.parties
        if (
            row.source_id,
            row.normalizer_version,
            row.content_sha256,
            row.observation_id,
            row.role,
            row.ordinal,
        )
        == (
            subject.source_id,
            subject.normalizer_version,
            subject.content_sha256,
            subject.observation_id,
            subject.role,
            subject.ordinal,
        )
    ]
    observations = [row.claim for row in cohort.registry]
    selected = request.candidate.import_id, request.candidate.registry_number
    keys = {(row.import_id, row.registry_number) for row in observations}
    if len(parties) != 1 or selected not in keys:
        raise ReviewError("review_evidence")
    if anchor is not None:
        if (
            request.operation != "accept"
            or anchor.entity_id != request.entity_id
            or anchor.observation.registry_number != request.candidate.registry_number
            or anchor.observation.outcome != "found"
        ):
            raise ReviewError("review_evidence")
        key = anchor.observation.import_id, anchor.observation.registry_number
        if key in keys:
            if any(
                row != anchor.observation
                for row in observations
                if (row.import_id, row.registry_number) == key
            ):
                raise ReviewError("review_evidence")
        else:
            observations.append(anchor.observation)
    try:
        result = compare((parties[0].claim(),), observations)
    except ComparisonError as exc:
        raise ReviewError(
            "review_limit" if exc.reason == "comparison_limit" else "review_evidence"
        ) from None
    comparison = result.comparisons[0]
    if not any(
        (
            result.registry[index].observation.import_id,
            result.registry[index].observation.registry_number,
        )
        == selected
        for index in comparison.registry_observation_refs
    ):
        raise ReviewError("review_evidence")
    return comparison.issues


def propose(
    request: ReviewRequest,
    events: Sequence[ReviewEvent],
    *,
    cohort: "ComparisonCohort | None" = None,
    anchor: ReviewAnchor | None = None,
) -> ReviewEvent:
    """Propose one transition; committed-request replay is the store's separate job."""
    _shape(request)
    if len(events) >= MAX_REVIEW_EVENTS:
        raise ReviewError("review_limit")
    head = fold_events(request.subject, events)
    if request.expected_revision != head.revision or any(
        row.event_id == request.request_id for row in events
    ):
        raise ReviewError("review_conflict")
    if request.operation == "revoke":
        prior = next((row for row in head.pairs if row.candidate == request.candidate), None)
        issues = () if prior is None else prior.issues
    else:
        if cohort is None:
            raise ReviewError("review_evidence")
        issues = _issues(request, cohort, anchor)
        if request.operation == "accept" and request.acknowledged_issues != issues:
            raise ReviewError("review_evidence")
    accepted = next((row.candidate for row in head.pairs if row.state == "accepted"), None)
    _change({row.candidate: row for row in head.pairs}, accepted, request, issues)
    return ReviewEvent(request, head.revision + 1, issues)
