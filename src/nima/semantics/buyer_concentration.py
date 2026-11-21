"""How concentrated one buyer's captured supplier participation is (U3), never spend or share.

For one reported buyer key, each selected record that has at least one eligible reported supplier
counts once for every such supplier. A record with two suppliers therefore counts for both, so
supplier counts overlap and are not summed to the denominator (``participation_total`` and
``joint_records`` state this). Records whose suppliers are unknown, empty or all ineligible are
unresolved and kept in the result with their reason. No contract value is allocated, no supplier
is chosen when several tie for the top, and an eligible reported key is a grouping key, never a
verified company.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from typing import cast

from nima.semantics.participation import (
    NORMALIZER,
    Observation,
    SemanticError,
    validate_observations,
)
from nima.semantics.participation import sql_rows as _participation_rows
from nima.semantics.parties import buyer_key, reported_supplier, trim_ascii
from nima.semantics.selection import Selected, select_latest

MAX_OBSERVATIONS = 5000


@dataclass(frozen=True)
class Share:
    numerator: int
    denominator: int


@dataclass(frozen=True)
class RecordDecision:
    source_id: str
    version_hashes: tuple[str, ...]
    observation_ids: tuple[int, ...]
    resolution: str
    supplier_keys: tuple[str, ...]
    ineligible_occurrences: int
    cancelled: bool | None


@dataclass(frozen=True)
class SupplierCount:
    supplier_key: str
    record_count: int
    source_ids: tuple[str, ...]
    cancelled_count: int
    unknown_cancellation_count: int


@dataclass(frozen=True)
class MetricResult:
    status: str
    buyer_key: str | None
    buyer_records: int
    resolved_records: int
    unresolved_records: int
    unresolved_share: Share | None
    top_supplier_keys: tuple[str, ...]
    top_record_count: int | None
    top_share: Share | None
    distinct_suppliers: int
    participation_total: int
    joint_records: int
    partial_source_ids: tuple[str, ...]
    suppliers: tuple[SupplierCount, ...]
    ambiguous_source_ids: tuple[str, ...]
    records: tuple[RecordDecision, ...]

    def payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(json.dumps(asdict(self), allow_nan=False)))


def reference_sql() -> str:
    """Three bound inputs: observation JSON, inclusive UTC cutoff, trimmed reported buyer key."""
    return files("nima.semantics").joinpath("buyer_concentration.sql").read_text()


def sql_rows(
    observations: tuple[Observation, ...], *, limit: int = MAX_OBSERVATIONS
) -> list[dict[str, object]]:
    """The same rows the first metric reads, validated with this metric's higher bound."""
    return _participation_rows(observations, limit=limit)


def definition() -> dict[str, object]:
    return {
        "metric": "buyer_supplier_record_concentration.v1",
        "status": "draft",
        "source": "kimdis.contract",
        "normalizer": NORMALIZER,
        "buyer": "kimdis.buyer-key:reported_ascii_trimmed_exact_match",
        "supplier": "reported_gr_or_el_nine_ascii_digits_nonzero_no_checksum_grouped_as_gr",
        "measure": "record_participation_counts_not_money_not_market_share",
        "denominator": "buyer_records_with_at_least_one_eligible_supplier",
        "unresolved": "unknown_empty_or_no_eligible_suppliers_kept_with_reason",
        "ties": "every_tied_top_supplier_listed_none_chosen",
        "revision": "latest_captured_before_filters_ties_unresolved",
        "cancellation": "include_true_false_unknown_with_breakdown",
        "identity": "reported_identifier_only",
        "sql_sha256": hashlib.sha256(reference_sql().encode()).hexdigest(),
    }


def definition_sha256() -> str:
    return hashlib.sha256(
        json.dumps(definition(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _decision(selected: Selected[Observation]) -> RecordDecision:
    chosen = selected.chosen
    keys: set[str] = set()
    ineligible = 0
    for supplier in chosen.suppliers or ():
        reported = reported_supplier(supplier.tax_id, supplier.country_code)
        if reported.eligible_tax_id and reported.greek_country:
            keys.add(f"GR:{reported.tax_id}")
        else:
            ineligible += 1
    if chosen.suppliers is None:
        resolution = "unknown_suppliers"
    elif chosen.suppliers == ():
        resolution = "empty_suppliers"
    elif not keys:
        resolution = "no_eligible_supplier"
    else:
        resolution = "resolved"
    return RecordDecision(
        selected.source_id,
        tuple(sorted(selected.versions)),
        tuple(sorted(row.observation_id for row in selected.current)),
        resolution,
        tuple(sorted(keys)),
        ineligible,
        chosen.cancelled,
    )


def evaluate(
    observations: tuple[Observation, ...], *, buyer: str, cutoff: datetime
) -> MetricResult:
    """Select captured revisions before attributing records; evidence verification is external."""
    requested = trim_ascii(buyer) if isinstance(buyer, str) else ""
    if not requested or not isinstance(cutoff, datetime) or cutoff.utcoffset() != timedelta(0):
        raise SemanticError("semantic_selection")
    validate_observations(observations, limit=MAX_OBSERVATIONS)
    wanted = buyer_key(requested)
    selections = select_latest(observations, cutoff)
    ambiguous = tuple(item.source_id for item in selections if item.ambiguous)
    decisions = tuple(
        _decision(item)
        for item in selections
        if not item.ambiguous and buyer_key(item.chosen.buyer_key) == wanted
    )
    resolved = [row for row in decisions if row.resolution == "resolved"]
    by_supplier: dict[str, list[RecordDecision]] = {}
    for row in resolved:
        for key in row.supplier_keys:
            by_supplier.setdefault(key, []).append(row)
    suppliers = tuple(
        SupplierCount(
            key,
            len(rows),
            tuple(row.source_id for row in rows),
            sum(row.cancelled is True for row in rows),
            sum(row.cancelled is None for row in rows),
        )
        for key, rows in sorted(by_supplier.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )
    top_count = suppliers[0].record_count if suppliers else None
    top_keys = tuple(row.supplier_key for row in suppliers if row.record_count == top_count)
    if not observations:
        status = "empty_capture"
    elif not selections:
        status = "no_observations_before_cutoff"
    elif resolved:
        status = "observed_concentration"
    elif decisions:
        status = "buyer_records_unresolved"
    elif ambiguous:
        status = "selection_unresolved"
    else:
        status = "no_observed_buyer_records"
    unresolved = len(decisions) - len(resolved)
    return MetricResult(
        status,
        wanted,
        len(decisions),
        len(resolved),
        unresolved,
        Share(unresolved, len(decisions)) if decisions else None,
        top_keys,
        top_count,
        Share(top_count, len(resolved)) if top_count is not None else None,
        len(suppliers),
        sum(row.record_count for row in suppliers),
        sum(len(row.supplier_keys) >= 2 for row in resolved),
        tuple(row.source_id for row in resolved if row.ineligible_occurrences > 0),
        suppliers,
        ambiguous,
        decisions,
    )
