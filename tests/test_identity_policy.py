"""Comparison keys describe reported identifiers, never verified companies."""

from typing import cast

import pytest

from nima.identity.policy import PartyClaim, evaluate


def claim(**changes: object) -> PartyClaim:
    return cast(
        PartyClaim,
        {
            "name": "ΔΟΚΙΜΗ",
            "tax_id": "001234567",
            "country_code": "GR",
            "source_key": None,
            "role": "supplier",
            "ordinal": 0,
            **changes,
        },
    )


def test_exact_comparison_preserves_zeros_and_names() -> None:
    value = claim(tax_id=" \t001234567\r\n", name="  Άλφα ΑΕ ")
    assessment = evaluate(value)
    assert assessment.comparison_tax_id == "001234567"
    assert assessment.format_status == "nine_ascii_digits"
    assert assessment.authority_status == assessment.checksum_status == "not_checked"
    assert assessment.issuer_country is None
    assert assessment.keys == (("kimdis.reported-country-tax", "GR", "001234567"),)
    assert value["tax_id"] == " \t001234567\r\n" and value["name"] == "  Άλφα ΑΕ "
    assert evaluate(claim(country_code="EL")).keys != assessment.keys


@pytest.mark.parametrize(
    "change,issue",
    [
        ({"tax_id": None}, "tax_missing"),
        ({"tax_id": "000000000"}, "placeholder"),
        ({"tax_id": "１２３４５６７８９"}, "format_unassessed"),
        ({"tax_id": "EL001234567"}, "format_unassessed"),
        ({"tax_id": "001-234567"}, "format_unassessed"),
        ({"tax_id": "\u00a0001234567"}, "format_unassessed"),
        ({"country_code": None}, "country_missing"),
        ({"country_code": "DE"}, "country_unassessed"),
    ],
)
def test_unsupported_claims_stay_unresolved(change: dict[str, object], issue: str) -> None:
    assessment = evaluate(claim(**change))
    assert assessment.keys == () and issue in assessment.issues


def test_buyer_key_and_tax_keys_have_separate_namespaces() -> None:
    buyer = evaluate(claim(role="buyer", source_key=" 001234567 "))
    assert buyer.keys == (
        ("kimdis.buyer-key", "001234567"),
        ("kimdis.reported-country-tax", "GR", "001234567"),
    )
    assert evaluate(claim(source_key="001234567")).keys == buyer.keys[1:]
    assert (
        evaluate(claim(role="buyer", tax_id=None, country_code=None, source_key="001234567")).keys
        == buyer.keys[:1]
    )
