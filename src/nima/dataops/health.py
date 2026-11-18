"""Pure selected-capture attention policy; no source-current or liveness inference."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from nima.identity.artifacts import encode

VERSION = "dataops-health-v1"


class HealthError(ValueError):
    """Fixed operational reason without driver messages, source fields or paths."""


@dataclass(frozen=True)
class CaptureSample:
    run_id: UUID
    sampled_at: datetime
    status: str
    query_from: str | None
    query_to: str | None
    page_count: int
    record_count: int
    quarantined_count: int
    observation_count: int
    pending_projection_count: int
    projection_version: str
    oldest_observed_at: datetime | None
    newest_observed_at: datetime | None
    workflow_id: UUID | None
    workflow_status: str | None
    workflow_updated_at: datetime | None


@dataclass(frozen=True)
class CapacitySample:
    directory: str
    sampled_at: datetime
    available_bytes: int
    available_inodes: int | None


@dataclass(frozen=True)
class HealthResult:
    body: bytes
    status: str
    attention_count: int


def validate_thresholds(max_age_hours: int, min_free_bytes: int) -> None:
    if (
        type(max_age_hours) is not int
        or not 1 <= max_age_hours <= 8760
        or type(min_free_bytes) is not int
        or not 1 <= min_free_bytes <= 2**63 - 1
    ):
        raise HealthError("health_configuration")


def _time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.utcoffset() is None:
        raise HealthError("health_evidence")
    return value.astimezone(UTC).isoformat()


def build_report(
    capture: CaptureSample,
    capacity: CapacitySample,
    *,
    max_age_hours: int,
    min_free_bytes: int,
) -> HealthResult:
    """Compare exact age/available-capacity boundaries; retain unknown measurements."""
    validate_thresholds(max_age_hours, min_free_bytes)
    c, f = capture, capacity
    # Reject unusable clocks before datetime arithmetic or private publication.
    for clock in (
        c.sampled_at,
        c.oldest_observed_at,
        c.newest_observed_at,
        c.workflow_updated_at,
        f.sampled_at,
    ):
        _time(clock)
    flags: list[str] = []
    if c.status != "complete":
        flags.append("run_status_attention")
    age: int | None = None
    if c.oldest_observed_at is None or c.newest_observed_at is None:
        flags.append("capture_unobserved")
    elif c.newest_observed_at > c.sampled_at:
        flags.append("future_observation")
    else:
        delta = c.sampled_at - c.oldest_observed_at
        age = int(delta.total_seconds())
        if delta > timedelta(hours=max_age_hours):
            flags.append("capture_older_than_threshold")
    if c.quarantined_count:
        flags.append("quarantined_records")
    if c.observation_count != c.record_count - c.quarantined_count:
        flags.append("record_count_mismatch")
    if c.pending_projection_count:
        flags.append("projection_pending")
    if c.workflow_status is not None and c.workflow_status != "complete":
        flags.append("workflow_not_complete")
    if f.available_bytes < min_free_bytes:
        flags.append("capacity_below_threshold")
    if f.available_inodes == 0:
        flags.append("no_free_inodes")
    status = "attention" if flags else "checks_passed"
    body = encode(
        {
            "artifact_version": VERSION,
            "status": status,
            "scope": "one_selected_kimdis_run_and_operator_selected_filesystem",
            "thresholds": {
                "max_capture_age_hours": max_age_hours,
                "min_free_bytes": min_free_bytes,
            },
            "attention_reasons": flags,
            "capture": {
                "run_id": str(c.run_id),
                "sampled_at": _time(c.sampled_at),
                "recorded_status": c.status,
                "query_window": {"from": c.query_from, "to": c.query_to},
                "page_count": c.page_count,
                "record_count": c.record_count,
                "quarantined_count": c.quarantined_count,
                "observation_count": c.observation_count,
                "pending_projection_count": c.pending_projection_count,
                "projection_version": c.projection_version,
                "oldest_observed_at": _time(c.oldest_observed_at),
                "newest_observed_at": _time(c.newest_observed_at),
                "oldest_observation_age_seconds": age,
                "workflow": {
                    "assessment": "not_linked" if c.workflow_status is None else "reported",
                    "request_id": None if c.workflow_id is None else str(c.workflow_id),
                    "status": c.workflow_status,
                    "updated_at": _time(c.workflow_updated_at),
                },
            },
            "capacity": {
                "directory": f.directory,
                "sampled_at": _time(f.sampled_at),
                "available_bytes": f.available_bytes,
                "available_inodes": f.available_inodes,
                "binding": "operator_selected_target; archive_binding_not_verified",
            },
            "measurement_consistency": "database_repeatable_read; filesystem_sampled_after_sql",
            "not_checked": [
                "archive_integrity",
                "field_reconciliation",
                "source_currentness",
                "worker_liveness",
                "scheduler_liveness",
                "execution_compatibility",
                "broader_coverage",
            ],
            "meaning": (
                "Limited operational checks; no source-current, company-absence "
                "or whole-platform health claim"
            ),
        }
    )
    return HealthResult(body, status, len(flags))
