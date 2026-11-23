"""L5b policy: searched AFMs, search hits and a looked-up AFM that answered 404.

Pure and synthetic. A search hit is a registry observation only through its own reported AFM; a hit
that reports another AFM stays evidence and is never an agreement.
"""

from uuid import UUID

import pytest

from nima.identity import ComparisonError
from nima.identity.policy import PartyClaim
from nima.identity.registry_policy import (
    RegistryObservation,
    SearchQuery,
    compare,
)
from tests.test_registry_policy import observation, party

RUN = UUID(int=9)
A, B, C, D, E = "100000001", "100000002", "100000003", "100000004", "100000005"


def hit(
    number: str, reported: str | None, queried: str, *, matches: bool = True, run: UUID = RUN
) -> RegistryObservation:
    return RegistryObservation(run, number, "found", reported, queried, matches)


def query(afm: str, outcome: str, *, truncated: bool = False, run: UUID = RUN) -> SearchQuery:
    return SearchQuery(run, afm, outcome, truncated)  # type: ignore[arg-type]


# The spec's example: single, multiple, 404, mismatch, truncated.
HITS = (
    hit("1", A, A),
    hit("2", B, B),
    hit("3", B, B),
    hit("5", "999999999", D, matches=False),
    hit("6", E, E),
    hit("7", E, E),
)
QUERIES = (
    query(A, "hit_single"),
    query(B, "hit_multiple"),
    query(C, "not_found_at_observation"),
    query(D, "afm_mismatch"),
    query(E, "truncated", truncated=True),
)


def test_the_five_afm_example_gives_one_outcome_per_party() -> None:
    parties: list[PartyClaim] = [party(tax) for tax in (A, B, C, D, E, None)]
    result = compare(parties, HITS, QUERIES)
    outcomes = [
        (row.outcome, row.registry_observation_refs, row.issues) for row in result.comparisons
    ]
    assert outcomes == [
        ("reported_identifier_agreement", (0,), ()),
        (
            "reported_identifier_agreement",
            (1, 2),
            ("multiple_registry_numbers_for_reported_afm",),
        ),
        ("queried_not_found_at_observation", (), ()),
        ("no_candidate_in_selected_imports", (), ("search_afm_mismatch",)),
        (
            "reported_identifier_agreement",
            (4, 5),
            ("multiple_registry_numbers_for_reported_afm", "search_truncated"),
        ),
        ("unassessed_identifier", (), ()),
    ]
    assert result.automatic_identity_links == 0
    assert result.policy_version == "registry-comparison-v2"


def test_a_mismatching_hit_is_kept_as_evidence_and_never_an_agreement() -> None:
    result = compare(
        [party("999999999")],
        (hit("5", "999999999", D, matches=False),),
        (query(D, "afm_mismatch"),),
    )
    only = result.registry[0]
    assert only.comparison_afm == "999999999" and only.identifier_status == "search_afm_mismatch"
    assert result.comparisons[0].outcome == "no_candidate_in_selected_imports"
    assert result.comparisons[0].registry_observation_refs == ()


def test_an_agreement_from_another_import_outranks_a_404_for_the_same_afm() -> None:
    other = observation("4", A, run=2)
    result = compare(
        [party(A)],
        (other, hit("1", A, A)),
        (query(A, "hit_single"), query(A, "not_found_at_observation", run=UUID(int=11))),
    )
    assert result.comparisons[0].outcome == "reported_identifier_agreement"
    assert len(result.comparisons[0].registry_observation_refs) == 2


def test_a_404_from_any_selected_search_marks_the_afm_as_looked_up() -> None:
    run2 = UUID(int=10)
    result = compare(
        [party(A)],
        (),
        (query(A, "quarantined", run=run2), query(A, "not_found_at_observation")),
    )
    assert result.comparisons[0].outcome == "queried_not_found_at_observation"
    assert result.comparisons[0].issues == ("search_quarantined",)


def test_a_quarantined_search_alone_leaves_no_candidate_and_says_why() -> None:
    result = compare([party(A)], (), (query(A, "quarantined"),))
    row = result.comparisons[0]
    assert (row.outcome, row.issues) == (
        "no_candidate_in_selected_imports",
        ("search_quarantined",),
    )


def test_an_afm_that_was_never_searched_keeps_the_original_wording() -> None:
    result = compare([party(A), party(B)], (hit("1", A, A),), (query(A, "hit_single"),))
    assert result.comparisons[1].outcome == "no_candidate_in_selected_imports"
    assert result.comparisons[1].issues == ()


def test_input_without_search_evidence_is_exactly_the_old_comparison() -> None:
    parties = [party("001234567"), party(None), party("123456789")]
    observations = (
        observation("1", "001234567"),
        observation("2", None, outcome="not_found_at_observation"),
    )
    old = compare(parties, observations)
    assert compare(parties, observations, ()) == old
    assert old.policy_version == "registry-comparison-v1"
    assert [row.outcome for row in old.comparisons] == [
        "reported_identifier_agreement",
        "unassessed_identifier",
        "no_candidate_in_selected_imports",
    ]


def test_the_same_company_found_by_two_searches_is_two_observations_but_one_twice_is_refused() -> (
    None
):
    both = (query(A, "hit_single"), query(B, "afm_mismatch"))
    twice = (hit("1", A, A), hit("1", A, B, matches=False))
    assert len(compare([party(A)], twice, both).registry) == 2
    with pytest.raises(ComparisonError, match="^registry_observation$"):
        compare([party(A)], (hit("1", A, A), hit("1", A, A)), both)


@pytest.mark.parametrize(
    "bad",
    [
        RegistryObservation(RUN, "1", "found", A, "12345678", True),
        RegistryObservation(RUN, "1", "found", A, A, None),
        RegistryObservation(RUN, "1", "not_found_at_observation", None, A, True),
        RegistryObservation(RUN, "1", "found", A, None, True),
        RegistryObservation(RUN, "1", "found", A, A, "yes"),  # type: ignore[arg-type]
    ],
)
def test_a_malformed_search_hit_is_refused(bad: RegistryObservation) -> None:
    # A matching query exists, so only the hit's own shape can be what is refused.
    with pytest.raises(ComparisonError, match="^registry_observation$"):
        compare([party(A)], (bad,), (query(A, "hit_single"),))


@pytest.mark.parametrize(
    "bad",
    [
        SearchQuery(RUN, "12345678", "hit_single", False),
        SearchQuery(RUN, "000000000", "hit_single", False),
        SearchQuery(RUN, A, "bogus", False),  # type: ignore[arg-type]
        SearchQuery(RUN, A, "hit_single", "no"),  # type: ignore[arg-type]
        SearchQuery("x", A, "hit_single", False),  # type: ignore[arg-type]
    ],
)
def test_a_malformed_search_query_is_refused(bad: SearchQuery) -> None:
    with pytest.raises(ComparisonError, match="^registry_observation$"):
        compare([party(A)], (), (bad,))


def test_one_query_per_import_and_afm() -> None:
    with pytest.raises(ComparisonError, match="^registry_observation$"):
        compare([party(A)], (), (query(A, "hit_single"), query(A, "hit_single")))


def test_a_hit_must_belong_to_a_query_that_returned_hits() -> None:
    # A hit with no matching query row, or under a 404, cannot happen in stored evidence.
    with pytest.raises(ComparisonError, match="^registry_observation$"):
        compare([party(A)], (hit("1", A, A),), ())
    with pytest.raises(ComparisonError, match="^registry_observation$"):
        compare([party(A)], (hit("1", A, A),), (query(A, "not_found_at_observation"),))


def test_outcome_values_are_the_stored_vocabulary() -> None:
    for name in (
        "hit_single",
        "hit_multiple",
        "truncated",
        "afm_mismatch",
        "not_found_at_observation",
        "quarantined",
    ):
        compare([party(A)], (), (query(A, name),))
