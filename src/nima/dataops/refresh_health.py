"""Pure attention rules for one recorded refresh policy, without control actions."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from nima.dataops.health import HealthError, HealthResult
from nima.identity.artifacts import encode
from nima.orchestration.refresh import business_date
from nima.workflows.recovery import RecoveryBudget


@dataclass(frozen=True)
class RecentWindow:
    query_date: date
    observed_at: datetime | None
    latest_business_date: date | None


@dataclass(frozen=True)
class RefreshChild:
    query_date: date
    request_id: UUID
    run_id: UUID | None
    dispatch_state: str
    reconciled_at: datetime | None
    observed_at: datetime | None
    updated_at: datetime
    budget: RecoveryBudget


@dataclass(frozen=True)
class RefreshCycle:
    cycle_id: UUID
    business_date: date
    completed_at: datetime | None
    query_dates: tuple[date, ...]
    children: tuple[RefreshChild, ...]


@dataclass(frozen=True)
class PolicyHealthSample:
    policy_id: UUID
    sampled_at: datetime
    start: date
    state: str
    last_tick_at: datetime | None
    retired: bool
    compatible: bool
    missing_days: int
    oldest_missing: tuple[date, ...]
    recent: tuple[RecentWindow, ...]
    cycle: RefreshCycle | None


def validate_cycle(c: RefreshCycle) -> None:
    if (
        not 1 <= len(c.query_dates) <= 14
        or len(c.children) != len(c.query_dates)
        or tuple(sorted(set(c.query_dates))) != c.query_dates
        or tuple(child.query_date for child in c.children) != c.query_dates
    ):
        raise HealthError("refresh_health_evidence")


def validate_ages(tick: int, observation: int) -> None:
    if any(type(hours) is not int or not 1 <= hours <= 8760 for hours in (tick, observation)):
        raise HealthError("refresh_health_configuration")


def recent_dates(start: date, day: date) -> tuple[date, ...]:
    return tuple(
        date.fromordinal(n)
        for n in range(max(start.toordinal(), day.toordinal() - 7), day.toordinal())
    )


def _iso(value: datetime | None) -> str | None:
    if value is not None and value.utcoffset() is None:
        raise HealthError("refresh_health_evidence")
    return None if value is None else value.astimezone(UTC).isoformat()


def _age(
    value: datetime | None, now: datetime, hours: int, label: str, reasons: set[str]
) -> int | None:
    _iso(value)
    if value is None:
        reasons.add(f"{label}_unobserved")
        return None
    if value > now:
        reasons.add(f"future_{label}")
        return None
    delta = now - value
    if delta > timedelta(hours=hours):
        reasons.add(f"{label}_older_than_threshold")
    return int(delta.total_seconds())


def assess(
    sample: PolicyHealthSample, *, max_tick_age_hours: int, max_observation_age_hours: int
) -> HealthResult:
    validate_ages(max_tick_age_hours, max_observation_age_hours)
    s = sample
    _iso(s.sampled_at)
    day = business_date(s.sampled_at)
    due = recent_dates(s.start, day)
    if (
        s.state not in {"enabled", "paused", "pending"}
        or [r.query_date for r in s.recent] != list(due)
        or not 0 <= s.missing_days <= max(0, (day - s.start).days)
        or len(s.oldest_missing) != min(7, s.missing_days)
        or tuple(sorted(set(s.oldest_missing))) != s.oldest_missing
        or any(not s.start <= d < day for d in s.oldest_missing)
    ):
        raise HealthError("refresh_health_evidence")
    flags: set[str] = set()
    if s.retired:
        flags.add("policy_retired")
    elif s.state != "enabled":
        flags.add("policy_paused" if s.state == "paused" else "schedule_pending")
    if not s.compatible:
        flags.add("processing_incompatible")
    if s.missing_days:
        flags.add("coverage_gaps")
    tick_age = (
        _age(s.last_tick_at, s.sampled_at, max_tick_age_hours, "tick", flags) if due else None
    )
    recent: list[dict[str, object]] = []
    for window in s.recent:
        age = _age(
            window.observed_at, s.sampled_at, max_observation_age_hours, "observation", flags
        )
        reobserved = window.latest_business_date == day and window.observed_at is not None
        if not reobserved:
            flags.add("recent_window_not_reobserved")
        if window.latest_business_date is not None and window.latest_business_date > day:
            flags.add("future_business_date")
        recent.append(
            {
                "query_date": window.query_date.isoformat(),
                "last_observed_at": _iso(window.observed_at),
                "latest_completed_business_date": window.latest_business_date.isoformat()
                if window.latest_business_date
                else None,
                "reobserved_today": reobserved,
                "observation_age_seconds": age,
            }
        )
    cycle_report: dict[str, object] | None = None
    if s.cycle is not None:
        c = s.cycle
        validate_cycle(c)
        if c.completed_at is None:
            flags.add("cycle_unresolved")
        if c.business_date > day:
            flags.add("future_business_date")
        _iso(c.completed_at)
        if c.completed_at is not None and c.completed_at > s.sampled_at:
            flags.add("future_processing_clock")
        children: list[dict[str, object]] = []
        for child in c.children:
            reasons: set[str] = set()
            budget = child.budget
            for clock in (child.updated_at, budget.started_at, child.reconciled_at):
                _iso(clock)
                if clock is not None and clock > s.sampled_at:
                    reasons.add("future_processing_clock")
            _iso(child.observed_at)
            if child.observed_at is not None and child.observed_at > s.sampled_at:
                reasons.add("future_observation")
            if child.reconciled_at is None:
                reasons.add("child_unresolved")
                if child.dispatch_state == "sending":
                    reasons.add("dispatch_unknown")
                if budget.status in {"partial", "failed", "deferred"}:
                    reasons.add("child_incomplete")
                failure = budget.failure(s.sampled_at)
                if failure is not None and failure != "recovery_complete":
                    reasons.add(failure)
            elif budget.status != "complete" or child.observed_at is None:
                reasons.add("window_state_mismatch")
            flags.update(reasons)
            children.append(
                {
                    "query_date": child.query_date.isoformat(),
                    "request_id": str(child.request_id),
                    "run_id": str(child.run_id) if child.run_id else None,
                    "request_state": budget.status,
                    "dispatch_state": child.dispatch_state,
                    "reconciled_at": _iso(child.reconciled_at),
                    "source_observed_at": _iso(child.observed_at),
                    "processing_updated_at": _iso(child.updated_at),
                    "started_at": _iso(budget.started_at),
                    "consumed": {
                        "executions": budget.executions,
                        "attempts": budget.attempts,
                        "projection_batches": budget.projection_batches,
                        "dispatches": budget.dispatches,
                    },
                    "attention_reasons": sorted(reasons),
                }
            )
        cycle_report = {
            "cycle_id": str(c.cycle_id),
            "business_date": c.business_date.isoformat(),
            "completed_at": _iso(c.completed_at),
            "children": children,
        }
    status = "attention" if flags else "checks_passed"
    body = encode(
        {
            "artifact_version": "refresh-health-v1",
            "scope": "one_selected_policy_recorded_sql_state",
            "source": "kimdis.contract",
            "policy_id": str(s.policy_id),
            "state": s.state,
            "retired": s.retired,
            "execution_compatible": s.compatible,
            "sampled_at": _iso(s.sampled_at),
            "business_date": day.isoformat(),
            "last_tick_at": _iso(s.last_tick_at),
            "tick_age_seconds": tick_age,
            "thresholds": {
                "max_tick_age_hours": max_tick_age_hours,
                "max_observation_age_hours": max_observation_age_hours,
            },
            "coverage": {
                "start": s.start.isoformat(),
                "through": (day - timedelta(days=1)).isoformat(),
                "missing_days": s.missing_days,
                "oldest_missing_dates": [d.isoformat() for d in s.oldest_missing],
            },
            "recent": recent,
            "cycle": cycle_report,
            "worker_liveness": "unknown",
            "status": status,
            "attention_reasons": sorted(flags),
        }
    )
    if len(body) > 32 * 1024:
        raise HealthError("refresh_health_limit")
    return HealthResult(body, status, len(flags))
