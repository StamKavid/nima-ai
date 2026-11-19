"""Pure selected-journal assessment, separate from current evidence/source health."""

import json
from datetime import UTC, datetime, timedelta
from typing import cast

from nima.contracts import CONTRACT_ID, ContractError, bound_contract
from nima.contracts.history import (
    VALIDATOR_VERSION,
    HistoryError,
    ValidationRecord,
    digest,
    valid_digest,
)
from nima.storage.validations import read_validation_history


def validate_thresholds(hours: int, minutes: int) -> None:
    if (
        type(hours) is not int
        or type(minutes) is not int
        or not 1 <= hours <= 8760
        or not 1 <= minutes <= 10080
    ):
        raise HistoryError("validation_configuration")


def current_policy() -> dict[str, str]:
    try:
        metadata = bound_contract()
        return {
            "contract_id": metadata["id"],
            "contract_version": metadata["version"],
            "contract_sha256": digest(metadata),
            "validator_version": VALIDATOR_VERSION,
        }
    except ContractError:
        raise HistoryError("validation_policy") from None


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def assess_history(
    artifact: str,
    sampled_at: datetime,
    records: tuple[ValidationRecord, ...],
    policy: dict[str, str],
    *,
    max_check_age_hours: int,
    max_pending_age_minutes: int,
) -> dict[str, object]:
    validate_thresholds(max_check_age_hours, max_pending_age_minutes)
    if not valid_digest(artifact):
        raise HistoryError("validation_configuration")
    if (
        not isinstance(sampled_at, datetime)
        or sampled_at.utcoffset() is None
        or len({r.attempt_id for r in records}) != len(records)
        or any(r.intent.artifact_sha256 != artifact for r in records)
    ):
        raise HistoryError("validation_integrity")
    keys = {"contract_id", "contract_version", "contract_sha256", "validator_version"}
    if (
        set(policy) != keys
        or policy["contract_id"] != CONTRACT_ID
        or policy["validator_version"] != VALIDATOR_VERSION
        or not valid_digest(policy["contract_sha256"])
    ):
        raise HistoryError("validation_configuration")
    now = sampled_at.astimezone(UTC)
    reasons = set()
    counts = {
        name: sum(r.status == name for r in records)
        for name in ("pending", "passed", "failed", "blocked")
    }
    matching = [r for r in records if {k: r.intent.payload()[k] for k in keys} == policy]
    counts.update(attempts=len(records), current_policy_attempts=len(matching))
    overdue = sum(
        r.outcome is None
        and now - r.started_at.astimezone(UTC) > timedelta(minutes=max_pending_age_minutes)
        for r in records
    )
    counts["overdue_pending"] = overdue
    if overdue:
        reasons.add("overdue_pending")
    for r in records:
        start = r.started_at.astimezone(UTC)
        end = None if r.recorded_at is None else r.recorded_at.astimezone(UTC)
        if start > now or (end is not None and end > now):
            reasons.add("future_timestamp")
        if end is not None and end < start:
            reasons.add("clock_order")
    latest = []
    if not records:
        reasons.add("no_checks")
    else:
        last_start = max(r.started_at.astimezone(UTC) for r in records)
        latest = [r for r in records if r.started_at.astimezone(UTC) == last_start]
        if len(latest) > 1:
            reasons.add("ambiguous_latest")
        else:
            last = latest[0]
            if last.status != "passed":
                reasons.add("latest_" + last.status)
            if last not in matching:
                reasons.add("latest_policy_mismatch")
            if last.recorded_at is not None and now - last.recorded_at.astimezone(UTC) > timedelta(
                hours=max_check_age_hours
            ):
                reasons.add("stale_check")
    passed = [
        cast(datetime, r.recorded_at).astimezone(UTC) for r in matching if r.status == "passed"
    ]
    single = latest[0] if len(latest) == 1 else None
    result: dict[str, object] = {
        "version": "nima-validation-health-v1",
        "artifact_sha256": artifact,
        "sampled_at": _iso(now),
        "verification_scope": "recorded_validation_history_only",
        "policy": dict(policy),
        "thresholds": {
            "max_check_age_hours": max_check_age_hours,
            "max_pending_age_minutes": max_pending_age_minutes,
        },
        "status": "attention" if reasons else "checks_passed",
        "reasons": sorted(reasons),
        "counts": counts,
        "latest_attempt_ids": sorted(str(r.attempt_id) for r in latest),
        "latest_started_at": _iso(latest[0].started_at) if latest else None,
        "latest_status": None if not latest else "ambiguous" if single is None else single.status,
        "latest_recorded_at": None if single is None else _iso(single.recorded_at),
        "last_current_policy_passed_at": _iso(max(passed)) if passed else None,
    }
    if len(json.dumps(result, allow_nan=False).encode()) > 64 * 1024:
        raise HistoryError("validation_limit")
    return result


def prepare_validation_health(
    dsn: str,
    artifact: str,
    *,
    max_check_age_hours: int,
    max_pending_age_minutes: int,
) -> dict[str, object]:
    validate_thresholds(max_check_age_hours, max_pending_age_minutes)
    policy = current_policy()
    sampled, records = read_validation_history(dsn, artifact)
    return assess_history(
        artifact,
        sampled,
        records,
        policy,
        max_check_age_hours=max_check_age_hours,
        max_pending_age_minutes=max_pending_age_minutes,
    )
