"""L5c-1: several registry numbers under one AFM are a conflict only when they are not branches.

A branch repeats its head office's AFM (L6 pilot), so a head office with branches is an ordinary
agreement. Unknown branch status counts as a head office, so evidence without the flag behaves as it
always did.
"""

from uuid import UUID

import pytest

from nima.identity import ComparisonError
from nima.identity.registry_policy import RegistryObservation, compare
from tests.test_registry_policy import party

AFM = "001234567"
ISSUE = "multiple_registry_numbers_for_reported_afm"


def row(
    number: str, branch: bool | None, *, afm: str | None = AFM, run: int = 1
) -> RegistryObservation:
    return RegistryObservation(UUID(int=run), number, "found", afm, is_branch=branch)


def issues(*rows: RegistryObservation) -> tuple[tuple[str, ...], tuple[int, ...]]:
    result = compare([party(AFM)], rows)
    return result.comparisons[0].issues, result.comparisons[0].registry_observation_refs


def test_a_head_office_with_branches_is_an_ordinary_agreement() -> None:
    found, refs = issues(row("1", False), row("2", True), row("3", True))
    assert found == () and refs == (0, 1, 2)


def test_two_head_offices_are_a_conflict_and_the_branches_carry_it_too() -> None:
    result = compare([party(AFM)], (row("1", False), row("2", False), row("3", True)))
    assert result.comparisons[0].issues == (ISSUE,)
    assert all(ISSUE in assessed.issues for assessed in result.registry)


def test_branches_alone_cannot_show_a_conflict() -> None:
    assert issues(row("1", True), row("2", True))[0] == ()


def test_unknown_branch_status_counts_as_a_head_office() -> None:
    assert issues(row("1", None), row("2", None))[0] == (ISSUE,)
    assert issues(row("1", None), row("2", True))[0] == ()
    assert issues(row("1", None), row("2", False))[0] == (ISSUE,)


def test_the_same_number_in_two_imports_is_not_two_registry_numbers() -> None:
    assert issues(row("1", False, run=1), row("1", False, run=2))[0] == ()


def test_a_changed_afm_for_one_registry_number_is_still_reported_for_a_branch() -> None:
    result = compare(
        [party(AFM)], (row("1", True, afm=AFM), row("1", True, afm="123456789", run=2))
    )
    assert "reported_afm_changed_for_registry_number" in result.registry[0].issues


@pytest.mark.parametrize("flag", ["yes", 1, 0, "False"])
def test_a_branch_flag_that_is_not_a_boolean_is_refused(flag: object) -> None:
    with pytest.raises(ComparisonError, match="^registry_observation$"):
        compare([party(AFM)], (row("1", flag),), ())  # type: ignore[arg-type]


def test_the_policy_version_is_the_branch_aware_one_with_or_without_searches() -> None:
    assert compare([party(AFM)], (row("1", False),)).policy_version == "registry-comparison-v3"
