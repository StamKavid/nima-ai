"""Opt-in bounded stage diagnostics; SQL journals remain authoritative."""

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import UUID, uuid4

import psycopg

from nima.ingestion.archive import ArchiveError
from nima.storage.postgres import CheckpointError, MigrationError
from nima.storage.workflows import WorkflowError

Stage = Literal["prepare", "collect", "project", "finalize"]
Event = Literal["started", "run_selected", "succeeded", "failed", "interrupted"]
_WRITE_LOCK = Lock()
_REASONS = frozenset(
    {
        "archive_invalid",
        "archive_io",
        "collection_incomplete",
        "database",
        "database_schema",
        "diagnostics_unavailable",
        "identity_coverage",
        "invalid_page",
        "invalid_projection",
        "page_limit",
        "pagination_changed",
        "projection_budget",
        "projection_busy",
        "projection_incomplete",
        "quarantined",
        "request_conflict",
        "request_unavailable",
        "request_unprepared",
        "request_version",
        "response_size",
        "retry_delay",
        "retry_exhausted",
        "run_busy",
        "run_unavailable",
        "source_busy",
        "source_changed",
        "time_budget",
        "transport",
        "unsupported_encoding",
        "workflow_attempt_limit",
        "workflow_deadline",
        "workflow_execution_limit",
        "workflow_fenced",
        "workflow_not_started",
    }
) | frozenset(f"http_{status}" for status in range(100, 600))


def _failure(error: BaseException) -> tuple[str, bool]:
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return "interrupted", False
    if isinstance(error, WorkflowError):
        if error.reason in _REASONS:
            return error.reason, error.retryable is True
        return "unrecognized_failure", False
    if isinstance(error, psycopg.Error):
        return "database", True
    if isinstance(error, (CheckpointError, MigrationError)):
        return "run_unavailable", False
    if isinstance(error, (OSError, ArchiveError)):
        return "archive_invalid", False
    return "unexpected_error", False


@dataclass
class StageEvents:
    stage: Stage
    request: UUID
    enabled: bool
    invocation: UUID = field(default_factory=uuid4)
    run: UUID | None = None

    def bind_run(self, run: UUID) -> None:
        self.run = run
        self.emit("run_selected")

    def emit(self, event: Event, failure: tuple[str, bool] | None = None) -> None:
        if not self.enabled:
            return
        record: dict[str, object] = {
            "schema_version": "nima-workflow-stage-event-v1",
            "source": "kimdis.contract",
            "stage": self.stage,
            "event": event,
            "request_id": str(self.request),
            "invocation_id": str(self.invocation),
            "run_id": str(self.run) if self.run is not None else None,
            "processed_at": datetime.now(UTC).isoformat(),
        }
        if failure is not None:
            record["reason"], record["retryable"] = failure
        line = json.dumps(record, separators=(",", ":")) + "\n"
        try:
            with _WRITE_LOCK:
                if sys.stderr.write(line) != len(line):
                    raise WorkflowError("diagnostics_unavailable")
                sys.stderr.flush()
        except (OSError, ValueError):
            raise WorkflowError("diagnostics_unavailable") from None


@contextmanager
def workflow_stage(stage: Stage, request: UUID) -> Iterator[StageEvents]:
    mode = os.environ.get("NIMA_WORKFLOW_EVENTS", "off")
    if mode not in {"off", "stderr"}:
        raise WorkflowError("diagnostics_configuration")
    events = StageEvents(stage, request, mode == "stderr")
    events.emit("started")
    try:
        yield events
    except BaseException as error:
        reason = _failure(error)
        event: Event = "interrupted" if reason[0] == "interrupted" else "failed"
        try:
            events.emit(event, reason)
        except WorkflowError:
            # A failed sink must neither erase the primary failure nor go unreported.
            error.add_note("diagnostics_unavailable")
        raise
    else:
        events.emit("succeeded")
