"""Known-answer operational signals; no network/database/filesystem dependencies."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from nima.dataops.health import CapacitySample, CaptureSample, HealthError, build_report

NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)
RUN = UUID("10000000-0000-0000-0000-000000000001")


def capture() -> CaptureSample:
    return CaptureSample(
        run_id=RUN,
        sampled_at=NOW,
        status="complete",
        query_from="2026-11-06",
        query_to="2026-11-06",
        page_count=2,
        record_count=5,
        quarantined_count=0,
        observation_count=5,
        pending_projection_count=0,
        projection_version="test-projection-v1",
        oldest_observed_at=NOW - timedelta(hours=24),
        newest_observed_at=NOW,
        workflow_id=None,
        workflow_status=None,
        workflow_updated_at=None,
    )


def capacity() -> CapacitySample:
    return CapacitySample("/private/archive", NOW + timedelta(seconds=1), 1024, 10)


def document(c: CaptureSample | None = None, f: CapacitySample | None = None) -> dict[str, Any]:
    result = build_report(c or capture(), f or capacity(), max_age_hours=24, min_free_bytes=1024)
    return cast(dict[str, Any], json.loads(result.body))


def test_equal_thresholds_pass_with_explicit_narrow_scope_and_separate_clocks() -> None:
    report = document()
    assert report["status"] == "checks_passed" and report["attention_reasons"] == []
    assert report["artifact_version"] == "dataops-health-v1"
    assert report["capture"]["oldest_observation_age_seconds"] == 86400
    assert report["capture"]["query_window"] == {"from": "2026-11-06", "to": "2026-11-06"}
    assert report["capacity"]["sampled_at"] != report["capture"]["sampled_at"]
    assert report["capture"]["workflow"]["assessment"] == "not_linked"
    assert report["not_checked"] == [
        "archive_integrity",
        "field_reconciliation",
        "source_currentness",
        "worker_liveness",
        "scheduler_liveness",
        "execution_compatibility",
        "broader_coverage",
    ]
    assert (
        build_report(capture(), capacity(), max_age_hours=24, min_free_bytes=1024).attention_count
        == 0
    )


@pytest.mark.parametrize("delta", [timedelta(microseconds=1), timedelta(days=2)])
def test_old_first_page_is_attention_even_with_new_last_page(delta: timedelta) -> None:
    report = document(replace(capture(), oldest_observed_at=NOW - timedelta(hours=24) - delta))
    assert report["status"] == "attention"
    assert report["attention_reasons"] == ["capture_older_than_threshold"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("status", "running", "run_status_attention"),
        ("status", "failed", "run_status_attention"),
        ("pending_projection_count", 1, "projection_pending"),
        ("observation_count", 4, "record_count_mismatch"),
        ("workflow_status", "failed", "workflow_not_complete"),
        ("workflow_status", "deferred", "workflow_not_complete"),
        ("workflow_status", "running", "workflow_not_complete"),
    ],
)
def test_recorded_states_are_attention_without_liveness_or_repair_claims(
    field: str, value: Any, reason: str
) -> None:
    sample = replace(capture(), **{field: value})
    assert document(sample)["attention_reasons"] == [reason]


def test_future_or_unobserved_capture_never_becomes_fresh() -> None:
    future = document(replace(capture(), newest_observed_at=NOW + timedelta(microseconds=1)))
    assert future["attention_reasons"] == ["future_observation"]
    assert future["capture"]["oldest_observation_age_seconds"] is None
    absent = document(
        replace(
            capture(),
            oldest_observed_at=None,
            newest_observed_at=None,
            page_count=0,
            record_count=0,
            observation_count=0,
        )
    )
    assert absent["attention_reasons"] == ["capture_unobserved"]


def test_quarantine_is_reported_and_counter_check_accounts_for_it() -> None:
    report = document(
        replace(capture(), status="quarantined", quarantined_count=1, observation_count=4)
    )
    assert report["attention_reasons"] == ["run_status_attention", "quarantined_records"]


def test_complete_empty_page_and_unavailable_inode_total_are_explicit() -> None:
    sample = replace(capture(), record_count=0, observation_count=0)
    report = document(sample, replace(capacity(), available_inodes=None))
    assert report["status"] == "checks_passed"
    assert report["capacity"]["available_inodes"] is None
    assert report["capture"]["observation_count"] == 0


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"available_bytes": 1023}, "capacity_below_threshold"),
        ({"available_inodes": 0}, "no_free_inodes"),
    ],
)
def test_capacity_threshold_uses_available_resources(changes: dict[str, Any], reason: str) -> None:
    assert document(f=replace(capacity(), **changes))["attention_reasons"] == [reason]


@pytest.mark.parametrize(
    "hours,bytes_", [(0, 1), (8761, 1), (True, 1), (1, 0), (1, -1), (1, True), (1, 2**63)]
)
def test_invalid_thresholds_are_fixed_configuration_errors(hours: Any, bytes_: Any) -> None:
    with pytest.raises(HealthError, match="^health_configuration$"):
        build_report(capture(), capacity(), max_age_hours=hours, min_free_bytes=bytes_)


def test_naive_clock_is_unavailable_evidence_not_a_fresh_sample() -> None:
    with pytest.raises(HealthError, match="^health_evidence$"):
        document(replace(capture(), sampled_at=NOW.replace(tzinfo=None)))
