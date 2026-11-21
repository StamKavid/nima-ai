"""Captured contract records by CPV base code and reported month (U2), never spend or share.

A record is counted once under each distinct reported CPV base code (the first eight digits) of
its latest observed version, in the calendar month of its reported submission date. Overlap
between codes is real and is disclosed: the cells of one month can add up to more than that
month's distinct records. Records with no reported code are unclassified; records whose date is
missing or not in a measured shape sit in the unknown period. No code is checked against a CPV
release (``not_checked``).
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from typing import cast

from nima.semantics.selection import Selected, select_latest
from nima.semantics.timemodel import TIME_MODEL_VERSION, parse_reported_submission

NORMALIZER = "kimdis-normalized-v1"
MAX_OBSERVATIONS = 5000
MAX_ASSERTIONS = 1000
STATUSES = frozenset({"reported", "missing", "null", "empty", "invalid"})
_CODE = re.compile(r"[0-9]{8}-[0-9]")
_BASE = re.compile(r"[0-9]{8}")
_PERIOD = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
_SHA = re.compile(r"[0-9a-f]{64}")


class SemanticError(ValueError):
    """Fixed reason only; source values never enter exception messages."""


@dataclass(frozen=True)
class CpvAssertion:
    status: str
    code: str | None


@dataclass(frozen=True)
class Observation:
    observation_id: int
    source_id: str
    normalizer_version: str
    content_sha256: str
    observed_at: datetime
    cancelled: bool | None
    submitted_text: str | None
    cpv: tuple[CpvAssertion, ...] | None


@dataclass(frozen=True)
class RecordDecision:
    source_id: str
    version_hashes: tuple[str, ...]
    observation_ids: tuple[int, ...]
    ambiguous: bool
    period: str | None
    date_outcome: str | None
    cpv_base_codes: tuple[str, ...]
    classification: str | None
    cancelled: bool | None


@dataclass(frozen=True)
class Cell:
    cpv_base_code: str | None
    period: str | None
    record_count: int
    source_ids: tuple[str, ...]
    cancelled_count: int
    unknown_cancellation_count: int


@dataclass(frozen=True)
class PeriodTotal:
    period: str | None
    record_count: int


@dataclass(frozen=True)
class Coverage:
    selected_records: int
    classified: int
    unclassified_no_reported_code: int
    unclassified_metadata_unavailable: int
    period_parsed: int
    period_absent: int
    period_unparseable: int


@dataclass(frozen=True)
class MetricResult:
    status: str
    cells: tuple[Cell, ...]
    period_totals: tuple[PeriodTotal, ...]
    coverage: Coverage
    ambiguous_source_ids: tuple[str, ...]
    records: tuple[RecordDecision, ...]

    def payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(json.dumps(asdict(self), allow_nan=False)))


def reference_sql() -> str:
    """Five bound inputs: observation JSON, UTC cutoff, CPV base code, first and last month."""
    return files("nima.semantics").joinpath("cpv_period.sql").read_text()


def definition() -> dict[str, object]:
    return {
        "metric": "captured_record_count_by_cpv_period.v1",
        "status": "draft",
        "source": "kimdis.contract",
        "normalizer": NORMALIZER,
        "time_model": TIME_MODEL_VERSION,
        "period": "month_of_reported_submission_date_zone_less_read_as_athens_civil",
        "cpv": "reported_main_code_first_eight_digits_distinct_per_record",
        "taxonomy_validation": "not_checked",
        "unclassified": "no_reported_code_or_metadata_unavailable_kept_visible",
        "unknown_period": "absent_or_unparseable_date_kept_visible",
        "revision": "latest_captured_before_filters_ties_unresolved",
        "grain": "distinct_source_id_per_cpv_and_period",
        "cancellation": "include_true_false_unknown_with_breakdown",
        "overlap": "record_under_each_distinct_code_period_total_counts_it_once",
        "sql_sha256": hashlib.sha256(reference_sql().encode()).hexdigest(),
    }


def definition_sha256() -> str:
    return hashlib.sha256(
        json.dumps(definition(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_assertion(value: object) -> bool:
    if not isinstance(value, CpvAssertion) or value.status not in STATUSES:
        return False
    if value.status == "reported":
        return isinstance(value.code, str) and _CODE.fullmatch(value.code) is not None
    return value.code is None


def _valid_observation(row: object) -> bool:
    return (
        isinstance(row, Observation)
        and type(row.observation_id) is int
        and row.observation_id > 0
        and isinstance(row.source_id, str)
        and row.source_id.startswith("kimdis:")
        and bool(row.source_id[7:].strip())
        and row.normalizer_version == NORMALIZER
        and isinstance(row.content_sha256, str)
        and _SHA.fullmatch(row.content_sha256) is not None
        and isinstance(row.observed_at, datetime)
        and row.observed_at.utcoffset() == timedelta(0)
        and (row.cancelled is None or type(row.cancelled) is bool)
        and (row.submitted_text is None or isinstance(row.submitted_text, str))
        and (
            row.cpv is None
            or (
                isinstance(row.cpv, tuple)
                and len(row.cpv) <= MAX_ASSERTIONS
                and all(_valid_assertion(item) for item in row.cpv)
            )
        )
    )


def validate_observations(observations: tuple[Observation, ...]) -> None:
    if not isinstance(observations, tuple) or len(observations) > MAX_OBSERVATIONS:
        raise SemanticError("semantic_input")
    ids = set()
    versions: dict[tuple[str, str], tuple[object, ...]] = {}
    for row in observations:
        if not _valid_observation(row) or row.observation_id in ids:
            raise SemanticError("semantic_input")
        ids.add(row.observation_id)
        key = (row.source_id, row.content_sha256)
        facts = (row.cancelled, row.submitted_text, row.cpv)
        if key in versions and versions[key] != facts:
            raise SemanticError("semantic_version_conflict")
        versions[key] = facts


def sql_rows(observations: tuple[Observation, ...]) -> list[dict[str, object]]:
    """Rows for the reference SQL; the period is parsed here by the shared time model."""
    validate_observations(observations)
    rows: list[dict[str, object]] = []
    for row in observations:
        date = parse_reported_submission(row.submitted_text)
        rows.append(
            {
                "observation_id": row.observation_id,
                "source_id": row.source_id,
                "content_sha256": row.content_sha256,
                "observed_at": row.observed_at.isoformat(),
                "cancelled": row.cancelled,
                "period": date.period,
                "date_outcome": date.outcome,
                "cpv": None if row.cpv is None else [asdict(item) for item in row.cpv],
            }
        )
    return rows


def _base_codes(row: Observation) -> tuple[str, ...]:
    reported = {item.code[:8] for item in row.cpv or () if item.status == "reported" and item.code}
    return tuple(sorted(reported))


def _decision(selected: Selected[Observation]) -> RecordDecision:
    hashes = tuple(sorted(selected.versions))
    observation_ids = tuple(sorted(row.observation_id for row in selected.current))
    if selected.ambiguous:
        return RecordDecision(
            selected.source_id, hashes, observation_ids, True, None, None, (), None, None
        )
    chosen = selected.chosen
    date = parse_reported_submission(chosen.submitted_text)
    bases = _base_codes(chosen)
    if chosen.cpv is None:
        classification = "unclassified_metadata_unavailable"
    else:
        classification = "classified" if bases else "unclassified_no_reported_code"
    return RecordDecision(
        selected.source_id,
        hashes,
        observation_ids,
        False,
        date.period,
        date.outcome,
        bases,
        classification,
        chosen.cancelled,
    )


def _validate_selection(
    cutoff: object, cpv_base_code: object, period_from: object, period_to: object
) -> None:
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() != timedelta(0):
        raise SemanticError("semantic_selection")
    if cpv_base_code is not None and (
        not isinstance(cpv_base_code, str) or _BASE.fullmatch(cpv_base_code) is None
    ):
        raise SemanticError("semantic_selection")
    for month in (period_from, period_to):
        if month is not None and (not isinstance(month, str) or _PERIOD.fullmatch(month) is None):
            raise SemanticError("semantic_selection")
    if isinstance(period_from, str) and isinstance(period_to, str) and period_from > period_to:
        raise SemanticError("semantic_selection")


def _in_period(period: str | None, first: str | None, last: str | None) -> bool:
    if first is None and last is None:
        return True
    return (
        period is not None
        and (first is None or period >= first)
        and (last is None or period <= last)
    )


def evaluate(
    observations: tuple[Observation, ...],
    *,
    cutoff: datetime,
    cpv_base_code: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
) -> MetricResult:
    """Select captured revisions before placing records; evidence verification is external."""
    _validate_selection(cutoff, cpv_base_code, period_from, period_to)
    validate_observations(observations)
    decisions = tuple(_decision(selected) for selected in select_latest(observations, cutoff))
    placed = [row for row in decisions if not row.ambiguous]
    cancelled_of = {row.source_id: row.cancelled for row in placed}
    grouped: dict[tuple[str | None, str | None], list[str]] = {}
    for row in placed:
        codes: tuple[str | None, ...] = row.cpv_base_codes or (None,)
        for code in codes:
            if cpv_base_code is not None and code != cpv_base_code:
                continue
            if not _in_period(row.period, period_from, period_to):
                continue
            grouped.setdefault((code, row.period), []).append(row.source_id)
    order = sorted(grouped, key=lambda k: (k[0] is None, k[0] or "", k[1] is None, k[1] or ""))
    cells = tuple(
        Cell(
            code,
            period,
            len(ids),
            tuple(sorted(ids)),
            sum(cancelled_of[i] is True for i in ids),
            sum(cancelled_of[i] is None for i in ids),
        )
        for code, period in order
        for ids in [grouped[(code, period)]]
    )
    per_period: dict[str | None, set[str]] = {}
    for (_, period), ids in grouped.items():
        per_period.setdefault(period, set()).update(ids)
    totals = tuple(
        PeriodTotal(period, len(per_period[period]))
        for period in sorted(per_period, key=lambda p: (p is None, p or ""))
    )
    coverage = Coverage(
        len(placed),
        sum(row.classification == "classified" for row in placed),
        sum(row.classification == "unclassified_no_reported_code" for row in placed),
        sum(row.classification == "unclassified_metadata_unavailable" for row in placed),
        sum(row.date_outcome == "parsed" for row in placed),
        sum(row.date_outcome == "absent" for row in placed),
        sum(row.date_outcome == "unparseable" for row in placed),
    )
    ambiguous = tuple(row.source_id for row in decisions if row.ambiguous)
    unresolved = (
        bool(ambiguous)
        or (
            cpv_base_code is not None
            and coverage.unclassified_no_reported_code + coverage.unclassified_metadata_unavailable
            > 0
        )
        or (
            (period_from is not None or period_to is not None)
            and coverage.period_absent + coverage.period_unparseable > 0
        )
    )
    if not observations:
        status = "empty_capture"
    elif not decisions:
        status = "no_observations_before_cutoff"
    elif cells:
        status = "observed_activity"
    else:
        status = "selection_unresolved" if unresolved else "no_observed_activity"
    return MetricResult(status, cells, totals, coverage, ambiguous, decisions)
