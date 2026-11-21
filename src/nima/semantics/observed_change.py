"""Observed change between two captures of one declared query (U4), never deletion or amendment.

A capture is one or more collection runs of one query with the versions they observed. The metric
says what the later capture did or did not contain relative to the earlier one, and it abstains
(``incomparable``, no categories) unless both captures are complete, ask the same question and are
strictly ordered in time. ``changed`` means the published record content differs; ``added`` means
the earlier capture did not contain it; ``missing_from_later_capture`` is never a deletion or a
legal event.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from typing import cast

from nima.semantics.participation import SemanticError
from nima.semantics.selection import Selected, select_latest

MAX_VERSIONS = 5000
MAX_RUNS = 100
_SHA = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class RunFacts:
    run_id: str
    query_sha256: str
    collection_complete: bool
    normalization_complete: bool
    quarantined: int
    observed_from: datetime
    observed_to: datetime


@dataclass(frozen=True)
class CapturedVersion:
    observation_id: int
    source_id: str
    content_sha256: str
    observed_at: datetime


@dataclass(frozen=True)
class Capture:
    runs: tuple[RunFacts, ...]
    versions: tuple[CapturedVersion, ...]


@dataclass(frozen=True)
class CaptureSummary:
    run_ids: tuple[str, ...]
    query_hashes: tuple[str, ...]
    records: int
    ambiguous_source_ids: tuple[str, ...]


@dataclass(frozen=True)
class Added:
    source_id: str
    later_version: str
    later_observation_ids: tuple[int, ...]


@dataclass(frozen=True)
class Changed:
    source_id: str
    earlier_version: str
    later_version: str
    earlier_observation_ids: tuple[int, ...]
    later_observation_ids: tuple[int, ...]


@dataclass(frozen=True)
class Missing:
    source_id: str
    earlier_version: str
    earlier_observation_ids: tuple[int, ...]


@dataclass(frozen=True)
class Counts:
    added: int
    changed: int
    missing_from_later_capture: int
    unchanged: int


@dataclass(frozen=True)
class MetricResult:
    status: str
    reasons: tuple[str, ...]
    earlier: CaptureSummary
    later: CaptureSummary
    counts: Counts
    added: tuple[Added, ...]
    changed: tuple[Changed, ...]
    missing_from_later_capture: tuple[Missing, ...]
    unchanged: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(json.dumps(asdict(self), allow_nan=False)))


def reference_sql() -> str:
    """Two bound inputs: the run facts and the observed versions of both captures, as JSON."""
    return files("nima.semantics").joinpath("observed_change.sql").read_text()


def definition() -> dict[str, object]:
    return {
        "metric": "observed_change_between_captures.v1",
        "status": "draft",
        "source": "kimdis.contract",
        "abstains": "incomparable_unless_both_complete_same_query_strictly_ordered",
        "reasons": [
            "no_runs",
            "not_later",
            "quarantined_records",
            "query_mismatch",
            "run_incomplete",
        ],
        "categories": ["added", "changed", "missing_from_later_capture", "unchanged"],
        "changed": "source_content_hash_differs_not_which_field_or_why",
        "missing": "never_deletion_withdrawal_or_a_legal_event",
        "revision": "latest_observed_within_each_capture_ties_excluded_and_listed",
        "sql_sha256": hashlib.sha256(reference_sql().encode()).hexdigest(),
    }


def definition_sha256() -> str:
    return hashlib.sha256(
        json.dumps(definition(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _utc(value: object) -> bool:
    return isinstance(value, datetime) and value.utcoffset() == timedelta(0)


def _valid_run(row: object) -> bool:
    return (
        isinstance(row, RunFacts)
        and isinstance(row.run_id, str)
        and 1 <= len(row.run_id) <= 64
        and isinstance(row.query_sha256, str)
        and _SHA.fullmatch(row.query_sha256) is not None
        and type(row.collection_complete) is bool
        and type(row.normalization_complete) is bool
        and type(row.quarantined) is int
        and row.quarantined >= 0
        and _utc(row.observed_from)
        and _utc(row.observed_to)
        and row.observed_from <= row.observed_to
    )


def _valid_version(row: object) -> bool:
    return (
        isinstance(row, CapturedVersion)
        and type(row.observation_id) is int
        and row.observation_id > 0
        and isinstance(row.source_id, str)
        and row.source_id.startswith("kimdis:")
        and bool(row.source_id[7:].strip())
        and isinstance(row.content_sha256, str)
        and _SHA.fullmatch(row.content_sha256) is not None
        and _utc(row.observed_at)
    )


def validate_captures(earlier: Capture, later: Capture) -> None:
    ids: set[int] = set()
    for capture in (earlier, later):
        if (
            not isinstance(capture, Capture)
            or not isinstance(capture.runs, tuple)
            or not isinstance(capture.versions, tuple)
            or len(capture.runs) > MAX_RUNS
            or len(capture.versions) > MAX_VERSIONS
            or not all(_valid_run(run) for run in capture.runs)
            or not all(_valid_version(version) for version in capture.versions)
        ):
            raise SemanticError("semantic_input")
        for version in capture.versions:
            if version.observation_id in ids:
                raise SemanticError("semantic_input")
            ids.add(version.observation_id)


def sql_rows(
    earlier: Capture, later: Capture
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Run rows and version rows for the reference SQL, each labelled with its capture."""
    validate_captures(earlier, later)
    runs: list[dict[str, object]] = []
    versions: list[dict[str, object]] = []
    for label, capture in (("earlier", earlier), ("later", later)):
        for run in capture.runs:
            runs.append(
                {
                    **asdict(run),
                    "capture": label,
                    "observed_from": run.observed_from.isoformat(),
                    "observed_to": run.observed_to.isoformat(),
                }
            )
        for version in capture.versions:
            versions.append(
                {
                    **asdict(version),
                    "capture": label,
                    "observed_at": version.observed_at.isoformat(),
                }
            )
    return runs, versions


def _selections(capture: Capture) -> tuple[Selected[CapturedVersion], ...]:
    if not capture.versions:
        return ()
    cutoff = max(version.observed_at for version in capture.versions)
    return select_latest(capture.versions, cutoff)


def _summary(capture: Capture, selections: tuple[Selected[CapturedVersion], ...]) -> CaptureSummary:
    return CaptureSummary(
        tuple(sorted(run.run_id for run in capture.runs)),
        tuple(sorted({run.query_sha256 for run in capture.runs})),
        sum(not item.ambiguous for item in selections),
        tuple(item.source_id for item in selections if item.ambiguous),
    )


def _reasons(earlier: Capture, later: Capture) -> tuple[str, ...]:
    every = (*earlier.runs, *later.runs)
    found = []
    if not earlier.runs or not later.runs:
        found.append("no_runs")
    if any(not (run.collection_complete and run.normalization_complete) for run in every):
        found.append("run_incomplete")
    if any(run.quarantined > 0 for run in every):
        found.append("quarantined_records")
    if len({run.query_sha256 for run in every}) > 1:
        found.append("query_mismatch")
    if (
        earlier.runs
        and later.runs
        and max(run.observed_to for run in earlier.runs)
        >= min(run.observed_from for run in later.runs)
    ):
        found.append("not_later")
    return tuple(sorted(found))


def _version(item: Selected[CapturedVersion]) -> str:
    return next(iter(item.versions))


def _observation_ids(item: Selected[CapturedVersion]) -> tuple[int, ...]:
    return tuple(sorted(row.observation_id for row in item.current))


def evaluate(earlier: Capture, later: Capture) -> MetricResult:
    """Compare two captures; verification that each run is complete happens where runs are read."""
    validate_captures(earlier, later)
    first, second = _selections(earlier), _selections(later)
    summaries = (_summary(earlier, first), _summary(later, second))
    reasons = _reasons(earlier, later)
    added: list[Added] = []
    changed: list[Changed] = []
    missing: list[Missing] = []
    unchanged: list[str] = []
    if not reasons:
        before = {item.source_id: item for item in first if not item.ambiguous}
        after = {item.source_id: item for item in second if not item.ambiguous}
        excluded = set(summaries[0].ambiguous_source_ids) | set(summaries[1].ambiguous_source_ids)
        only_after = sorted(set(after) - set(before) - excluded)
        only_before = sorted(set(before) - set(after) - excluded)
        in_both = sorted((set(before) & set(after)) - excluded)
        added = [
            Added(sid, _version(after[sid]), _observation_ids(after[sid])) for sid in only_after
        ]
        missing = [
            Missing(sid, _version(before[sid]), _observation_ids(before[sid]))
            for sid in only_before
        ]
        for source_id in in_both:
            old, new = before[source_id], after[source_id]
            if _version(old) != _version(new):
                changed.append(
                    Changed(
                        source_id,
                        _version(old),
                        _version(new),
                        _observation_ids(old),
                        _observation_ids(new),
                    )
                )
            else:
                unchanged.append(source_id)
    if reasons:
        status = "incomparable"
    elif added or changed or missing:
        status = "observed_changes"
    else:
        status = "no_observed_change"
    return MetricResult(
        status,
        reasons,
        summaries[0],
        summaries[1],
        Counts(len(added), len(changed), len(missing), len(unchanged)),
        tuple(added),
        tuple(changed),
        tuple(missing),
        tuple(unchanged),
    )
