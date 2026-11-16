"""Captured-publication counts, never verified company identity or paid spending."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from typing import cast

ASCII_WHITESPACE = " \t\r\n\f\v"
NORMALIZER = "kimdis-normalized-v1"


class SemanticError(ValueError):
    """Fixed reason only; source values never enter exception messages."""


def valid_tax_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9]{9}", value) is not None
        and value != "000000000"
    )


@dataclass(frozen=True)
class Supplier:
    ordinal: int
    tax_id: str | None
    country_code: str | None


@dataclass(frozen=True)
class Observation:
    observation_id: int
    source_id: str
    normalizer_version: str
    content_sha256: str
    observed_at: datetime
    buyer_key: str | None
    cancelled: bool | None
    suppliers: tuple[Supplier, ...] | None


@dataclass(frozen=True)
class RecordDecision:
    source_id: str
    version_hashes: tuple[str, ...]
    observation_ids: tuple[int, ...]
    buyer_key: str | None
    cancelled: bool | None
    matching_ordinals: tuple[int, ...]
    unassessed: bool
    unknown_suppliers: bool
    empty_suppliers: bool
    ambiguous: bool
    ambiguous_candidate: bool
    invalid_supplier_count: int


@dataclass(frozen=True)
class BuyerRecordCount:
    buyer_key: str
    source_ids: tuple[str, ...]
    record_count: int
    cancelled_count: int
    unknown_cancellation_count: int


@dataclass(frozen=True)
class MetricResult:
    status: str
    total: int
    cancelled_count: int
    unknown_cancellation_count: int
    not_cancelled_count: int
    buyers: tuple[BuyerRecordCount, ...]
    unassigned_source_ids: tuple[str, ...]
    unassessed_source_ids: tuple[str, ...]
    ambiguous_source_ids: tuple[str, ...]
    unknown_supplier_source_ids: tuple[str, ...]
    empty_supplier_source_ids: tuple[str, ...]
    invalid_supplier_count: int
    records: tuple[RecordDecision, ...]

    def payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(json.dumps(asdict(self), allow_nan=False)))


def reference_sql() -> str:
    """Three bound inputs: observation JSON, inclusive UTC cutoff, exact tax ID."""
    return files("nima.semantics").joinpath("participation.sql").read_text()


def definition() -> dict[str, object]:
    return {
        "metric": "captured_contract_record_count.v1",
        "status": "draft",
        "source": "kimdis.contract",
        "connector": "kimdis-contract-v1",
        "normalizer": NORMALIZER,
        "projection": "kimdis-participation-v1",
        "country": "GR",
        "country_aliases": ["GR", "EL"],
        "trim": ASCII_WHITESPACE,
        "tax_id": "nine_ascii_digits_nonzero_no_checksum",
        "buyer_key": "kimdis.buyer-key:reported_ascii_trimmed",
        "revision": "latest_captured_before_supplier_filter_ties_unresolved",
        "grain": "distinct_source_id",
        "cancellation": "include_true_false_unknown_with_breakdown",
        "identity": "reported_identifier_only",
        "sql_sha256": hashlib.sha256(reference_sql().encode()).hexdigest(),
    }


def definition_sha256() -> str:
    return hashlib.sha256(
        json.dumps(definition(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_observations(observations: tuple[Observation, ...]) -> None:
    if not isinstance(observations, tuple) or len(observations) > 500:
        raise SemanticError("semantic_input")
    ids = set()
    versions: dict[tuple[str, str], tuple[object, ...]] = {}
    for row in observations:
        if (
            not isinstance(row, Observation)
            or type(row.observation_id) is not int
            or row.observation_id <= 0
            or row.observation_id in ids
            or not isinstance(row.source_id, str)
            or not row.source_id.startswith("kimdis:")
            or not row.source_id[7:].strip()
            or row.normalizer_version != NORMALIZER
            or not isinstance(row.content_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", row.content_sha256) is None
            or not isinstance(row.observed_at, datetime)
            or row.observed_at.utcoffset() != timedelta(0)
            or (row.buyer_key is not None and not isinstance(row.buyer_key, str))
            or (row.cancelled is not None and type(row.cancelled) is not bool)
            or (
                row.suppliers is not None
                and (not isinstance(row.suppliers, tuple) or len(row.suppliers) > 1000)
            )
        ):
            raise SemanticError("semantic_input")
        for ordinal, supplier in enumerate(row.suppliers or ()):
            if (
                not isinstance(supplier, Supplier)
                or type(supplier.ordinal) is not int
                or supplier.ordinal != ordinal
                or (supplier.tax_id is not None and not isinstance(supplier.tax_id, str))
                or (
                    supplier.country_code is not None and not isinstance(supplier.country_code, str)
                )
            ):
                raise SemanticError("semantic_input")
        ids.add(row.observation_id)
        key = (row.source_id, row.content_sha256)
        facts = (row.buyer_key, row.cancelled, row.suppliers)
        if key in versions and versions[key] != facts:
            raise SemanticError("semantic_version_conflict")
        versions[key] = facts


def sql_rows(observations: tuple[Observation, ...]) -> list[dict[str, object]]:
    validate_observations(observations)
    return [{**asdict(row), "observed_at": row.observed_at.isoformat()} for row in observations]


def _decision(rows: list[Observation], tax_id: str) -> RecordDecision:
    latest = max(row.observed_at for row in rows)
    current = [row for row in rows if row.observed_at == latest]
    versions = {row.content_sha256: row for row in current}
    matching = []
    unassessed, unknown, empty, candidate = False, False, False, False
    invalid = 0
    for row in versions.values():
        unknown |= row.suppliers is None
        empty |= row.suppliers == ()
        for supplier in row.suppliers or ():
            tax = (supplier.tax_id or "").strip(ASCII_WHITESPACE)
            country = (supplier.country_code or "").strip(ASCII_WHITESPACE)
            invalid += not valid_tax_id(tax)
            if tax == tax_id:
                candidate = True
                if country in {"GR", "EL"}:
                    matching.append(supplier.ordinal)
                else:
                    unassessed = True
    ambiguous = len(versions) != 1
    chosen = current[0]
    buyer = (chosen.buyer_key or "").strip(ASCII_WHITESPACE)
    return RecordDecision(
        chosen.source_id,
        tuple(sorted(versions)),
        tuple(sorted(row.observation_id for row in current)),
        None if ambiguous or not buyer else f"kimdis.buyer-key:{buyer}",
        None if ambiguous else chosen.cancelled,
        () if ambiguous else tuple(sorted(matching)),
        unassessed,
        unknown,
        empty,
        ambiguous,
        ambiguous and candidate,
        invalid,
    )


def evaluate(
    observations: tuple[Observation, ...], *, tax_id: str, cutoff: datetime, country: str = "GR"
) -> MetricResult:
    """Select captured revisions before matching; evidence verification is external."""
    if (
        not valid_tax_id(tax_id)
        or country != "GR"
        or not isinstance(cutoff, datetime)
        or cutoff.utcoffset() != timedelta(0)
    ):
        raise SemanticError("semantic_selection")
    validate_observations(observations)
    grouped: dict[str, list[Observation]] = {}
    for row in observations:
        if row.observed_at <= cutoff:
            grouped.setdefault(row.source_id, []).append(row)
    records = tuple(_decision(grouped[key], tax_id) for key in sorted(grouped))
    matched = [record for record in records if record.matching_ordinals]
    buyers = tuple(
        BuyerRecordCount(
            buyer,
            tuple(row.source_id for row in matched if row.buyer_key == buyer),
            sum(row.buyer_key == buyer for row in matched),
            sum(row.buyer_key == buyer and row.cancelled is True for row in matched),
            sum(row.buyer_key == buyer and row.cancelled is None for row in matched),
        )
        for buyer in sorted({row.buyer_key for row in matched if row.buyer_key is not None})
    )
    unresolved = any(
        row.unassessed or row.ambiguous_candidate or row.unknown_suppliers for row in records
    )
    if not observations:
        status = "empty_capture"
    elif not records:
        status = "no_observations_before_cutoff"
    elif matched:
        status = "observed_participation"
    else:
        status = "selection_unresolved" if unresolved else "no_observed_participation"
    cancelled = sum(row.cancelled is True for row in matched)
    unknown = sum(row.cancelled is None for row in matched)
    return MetricResult(
        status,
        len(matched),
        cancelled,
        unknown,
        len(matched) - cancelled - unknown,
        buyers,
        tuple(row.source_id for row in matched if row.buyer_key is None),
        tuple(row.source_id for row in records if row.unassessed),
        tuple(row.source_id for row in records if row.ambiguous),
        tuple(row.source_id for row in records if row.unknown_suppliers),
        tuple(row.source_id for row in records if row.empty_suppliers),
        sum(row.invalid_supplier_count for row in records),
        records,
    )
