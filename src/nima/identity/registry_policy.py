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

type RegistryOutcome = Literal["found", "not_found_at_observation"]
type RegistryIdentifierStatus = Literal[
    "eligible", "tax_missing", "placeholder", "format_unassessed", "not_found_at_observation"
]
type ComparisonOutcome = Literal[
    "reported_identifier_agreement", "no_candidate_in_selected_imports", "unassessed_identifier"
]


@dataclass(frozen=True)
class RegistryObservation:
    import_id: UUID
    registry_number: str
    outcome: RegistryOutcome
    reported_afm: str | None


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
    policy_version: str = field(default=REGISTRY_POLICY_VERSION, init=False)


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
    if observation.outcome == "not_found_at_observation":
        if observation.reported_afm is not None:
            raise ComparisonError("registry_observation")
        return RegistryAssessment(observation, None, "not_found_at_observation")
    raw = observation.reported_afm
    afm = None if raw is None else raw.strip(" \t\r\n") or None
    status: RegistryIdentifierStatus
    if afm is None:
        status = "tax_missing"
    elif afm == "000000000":
        status = "placeholder"
    elif len(afm) != 9 or not afm.isascii() or not afm.isdecimal():
        status = "format_unassessed"
    else:
        status = "eligible"
    return RegistryAssessment(observation, afm, status)


def compare(
    parties: Sequence[PartyClaim], observations: Sequence[RegistryObservation]
) -> ComparisonResult:
    if len(parties) > MAX_COMPARISON_MENTIONS or len(observations) > MAX_REGISTRY_OBSERVATIONS:
        raise ComparisonError("comparison_limit")
    assessed = tuple(_registry(row) for row in observations)
    keys = {(row.observation.import_id, row.observation.registry_number) for row in assessed}
    if len(keys) != len(assessed):
        raise ComparisonError("registry_observation")
    registry = tuple(
        sorted(
            assessed,
            key=lambda row: (row.observation.import_id.int, row.observation.registry_number),
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
        if len({registry[index].observation.registry_number for index in references}) > 1
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
        outcome: ComparisonOutcome
        if tax is None:
            outcome = "unassessed_identifier"
        elif references:
            outcome = "reported_identifier_agreement"
        else:
            outcome = "no_candidate_in_selected_imports"
        issues = sorted({issue for index in references for issue in registry[index].issues})
        comparisons.append(Comparison(assessment, outcome, references, tuple(issues)))
    return ComparisonResult(registry, tuple(comparisons))
