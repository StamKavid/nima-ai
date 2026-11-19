"""Known-time health cases never substitute a historical pass for a newer failure."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from nima.contracts.history import VALIDATOR_VERSION, HistoryError, Outcome, ValidationRecord
from nima.dataops.validation_health import assess_history
from tests.test_validation_history import intent

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
POLICY = {
    "contract_id": "nima.supplier-buyers-readout",
    "contract_version": "1.0.0",
    "contract_sha256": "c" * 64,
    "validator_version": VALIDATOR_VERSION,
}


def record(
    status: str = "passed", *, age: timedelta = timedelta(), number: int = 1
) -> ValidationRecord:
    value = intent()
    completed = NOW - age
    if status == "pending":
        return ValidationRecord(UUID(int=number), value, completed, None, None)
    outcome = (
        Outcome(value.digest, "passed", "byte_equivalence", "ok", "f" * 64, 1, 1)
        if status == "passed"
        else Outcome(
            value.digest,
            status,
            "artifact_integrity",
            "artifact_digest" if status == "failed" else "artifact_unavailable",
        )
    )
    return ValidationRecord(
        UUID(int=number), value, completed - timedelta(seconds=1), outcome, completed
    )


def assess(*records: ValidationRecord, **thresholds: int) -> dict[str, object]:
    return assess_history(
        "b" * 64,
        NOW,
        tuple(records),
        POLICY,
        max_check_age_hours=thresholds.get("hours", 24),
        max_pending_age_minutes=thresholds.get("minutes", 30),
    )


@pytest.mark.parametrize(
    "status,reason",
    [
        ("passed", None),
        ("failed", "latest_failed"),
        ("blocked", "latest_blocked"),
        ("pending", "latest_pending"),
    ],
)
def test_latest_state(status: str, reason: str | None) -> None:
    result = assess(record(status))
    assert result["status"] == ("checks_passed" if reason is None else "attention")
    assert result["reasons"] == ([] if reason is None else [reason])


def test_empty_and_exact_age_boundaries() -> None:
    assert assess()["reasons"] == ["no_checks"]
    assert assess(record(age=timedelta(hours=24)))["status"] == "checks_passed"
    assert assess(record(age=timedelta(hours=24, microseconds=1)))["reasons"] == ["stale_check"]
    for seconds, overdue in [(1800, False), (1801, True)]:
        reasons = assess(record("pending", age=timedelta(seconds=seconds)))["reasons"]
        assert isinstance(reasons, list) and ("overdue_pending" in reasons) == overdue


def test_late_older_completion_cannot_hide_newer_failure() -> None:
    old = replace(record(), started_at=NOW - timedelta(minutes=4))
    failed = record("failed", age=timedelta(minutes=1), number=2)
    result = assess(old, failed)
    assert result["reasons"] == ["latest_failed"]
    assert result["latest_attempt_ids"] == [str(failed.attempt_id)]


def test_recovery_retains_historical_counts_and_pending_attention() -> None:
    failed = record("failed", age=timedelta(hours=1), number=2)
    result = assess(failed, record())
    assert result["status"] == "checks_passed"
    counts = result["counts"]
    assert isinstance(counts, dict) and counts["failed"] == 1
    pending = record("pending", age=timedelta(minutes=31), number=3)
    assert assess(failed, pending, record())["reasons"] == ["overdue_pending"]


def test_policy_mismatch_ties_and_clock_anomalies() -> None:
    old = record()
    different = replace(old.intent, contract_version="0.9.0")
    outcome = Outcome(different.digest, "passed", "byte_equivalence", "ok", "f" * 64, 1, 1)
    assert assess(replace(old, intent=different, outcome=outcome))["reasons"] == [
        "latest_policy_mismatch"
    ]
    assert assess(old, replace(old, attempt_id=UUID(int=2)))["reasons"] == ["ambiguous_latest"]
    future = assess(replace(old, recorded_at=NOW + timedelta(seconds=1)))["reasons"]
    order = assess(replace(old, recorded_at=old.started_at - timedelta(seconds=1)))["reasons"]
    assert isinstance(future, list) and "future_timestamp" in future
    assert isinstance(order, list) and "clock_order" in order
    same = replace(
        old,
        started_at=old.started_at.astimezone(timezone(timedelta(hours=2))),
        recorded_at=NOW.astimezone(timezone(timedelta(hours=2))),
    )
    assert assess(same)["status"] == "checks_passed"


@pytest.mark.parametrize("hours,minutes", [(0, 30), (True, 30), (8761, 30), (24, 0), (24, 10081)])
def test_invalid_thresholds(hours: int, minutes: int) -> None:
    with pytest.raises(HistoryError, match="^validation_configuration$"):
        assess(record(), hours=hours, minutes=minutes)


def test_duplicate_or_mixed_artifact_selection_is_refused() -> None:
    value = record()
    with pytest.raises(HistoryError, match="^validation_integrity$"):
        assess(value, value)
    with pytest.raises(HistoryError, match="^validation_integrity$"):
        assess_history(
            "0" * 64, NOW, (value,), POLICY, max_check_age_hours=24, max_pending_age_minutes=30
        )
