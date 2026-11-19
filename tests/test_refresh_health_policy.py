"""Policy attention uses recorded clocks/coverage, never a request success label alone."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from nima.dataops.health import HealthError
from nima.dataops.refresh_health import (
    PolicyHealthSample,
    RecentWindow,
    RefreshChild,
    RefreshCycle,
    assess,
)
from nima.workflows.recovery import RecoveryBudget

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
DAY = date(2026, 11, 19)


def sample() -> PolicyHealthSample:
    day = DAY - timedelta(days=1)
    child = RefreshChild(
        day,
        uuid4(),
        uuid4(),
        "accepted",
        NOW,
        NOW,
        NOW,
        RecoveryBudget("complete", NOW, 1, 1, 1, 1),
    )
    return PolicyHealthSample(
        uuid4(),
        NOW,
        day,
        "enabled",
        NOW,
        False,
        True,
        0,
        (),
        (RecentWindow(day, NOW, DAY),),
        RefreshCycle(uuid4(), DAY, NOW, (day,), (child,)),
    )


def report(value: PolicyHealthSample) -> dict[str, object]:
    return json.loads(assess(value, max_tick_age_hours=24, max_observation_age_hours=24).body)


def test_checks_passed_is_only_a_selected_recorded_assessment() -> None:
    value = report(sample())
    assert value["status"] == "checks_passed" and value["attention_reasons"] == []
    assert value["worker_liveness"] == "unknown"
    assert value["artifact_version"] == "refresh-health-v1"


@pytest.mark.parametrize("micros,attention", [(0, False), (1, True)])
def test_observation_and_processing_clocks_have_independent_exact_age_limits(
    micros: int,
    attention: bool,
) -> None:
    clock = NOW - timedelta(hours=24, microseconds=micros)
    value = sample()
    tick = report(replace(value, last_tick_at=clock))
    assert ("tick_older_than_threshold" in tick["attention_reasons"]) is attention
    observed = report(replace(value, recent=(replace(value.recent[0], observed_at=clock),)))
    assert ("observation_older_than_threshold" in observed["attention_reasons"]) is attention
    assert "tick_older_than_threshold" not in observed["attention_reasons"]


@pytest.mark.parametrize(
    "kind",
    ["missing_tick", "missing_observation", "future_tick", "future_observation", "old_overlap"],
)
def test_missing_future_and_unreobserved_windows_never_turn_green(kind: str) -> None:
    value = sample()
    if kind.endswith("tick"):
        value = replace(
            value, last_tick_at=None if kind.startswith("missing") else NOW + timedelta(seconds=1)
        )
    else:
        window = value.recent[0]
        window = (
            replace(window, latest_business_date=DAY - timedelta(days=1))
            if kind == "old_overlap"
            else replace(
                window,
                observed_at=None if kind.startswith("missing") else NOW + timedelta(seconds=1),
            )
        )
        value = replace(value, recent=(window,))
    assert report(value)["status"] == "attention"


@pytest.mark.parametrize(
    "reason,changes",
    [
        ("policy_paused", {"state": "paused"}),
        ("policy_retired", {"retired": True}),
        ("schedule_pending", {"state": "pending"}),
        ("processing_incompatible", {"compatible": False}),
        ("coverage_gaps", {"missing_days": 1, "oldest_missing": (DAY - timedelta(days=1),)}),
    ],
)
def test_policy_attention_dimensions_stay_explicit(reason: str, changes: dict[str, object]) -> None:
    value = report(replace(sample(), **changes))
    assert reason in value["attention_reasons"]


@pytest.mark.parametrize(
    "status",
    ["queued", "running", "collected", "projecting", "partial", "failed", "deferred", "complete"],
)
def test_unreconciled_child_cannot_hide_behind_recent_data_or_complete_status(status: str) -> None:
    value = sample()
    assert value.cycle is not None
    child = replace(
        value.cycle.children[0],
        reconciled_at=None,
        observed_at=None,
        budget=RecoveryBudget(status, NOW - timedelta(minutes=31), 4, 300, 100, 4),
    )
    value = replace(value, cycle=replace(value.cycle, completed_at=None, children=(child,)))
    result = report(value)
    assert "cycle_unresolved" in result["attention_reasons"]
    cycle = result["cycle"]
    assert isinstance(cycle, dict)
    assert cycle["children"][0]["attention_reasons"]
    if status != "complete":
        assert "workflow_deadline" in cycle["children"][0]["attention_reasons"]


def test_cardinality_and_naive_clocks_are_evidence_failures() -> None:
    value = sample()
    assert value.cycle is not None
    for corrupted in (
        replace(value, sampled_at=NOW.replace(tzinfo=None)),
        replace(value, cycle=replace(value.cycle, children=())),
    ):
        with pytest.raises(HealthError, match="^refresh_health_evidence$"):
            report(corrupted)


@pytest.mark.parametrize("hours", [0, 8761, True, "private"])
def test_invalid_thresholds_refuse_without_echoing_input(hours: object) -> None:
    from typing import cast

    with pytest.raises(HealthError, match="^refresh_health_configuration$"):
        assess(sample(), max_tick_age_hours=cast(int, hours), max_observation_age_hours=24)
