"""Pure reported-identifier comparisons, never accepted identities or graph links.

Observation selectors retain provenance; complete dated/context evidence remains
with the cohort/report layer. Registry AFM shape does not establish jurisdiction.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal
from uuid import UUID

from nima.identity import (
    MAX_COMPARISON_MENTIONS,
    MAX_REGISTRY_OBSERVATIONS,
    REGISTRY_POLICY_VERSION,
    ComparisonError,
)
from nima.identity.policy import Assessment, PartyClaim, evaluate
from nima.sources.gemi import registry_number
from nima.sources.gemi_search import queryable_afm

type RegistryOutcome = Literal["found", "not_found_at_observation"]
type RegistryIdentifierStatus = Literal[
    "eligible",
    "tax_missing",
    "placeholder",
    "format_unassessed",
    "not_found_at_observation",
    "search_afm_mismatch",
]
type ComparisonOutcome = Literal[
    "reported_identifier_agreement",
    "no_candidate_in_selected_imports",
    "unassessed_identifier",
    "queried_not_found_at_observation",
]
type SearchOutcome = Literal[
    "hit_single",
    "hit_multiple",
    "truncated",
    "afm_mismatch",
    "not_found_at_observation",
    "quarantined",
]
_HIT_OUTCOMES = frozenset({"hit_single", "hit_multiple", "truncated", "afm_mismatch"})
_SEARCH_OUTCOMES = _HIT_OUTCOMES | {"not_found_at_observation", "quarantined"}
# What a searched AFM's own answer adds to the comparison of a party carrying that AFM.
_QUERY_ISSUES = {"afm_mismatch": "search_afm_mismatch", "quarantined": "search_quarantined"}


@dataclass(frozen=True)
class RegistryObservation:
    import_id: UUID
    registry_number: str
    outcome: RegistryOutcome
    reported_afm: str | None
    # Set only for a company returned by an AFM search: the AFM that was asked for, and whether the
    # company reports it. A branch repeats its head office's AFM, so several hits may match.
    queried_afm: str | None = None
    afm_matches: bool | None = None
    # The registry's own flag. A branch repeats its head office's AFM, so branches do not count
    # towards a conflict; unknown (None) counts as a head office.
    is_branch: bool | None = None


@dataclass(frozen=True)
class SearchQuery:
    """One searched AFM and the fixed outcome of its answer; a 404 says nothing about existence."""

    import_id: UUID
    afm: str
    outcome: SearchOutcome
    truncated: bool


@dataclass(frozen=True)
class RegistryAssessment:
    observation: RegistryObservation
    comparison_afm: str | None
    identifier_status: RegistryIdentifierStatus
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class Comparison:
    assessment: Assessment
    outcome: ComparisonOutcome
    registry_observation_refs: tuple[int, ...]
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparisonResult:
    registry: tuple[RegistryAssessment, ...]
    comparisons: tuple[Comparison, ...]
    automatic_identity_links: Literal[0] = field(default=0, init=False)
    policy_version: str = REGISTRY_POLICY_VERSION


def _registry(observation: RegistryObservation) -> RegistryAssessment:
    if (
        not isinstance(observation.import_id, UUID)
        or observation.outcome not in ("found", "not_found_at_observation")
        or (observation.reported_afm is not None and not isinstance(observation.reported_afm, str))
    ):
        raise ComparisonError("registry_observation")
    try:
        canonical_number = registry_number(observation.registry_number)
    except ValueError:
        raise ComparisonError("registry_observation") from None
    if canonical_number != observation.registry_number:
        raise ComparisonError("registry_observation")
    if observation.is_branch is not None and type(observation.is_branch) is not bool:
        raise ComparisonError("registry_observation")
    searched = observation.queried_afm is not None or observation.afm_matches is not None
    if searched:
        try:
            queryable_afm(observation.queried_afm)
        except ValueError:
            raise ComparisonError("registry_observation") from None
        if observation.outcome != "found" or type(observation.afm_matches) is not bool:
            raise ComparisonError("registry_observation")
    if observation.outcome == "not_found_at_observation":
        if observation.reported_afm is not None:
            raise ComparisonError("registry_observation")
        return RegistryAssessment(observation, None, "not_found_at_observation")
    raw = observation.reported_afm
    afm = None if raw is None else raw.strip(" \t\r\n") or None
    status: RegistryIdentifierStatus
    if observation.afm_matches is False:
        status = "search_afm_mismatch"  # kept as evidence; never an agreement
    elif afm is None:
        status = "tax_missing"
    elif afm == "000000000":
        status = "placeholder"
    elif len(afm) != 9 or not afm.isascii() or not afm.isdecimal():
        status = "format_unassessed"
    else:
        status = "eligible"
    return RegistryAssessment(observation, afm, status)


def _queries(queries: Sequence[SearchQuery]) -> dict[tuple[UUID, str], SearchQuery]:
    selected: dict[tuple[UUID, str], SearchQuery] = {}
    for item in queries:
        try:
            queryable_afm(item.afm)
        except ValueError:
            raise ComparisonError("registry_observation") from None
        if (
            not isinstance(item.import_id, UUID)
            or item.outcome not in _SEARCH_OUTCOMES
            or type(item.truncated) is not bool
            or (item.import_id, item.afm) in selected
        ):
            raise ComparisonError("registry_observation")
        selected[(item.import_id, item.afm)] = item
    return selected


def compare(
    parties: Sequence[PartyClaim],
    observations: Sequence[RegistryObservation],
    queries: Sequence[SearchQuery] = (),
) -> ComparisonResult:
    if len(parties) > MAX_COMPARISON_MENTIONS or len(observations) > MAX_REGISTRY_OBSERVATIONS:
        raise ComparisonError("comparison_limit")
    searched = _queries(queries)
    assessed = tuple(_registry(row) for row in observations)
    for row in assessed:
        if row.observation.queried_afm is not None:
            owner = searched.get((row.observation.import_id, row.observation.queried_afm))
            if owner is None or owner.outcome not in _HIT_OUTCOMES:
                raise ComparisonError("registry_observation")
    keys = {
        (row.observation.import_id, row.observation.registry_number, row.observation.queried_afm)
        for row in assessed
    }
    if len(keys) != len(assessed):
        raise ComparisonError("registry_observation")
    registry = tuple(
        sorted(
            assessed,
            key=lambda row: (
                row.observation.import_id.int,
                row.observation.registry_number,
                row.observation.queried_afm or "",
            ),
        )
    )
    by_afm: dict[str, list[int]] = defaultdict(list)
    by_number: dict[str, set[str]] = defaultdict(set)
    for index, row in enumerate(registry):
        if row.comparison_afm is not None:
            by_number[row.observation.registry_number].add(row.comparison_afm)
        if row.identifier_status == "eligible" and row.comparison_afm is not None:
            by_afm[row.comparison_afm].append(index)
    conflicting_afms = {
        afm
        for afm, references in by_afm.items()
        if len(
            {
                registry[index].observation.registry_number
                for index in references
                if registry[index].observation.is_branch is not True
            }
        )
        > 1
    }
    changed_numbers = {number for number, afms in by_number.items() if len(afms) > 1}
    marked = []
    for row in registry:
        issues = []
        if row.identifier_status == "eligible" and row.comparison_afm in conflicting_afms:
            issues.append("multiple_registry_numbers_for_reported_afm")
        if row.comparison_afm is not None and row.observation.registry_number in changed_numbers:
            issues.append("reported_afm_changed_for_registry_number")
        marked.append(replace(row, issues=tuple(issues)))
    registry = tuple(marked)
    comparisons = []
    for party in parties:
        assessment = evaluate(party)
        tax = next(
            (key[2] for key in assessment.keys if key[0] == "kimdis.reported-country-tax"), None
        )
        references = () if tax is None else tuple(by_afm.get(tax, ()))
        looked_up = [item for (_, afm), item in searched.items() if afm == tax]
        outcome: ComparisonOutcome
        if tax is None:
            outcome = "unassessed_identifier"
        elif references:
            outcome = "reported_identifier_agreement"
        elif any(item.outcome == "not_found_at_observation" for item in looked_up):
            outcome = "queried_not_found_at_observation"
        else:
            outcome = "no_candidate_in_selected_imports"
        found = {issue for index in references for issue in registry[index].issues}
        for item in looked_up:
            if item.outcome in _QUERY_ISSUES:
                found.add(_QUERY_ISSUES[item.outcome])
            if item.truncated:
                found.add("search_truncated")
        comparisons.append(Comparison(assessment, outcome, references, tuple(sorted(found))))
    return ComparisonResult(
        registry,
        tuple(comparisons),
    )
