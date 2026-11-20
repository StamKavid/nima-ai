"""Synthetic schema fixtures, not verified production GEMI payloads."""

import hashlib
import json
from typing import cast

import pytest

from nima.sources.gemi import Assertion, InvalidProfile, normalize_profile


def profile(number: int = 1, /, **changes: object) -> bytes:
    return json.dumps(
        {
            "arGemi": number,
            "afm": "001234567",
            "coNameEl": "  Άλφα ΑΕ ",
            "autoRegistered": False,
            "coNamesEn": [],
            "legalType": {"id": 0, "descr": "ΜΟΡΦΗ"},
            **changes,
        },
        ensure_ascii=False,
    ).encode()


def test_profile_preserves_partial_claims_exact_ids_and_existing_pointers() -> None:
    raw = profile(
        activities=[
            {
                "activity": {"id": "01.01", "kadVersion": "2008"},
                "dtFrom": "2026-01-01",
                "dtTo": None,
            },
            {"activity": {"id": "01.01", "kadVersion": "2026"}},
        ]
    )
    result = normalize_profile(raw, "0001")
    assert result.source_id == "gemi:1"
    assert result.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.fields["reported_afm"] == Assertion("001234567", "/afm")
    assert result.fields["name_el"].value == "  Άλφα ΑΕ "
    assert result.fields["auto_registered"].value is False
    assert result.fields["names_en"].value == ()
    assert result.fields["is_branch"] == Assertion(None, None)
    assert result.fields["legal_type_id"].value == 0
    assert result.activities is not None
    assert [a["version"].value for a in result.activities] == ["2008", "2026"]
    assert result.activities[0]["version"].json_pointer == "/activities/0/activity/kadVersion"
    assert result.activities[0]["date_to"].json_pointer == "/activities/0/dtTo"
    assert result.activities[1]["date_to"].json_pointer is None
    with pytest.raises(TypeError):
        cast(dict[str, Assertion], result.fields)["name_el"] = Assertion("changed", None)


def test_unknowns_empty_lists_and_raw_only_properties_stay_distinct() -> None:
    sparse = normalize_profile(b'{"arGemi":1}', "1")
    assert sparse.activities is None and sparse.activities_pointer is None
    assert normalize_profile(profile(activities=[]), "1").activities == ()
    explicit_null = normalize_profile(profile(activities=None, afm=None), "1")
    assert explicit_null.activities_pointer == "/activities"
    assert explicit_null.fields["reported_afm"] == Assertion(None, "/afm")
    raw = profile(persons=[{"personName": "Synthetic person"}], capital="precise")
    raw = raw.replace(b'"precise"', b"0.100000000000000000001")
    result = normalize_profile(raw, "1")
    assert "persons" not in result.payload() and "capital" not in result.payload()
    assert result.response_sha256 == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "changes",
    [
        {"arGemi": True},
        {"arGemi": 0},
        {"arGemi": "01"},
        {"arGemi": " 1"},
        {"arGemi": "+1"},
        {"arGemi": "١"},
        {"arGemi": "2"},
        {"arGemi": ""},
        {"arGemi": 2},
        {"afm": 1234567},
        {"coNamesEn": [3]},
        {"coTitlesEl": {}},
        {"autoRegistered": 0},
        {"isBranch": "false"},
        {"legalType": []},
        {"status": {"id": True}},
        {"incorporationDate": "2026-02-30"},
        {"lastStatusChange": "20261110"},
        {"activities": {}},
        {"activities": [None]},
        {"activities": [{"activity": {"id": 1}}]},
        {"activities": [{"dtFrom": "yesterday"}]},
        {"activities": [{}] * 1001},
        {"coNamesEn": [""] * 1001},
    ],
)
def test_invalid_profile_is_not_guessed(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidProfile):
        normalize_profile(profile(**changes), "1")


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"{}",
        b"bad",
        b"\xff",
        b'{"arGemi":1,"arGemi":2}',
        b'{"arGemi":1,"extra":NaN}',
        b'{"arGemi":1,"extra":Infinity}',
        b'{"arGemi":1,"extra":{"a":1,"a":2}}',
        rb'{"arGemi":1,"coNameEl":"\ud800"}',
    ],
)
def test_malformed_or_ambiguous_json_is_rejected(raw: bytes) -> None:
    with pytest.raises(InvalidProfile):
        normalize_profile(raw, "1")


def test_body_budget_and_alias_limit_do_not_silently_truncate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        normalize_profile(profile(coNamesEn=[""] * 1000), "1").fields["names_en"].value
        == ("",) * 1000
    )
    monkeypatch.setattr("nima.sources.gemi.MAX_BODY", 1)
    with pytest.raises(InvalidProfile, match="body_size"):
        normalize_profile(profile(), "1")


def test_live_profile_reports_the_registry_number_as_a_decimal_string() -> None:
    # Observed on 2026-11-20: the live API sends "arGemi": "1037501000", although the
    # published Swagger schema declares an integer. Both forms are accepted.
    as_string = normalize_profile(profile(**{"arGemi": "1037501000"}), "1037501000")
    as_integer = normalize_profile(profile(1037501000), "1037501000")
    assert as_string.fields["registry_number"].value == 1037501000
    assert as_string.fields["registry_number"].value == as_integer.fields["registry_number"].value
