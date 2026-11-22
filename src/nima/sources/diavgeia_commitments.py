"""Diavgeia commitment decisions (type Β.1.3) as a source adapter.

It reuses the Δ.2.2 adapter's request, envelope and metadata handling and changes only the
decision type and the type-specific fields. No real Β.1.3 response has been recorded yet, so the
field shapes follow the documentation only (``docs/sources/diavgeia-acceptance.md``): every
type-specific field is optional, and a shape that does not match quarantines that one record.

Suppliers (``sponsorAFMName``) are reduced to a count: no tax number and no name is projected
(``SPEC-diavgeia-commitments.md``, decision C3).
"""

from typing import ClassVar

from nima.sources.base import DEFAULT_MAX_BYTES, NormalizedPage
from nima.sources.diavgeia import (
    DiavgeiaAdapter,
    DiavgeiaQuery,
    _BadRecord,
    _header,
    _money,
    _optional_text,
    _related,
    normalize_search_page,
)

REGISTRY_KEY = "diavgeia-commitment"
CONNECTOR_VERSION = "diavgeia-commitment-search-v1"
NORMALIZER_VERSION = "diavgeia-commitment-v1"
DECISION_TYPE = "Β.1.3"


class CommitmentQuery(DiavgeiaQuery):
    """One organisation, one issue-date window of at most 30 days, commitments only."""

    decision_type: ClassVar[str] = DECISION_TYPE


def _scalar(value: object, reason: str) -> str | int | None:
    """A year or entry number exactly as published: text or a whole number, never a bool."""
    if value is None:
        return None
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.strip():
        return value
    raise _BadRecord(reason)


def _lines(extra: dict[str, object]) -> tuple[list[dict[str, str | None]], int]:
    lines = extra.get("amountWithKae")
    if lines is None:
        return [], 0
    if not isinstance(lines, list) or not all(isinstance(line, dict) for line in lines):
        raise _BadRecord("invalid_kae_lines")
    kept: list[dict[str, str | None]] = []
    suppliers = 0
    for line in lines:
        amount, _ = _money(line.get("amountWithVAT"), bare=True)
        kept.append({"kae": _optional_text(line.get("kae")), "amount_with_vat": amount})
        suppliers += line.get("sponsorAFMName") is not None
    return kept, suppliers


def _record(value: object) -> tuple[str, dict[str, object]]:
    header, extra = _header(value)
    amount, currency = _money(extra.get("amountWithVAT"), bare=True)
    partial = extra.get("partialead")
    if partial is not None and type(partial) is not bool:
        raise _BadRecord("invalid_partial_flag")
    lines, suppliers = _lines(extra)
    return f"diavgeia:{header['ada']}", {
        **header,
        "related_partial_ada": _related(extra.get("relatedPartialADA")),
        "financial_year": _scalar(extra.get("financialYear"), "invalid_financial_year"),
        "budget_type": _optional_text(extra.get("budgettype")),
        "entry_number": _scalar(extra.get("entryNumber"), "invalid_entry_number"),
        "partial_ada": partial,
        "amount_with_vat": amount,
        "amount_currency": currency,
        "kae_lines": lines,
        "supplier_count": suppliers,
    }


class CommitmentAdapter(DiavgeiaAdapter):
    """The adapter name stays ``diavgeia``: a decision keeps one identity, ``diavgeia:<ADA>``."""

    query_type = CommitmentQuery
    connector_version = CONNECTOR_VERSION
    normalizer_version = NORMALIZER_VERSION

    def normalize_page(self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> NormalizedPage:
        return normalize_search_page(raw, max_bytes, _record)
