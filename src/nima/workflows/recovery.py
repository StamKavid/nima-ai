"""Conservative headroom required for an explicit same-request recovery send."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class RecoveryBudget:
    status: str
    started_at: datetime | None
    executions: int
    attempts: int
    projection_batches: int
    dispatches: int

    def failure(self, sampled_at: datetime) -> str | None:
        if self.status == "complete":
            return "recovery_complete"
        if self.started_at is not None:
            if self.started_at > sampled_at:
                return "recovery_clock"
            if sampled_at - self.started_at > timedelta(minutes=30):
                return "workflow_deadline"
        for consumed, cap, reason in (
            (self.executions, 4, "workflow_execution_limit"),
            (self.attempts, 300, "workflow_attempt_limit"),
            (self.projection_batches, 100, "projection_budget"),
            (self.dispatches, 4, "recovery_dispatch_limit"),
        ):
            if consumed >= cap:
                return reason
        return None
