"""Shared record selection (M1) and reported party keys (M3) of the V1-05 semantic model."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from nima.semantics.parties import (
    ASCII_WHITESPACE,
    BUYER_NAMESPACE,
    buyer_key,
    reported_supplier,
    trim_ascii,
    valid_tax_id,
)
from nima.semantics.selection import select_latest


@dataclass(frozen=True)
class Seen:
    """Any source's observation: only these four facts are needed to select a revision."""

    source_id: str
    observation_id: int
    content_sha256: str
    observed_at: datetime


def at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


def test_nothing_observed_selects_nothing() -> None:
    assert select_latest((), at(3)) == ()


def test_the_cutoff_is_inclusive_and_applied_before_the_latest_is_chosen() -> None:
    rows = (Seen("a", 1, "h1", at(1)), Seen("a", 2, "h2", at(3)))
    assert select_latest(rows, at(2))[0].chosen.observation_id == 1
    assert select_latest(rows, at(3))[0].chosen.observation_id == 2
    assert select_latest(rows, at(1))[0].chosen.observation_id == 1
    assert select_latest(rows, datetime(2025, 12, 31, tzinfo=UTC)) == ()


def test_the_latest_observed_time_wins_not_the_input_order() -> None:
    rows = (Seen("a", 2, "h2", at(3)), Seen("a", 1, "h1", at(1)))
    selected = select_latest(rows, at(5))
    assert [row.observation_id for row in selected[0].current] == [2]
    assert not selected[0].ambiguous


def test_repeated_observation_of_one_version_is_not_ambiguous_and_keeps_every_observation() -> None:
    rows = (Seen("a", 1, "h1", at(2)), Seen("a", 2, "h1", at(2)), Seen("a", 3, "h0", at(1)))
    selected = select_latest(rows, at(5))
    assert not selected[0].ambiguous
    assert [row.observation_id for row in selected[0].current] == [1, 2]
    assert list(selected[0].versions) == ["h1"]
    assert selected[0].chosen.observation_id == 1


def test_different_versions_tied_at_the_latest_time_are_ambiguous_with_both_kept() -> None:
    rows = (Seen("a", 1, "h2", at(2)), Seen("a", 2, "h1", at(2)))
    selected = select_latest(rows, at(5))
    assert selected[0].ambiguous
    assert list(selected[0].versions) == ["h2", "h1"]
    assert [row.observation_id for row in selected[0].current] == [1, 2]


def test_a_b_a_selects_the_last_observed_a_without_inventing_a_version() -> None:
    rows = (Seen("a", 1, "A", at(1)), Seen("a", 2, "B", at(2)), Seen("a", 3, "A", at(3)))
    selected = select_latest(rows, at(5))
    assert [row.observation_id for row in selected[0].current] == [3]
    assert list(selected[0].versions) == ["A"]


def test_sources_are_returned_in_source_id_order_and_selected_independently() -> None:
    rows = (
        Seen("c", 1, "h", at(1)),
        Seen("a", 2, "h", at(2)),
        Seen("b", 3, "h", at(1)),
        Seen("a", 4, "k", at(1)),
    )
    selected = select_latest(rows, at(5))
    assert [item.source_id for item in selected] == ["a", "b", "c"]
    assert selected[0].chosen.observation_id == 2


def test_the_result_does_not_depend_on_the_order_of_the_observations() -> None:
    rows = (
        Seen("a", 1, "h1", at(1)),
        Seen("a", 2, "h2", at(2)),
        Seen("b", 3, "h3", at(2)),
        Seen("b", 4, "h4", at(2)),
    )
    forward = select_latest(rows, at(5))
    backward = select_latest(tuple(reversed(rows)), at(5))
    assert [(s.source_id, s.ambiguous, sorted(s.versions)) for s in forward] == [
        (s.source_id, s.ambiguous, sorted(s.versions)) for s in backward
    ]
    assert [sorted(r.observation_id for r in s.current) for s in forward] == [
        sorted(r.observation_id for r in s.current) for s in backward
    ]


def test_ascii_whitespace_is_exactly_the_six_ascii_characters() -> None:
    assert ASCII_WHITESPACE == " \t\r\n\f\v"


@pytest.mark.parametrize(
    ("raw", "trimmed"),
    [
        (None, ""),
        ("", ""),
        (" \t012345678\r\n\f\v", "012345678"),
        ("a b", "a b"),
        (" 12345678 ", " 12345678 "),
        ("​1", "​1"),
    ],
)
def test_only_ascii_whitespace_is_trimmed(raw: str | None, trimmed: str) -> None:
    assert trim_ascii(raw) == trimmed


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        (None, None),
        ("", None),
        (" \t\r\n", None),
        ("B1", f"{BUYER_NAMESPACE}:B1"),
        (" B1\t", f"{BUYER_NAMESPACE}:B1"),
        ("B 1", f"{BUYER_NAMESPACE}:B 1"),
        (" ", f"{BUYER_NAMESPACE}: "),
    ],
)
def test_a_buyer_key_is_the_trimmed_source_key_in_its_namespace_or_unknown(
    raw: str | None, key: str | None
) -> None:
    assert buyer_key(raw) == key


def test_the_buyer_namespace_is_named() -> None:
    assert BUYER_NAMESPACE == "kimdis.buyer-key"


@pytest.mark.parametrize("tax", ["012345678", "123456789", "999999999", "000000001", "100000000"])
def test_a_valid_tax_id_is_nine_ascii_digits_and_not_all_zero(tax: str) -> None:
    assert valid_tax_id(tax)


@pytest.mark.parametrize(
    "tax",
    [
        None,
        12345678,
        True,
        "",
        "000000000",
        "12345678",
        "1234567890",
        " 012345678",
        "01234567a",
        "١٢٣٤٥٦٧٨٩",
        "012345678\n",
    ],
)
def test_anything_else_is_not_a_valid_tax_id(tax: object) -> None:
    assert not valid_tax_id(tax)


@pytest.mark.parametrize(
    ("tax", "country", "trimmed_tax", "trimmed_country", "eligible", "greek"),
    [
        ("012345678", "GR", "012345678", "GR", True, True),
        (" \t012345678\r\n", " EL\t", "012345678", "EL", True, True),
        ("012345678", "gr", "012345678", "gr", True, False),
        ("012345678", "DE", "012345678", "DE", True, False),
        ("012345678", None, "012345678", "", True, False),
        ("12345", "GR", "12345", "GR", False, True),
        (None, None, "", "", False, False),
        ("000000000", "GR", "000000000", "GR", False, True),
    ],
)
def test_a_reported_supplier_is_trimmed_and_assessed_without_inferring_identity(
    tax: str | None,
    country: str | None,
    trimmed_tax: str,
    trimmed_country: str,
    eligible: bool,
    greek: bool,
) -> None:
    supplier = reported_supplier(tax, country)
    assert (supplier.tax_id, supplier.country) == (trimmed_tax, trimmed_country)
    assert (supplier.eligible_tax_id, supplier.greek_country) == (eligible, greek)
