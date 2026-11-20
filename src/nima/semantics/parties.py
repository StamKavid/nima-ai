"""Reported party keys: trimmed source text, never a verified legal identity.

A reported supplier is a country and a tax number exactly as a source published them, with only
ASCII whitespace trimmed. A reported buyer key is the source's own organization key in a
namespace. Neither is an assertion about who a company or authority is; names and addresses are
labels, never keys, and no identity is inferred here. Rules that decide whether a key is eligible
for one metric belong to that metric's definition; this module only offers the shared,
source-text-preserving pieces.
"""

import re
from dataclasses import dataclass

ASCII_WHITESPACE = " \t\r\n\f\v"
BUYER_NAMESPACE = "kimdis.buyer-key"
GREEK_COUNTRY_CODES = frozenset({"GR", "EL"})


def trim_ascii(value: str | None) -> str:
    """Trim only ASCII space, tab, CR, LF, FF and VT; missing text becomes empty text."""
    return (value or "").strip(ASCII_WHITESPACE)


def valid_tax_id(value: object) -> bool:
    """Nine ASCII digits and not all zero; no checksum and no registry-authority claim."""
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9]{9}", value) is not None
        and value != "000000000"
    )


def buyer_key(raw: str | None) -> str | None:
    """The trimmed source organization key in its namespace; missing or blank stays unknown."""
    trimmed = trim_ascii(raw)
    return f"{BUYER_NAMESPACE}:{trimmed}" if trimmed else None


@dataclass(frozen=True)
class ReportedSupplier:
    tax_id: str
    country: str

    @property
    def eligible_tax_id(self) -> bool:
        return valid_tax_id(self.tax_id)

    @property
    def greek_country(self) -> bool:
        return self.country in GREEK_COUNTRY_CODES


def reported_supplier(tax_id: str | None, country: str | None) -> ReportedSupplier:
    return ReportedSupplier(trim_ascii(tax_id), trim_ascii(country))
