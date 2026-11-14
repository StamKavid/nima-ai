"""Reported identifier agreements remain evidence candidates with unresolved identity."""

from copy import deepcopy
from dataclasses import replace
from itertools import permutations
from typing import Literal, cast
from uuid import UUID

import pytest

from nima.identity import ComparisonError
from nima.identity.policy import PartyClaim
from nima.identity.registry_policy import RegistryObservation, RegistryOutcome, compare


def party(
    tax: str | None = "001234567",
    country: str | None = "GR",
    *,
    name: str | None = "ΑΛΦΑ ΑΕ",
    role: Literal["buyer", "supplier"] = "supplier",
    key: str | None = None,
) -> PartyClaim:
    return {
        "name": name,
        "tax_id": tax,
        "country_code": country,
        "role": role,
        "ordinal": 0,
        "source_key": key,
    }


def observation(
    number: str = "1",
    tax: str | None = "001234567",
    run: int = 1,
    *,
    outcome: Literal["found", "not_found_at_observation"] = "found",
) -> RegistryObservation:
    return RegistryObservation(UUID(int=run), number, outcome, tax)


def test_exact_text_agreement_preserves_originals_contexts_and_unknown_authority() -> None:
    parties = [party(" \t001234567\r\n", "GR"), party(country="EL", name="ΑΛΦΑ")]
    before = deepcopy(parties)
    evidence = observation(tax="\t001234567\n")
    result = compare(parties, (evidence,))
    assert parties == before and result.registry[0].observation == evidence
    assert result.registry[0].comparison_afm == "001234567"
    assert result.registry[0].identifier_status == "eligible"
    assert len(result.comparisons) == 2 and result.automatic_identity_links == 0
    assert result.policy_version == "registry-comparison-v1"
    for row, country in zip(result.comparisons, ("GR", "EL"), strict=True):
        assert row.outcome == "reported_identifier_agreement"
        assert row.registry_observation_refs == (0,) and row.issues == ()
        assert row.assessment.comparison_country == country
        assert row.assessment.identity_status == "unresolved"
        assert row.assessment.checksum_status == row.assessment.authority_status == "not_checked"
        assert row.assessment.issuer_country is None
        assert row.assessment.keys == (("kimdis.reported-country-tax", country, "001234567"),)


@pytest.mark.parametrize(
    "tax,country",
    [
        (None, "GR"),
        ("", "GR"),
        ("000000000", "GR"),
        ("GR001234567", "GR"),
        ("001-234-567", "GR"),
        ("１２３４５６７８９", "GR"),
        ("٠١٢٣٤٥٦٧٨", "GR"),
        ("12345678", "GR"),
        ("\u00a0001234567\u00a0", "GR"),
        ("001234567", None),
        ("001234567", "CY"),
        ("001234567", "gr"),
    ],
)
def test_ineligible_procurement_identifiers_are_never_repaired_into_matches(
    tax: str | None, country: str | None
) -> None:
    result = compare((party(tax, country),), (observation(),))
    row = result.comparisons[0]
    assert row.outcome == "unassessed_identifier"
    assert row.registry_observation_refs == () and result.automatic_identity_links == 0


def test_same_name_or_buyer_key_does_not_replace_tax_agreement() -> None:
    result = compare((party("123456789"), party(None, role="buyer", key="1")), (observation(),))
    assert result.comparisons[0].outcome == "no_candidate_in_selected_imports"
    assert result.comparisons[1].outcome == "unassessed_identifier"
    assert all(row.registry_observation_refs == () for row in result.comparisons)


def test_not_found_and_missing_afm_remain_distinct_without_negative_identity_links() -> None:
    evidence = (
        observation(tax=None),
        observation(tax=None, run=2, outcome="not_found_at_observation"),
    )
    result = compare((party(),), evidence)
    assert tuple(row.identifier_status for row in result.registry) == (
        "tax_missing",
        "not_found_at_observation",
    )
    assert tuple(row.observation for row in result.registry) == evidence
    assert result.comparisons[0].outcome == "no_candidate_in_selected_imports"
    assert result.comparisons[0].registry_observation_refs == ()
    assert result.automatic_identity_links == 0


def test_conflicts_and_a_b_a_observations_are_retained_without_selecting_a_winner() -> None:
    evidence = (
        observation(run=3),
        observation("2"),
        observation(tax="123456789", run=2),
        observation(),
        observation(tax=None, run=4),
        observation(tax=None, run=5, outcome="not_found_at_observation"),
    )
    result = compare((party(), party("123456789")), evidence)
    assert len(result.registry) == len(evidence)
    assert {row.observation for row in result.registry} == set(evidence)
    assert result.comparisons[0].registry_observation_refs == (0, 1, 3)
    assert result.comparisons[1].registry_observation_refs == (2,)
    multiple = "multiple_registry_numbers_for_reported_afm"
    changed = "reported_afm_changed_for_registry_number"
    assert result.comparisons[0].issues == (multiple, changed)
    assert result.comparisons[1].issues == (changed,)
    assert tuple(row.issues for row in result.registry) == (
        (multiple, changed),
        (multiple,),
        (changed,),
        (multiple, changed),
        (),
        (),
    )
    assert result.automatic_identity_links == 0


def test_selector_order_and_unchanged_repeats_keep_stable_observation_references() -> None:
    evidence = (observation(run=3), observation(), observation(run=2))
    expected = compare((party(), party(name="ΑΛΦΑ")), evidence)
    for order in permutations(evidence):
        assert compare((party(), party(name="ΑΛΦΑ")), order) == expected
    assert len(expected.comparisons) == 2 and len(expected.registry) == 3
    assert all(row.registry_observation_refs == (0, 1, 2) for row in expected.comparisons)
    assert all(row.issues == () for row in expected.registry)


@pytest.mark.parametrize(
    "tax,status",
    [
        (None, "tax_missing"),
        ("", "tax_missing"),
        (" \t\r\n", "tax_missing"),
        ("000000000", "placeholder"),
        ("EL001234567", "format_unassessed"),
        ("１２３４５６７８９", "format_unassessed"),
        ("٠١٢٣٤٥٦٧٨", "format_unassessed"),
        ("\u00a0001234567\u00a0", "format_unassessed"),
    ],
)
def test_registry_identifier_reasons_preserve_unknown_and_unsupported_text(
    tax: str | None, status: str
) -> None:
    evidence = observation(tax=tax)
    result = compare((party(),), (evidence,))
    assert result.registry[0].observation.reported_afm == tax
    assert result.registry[0].identifier_status == status
    assert result.comparisons[0].outcome == "no_candidate_in_selected_imports"
    assert result.comparisons[0].registry_observation_refs == ()


def test_policy_results_and_input_observations_cannot_be_mutated_into_identity_links() -> None:
    evidence = observation()
    result = compare((party(),), (evidence,))
    for target, attribute, value in (
        (result, "automatic_identity_links", 1),
        (evidence, "reported_afm", "123456789"),
    ):
        with pytest.raises(AttributeError):
            setattr(target, attribute, value)
    assert evidence.reported_afm == "001234567" and result.automatic_identity_links == 0


@pytest.mark.parametrize("number", ["0", "01", "-1", "١", "1" * 65, "private-sentinel"])
def test_noncanonical_registry_numbers_fail_with_fixed_reason(number: str) -> None:
    with pytest.raises(ComparisonError, match="registry_observation") as error:
        compare((party(),), (observation(number),))
    assert str(error.value) == "registry_observation"


@pytest.mark.parametrize("fault", ["import_id", "outcome", "afm_type", "profile_on_404"])
def test_malformed_registry_views_fail_before_sorting_or_matching(fault: str) -> None:
    evidence = observation()
    if fault == "import_id":
        evidence = replace(evidence, import_id=cast(UUID, "private-sentinel"))
    elif fault == "outcome":
        evidence = replace(evidence, outcome=cast(RegistryOutcome, "private-sentinel"))
    elif fault == "afm_type":
        evidence = replace(evidence, reported_afm=cast(str, 23))
    else:
        evidence = replace(evidence, outcome="not_found_at_observation")
    with pytest.raises(ComparisonError, match="registry_observation") as error:
        compare((party(),), (evidence,))
    assert str(error.value) == "registry_observation"


def test_duplicate_observation_key_is_an_error_instead_of_a_silent_deduplication() -> None:
    evidence = observation()
    with pytest.raises(ComparisonError, match="registry_observation"):
        compare((party(),), (evidence, replace(evidence, reported_afm="123456789")))


def test_registry_count_boundary_preserves_every_row_then_rejects_overflow() -> None:
    evidence = tuple(observation(str(i % 10 + 1), run=i // 10 + 1) for i in range(100))
    result = compare((party(),), evidence)
    assert len(result.registry) == len(result.comparisons[0].registry_observation_refs) == 100
    assert result.automatic_identity_links == 0
    with pytest.raises(ComparisonError, match="comparison_limit"):
        compare((party(),), (*evidence, observation(run=11)))


def test_party_count_boundary_preserves_every_occurrence_then_rejects_overflow() -> None:
    parties = (party(),) * 10000
    result = compare(parties, (observation(),))
    assert len(result.comparisons) == 10000 and result.automatic_identity_links == 0
    with pytest.raises(ComparisonError, match="comparison_limit"):
        compare((*parties, party()), (observation(),))


def test_empty_policy_inputs_remain_empty_or_explicitly_without_candidates() -> None:
    empty = compare((), ())
    assert not empty.registry and not empty.comparisons and empty.automatic_identity_links == 0
    absent = compare((party(),), ())
    assert absent.comparisons[0].outcome == "no_candidate_in_selected_imports"
    assert absent.comparisons[0].registry_observation_refs == ()


def test_changed_nonmissing_afm_text_is_visible_even_when_an_old_claim_is_unassessed() -> None:
    result = compare((party(),), (observation(tax="GR001234567"), observation(run=2)))
    assert result.registry[0].identifier_status == "format_unassessed"
    assert result.comparisons[0].registry_observation_refs == (1,)
    assert all(
        row.issues == ("reported_afm_changed_for_registry_number",) for row in result.registry
    )
