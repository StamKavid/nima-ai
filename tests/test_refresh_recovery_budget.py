"""Recovery headroom is explicit; equality at the deadline is still eligible."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from nima.workflows.recovery import RecoveryBudget

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
BUDGET = RecoveryBudget("deferred", NOW - timedelta(minutes=5), 1, 3, 0, 1)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("status", "complete", "recovery_complete"),
        ("executions", 4, "workflow_execution_limit"),
        ("attempts", 300, "workflow_attempt_limit"),
        ("projection_batches", 100, "projection_budget"),
        ("dispatches", 4, "recovery_dispatch_limit"),
        ("started_at", NOW + timedelta(microseconds=1), "recovery_clock"),
        ("started_at", NOW - timedelta(minutes=30, microseconds=1), "workflow_deadline"),
    ],
)
def test_each_original_budget_can_refuse_a_send(field: str, value: object, reason: str) -> None:
    assert replace(BUDGET, **{field: value}).failure(NOW) == reason


def test_queued_and_exact_remaining_headroom_are_eligible() -> None:
    assert (
        replace(BUDGET, status="queued", started_at=None, executions=0, attempts=0).failure(NOW)
        is None
    )
    assert (
        replace(
            BUDGET,
            started_at=NOW - timedelta(minutes=30),
            executions=3,
            attempts=299,
            projection_batches=99,
            dispatches=3,
        ).failure(NOW)
        is None
    )
