"""Approved comparison policy; no issuer, company type or identity is inferred."""

from dataclasses import dataclass
from typing import Literal, TypedDict


class PartyClaim(TypedDict):
    role: Literal["buyer", "supplier"]
    ordinal: int
    name: str | None
    tax_id: str | None
    source_key: str | None
    country_code: str | None


class Evidence(TypedDict):
    raw_sha256: str
    json_pointer: str
    observed_at: str


class Occurrence(PartyClaim):
    source_id: str
    normalizer_version: str
    content_sha256: str
    observation_id: int
    evidence: Evidence


@dataclass(frozen=True)
class Assessment:
    comparison_tax_id: str | None
    comparison_country: str | None
    comparison_source_key: str | None
    format_status: str
    keys: tuple[tuple[str, ...], ...]
    issues: tuple[str, ...]
    checksum_status: str = "not_checked"
    authority_status: str = "not_checked"
    issuer_country: None = None
    identity_status: str = "unresolved"


def _comparison(value: str | None) -> str | None:
    return None if value is None else value.strip(" \t\r\n") or None


def evaluate(claim: PartyClaim) -> Assessment:
    tax = _comparison(claim["tax_id"])
    country = _comparison(claim["country_code"])
    key = _comparison(claim["source_key"])
    nine_digits = tax is not None and len(tax) == 9 and tax.isascii() and tax.isdecimal()
    issues: list[str] = []
    keys: list[tuple[str, ...]] = []
    if claim["role"] == "buyer" and key is not None:
        keys.append(("kimdis.buyer-key", key))
    if tax is None:
        issues.append("tax_missing")
    elif tax == "000000000":
        issues.append("placeholder")
    elif not nine_digits:
        issues.append("format_unassessed")
    elif country is None:
        issues.append("country_missing")
    elif country not in {"GR", "EL"}:
        issues.append("country_unassessed")
    else:
        keys.append(("kimdis.reported-country-tax", country, tax))
    return Assessment(
        tax,
        country,
        key,
        "missing" if tax is None else "nine_ascii_digits" if nine_digits else "unassessed",
        tuple(keys),
        tuple(issues),
    )
