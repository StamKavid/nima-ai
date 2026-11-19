"""Bounded operator diagnostics never replace durable workflow evidence."""

import io
import json
import sys
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.orchestration.events import workflow_stage
from nima.storage.workflows import WorkflowError


def records(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    assert all(len(line.encode()) < 1024 for line in lines)
    return [json.loads(line) for line in lines]


def test_default_off_never_uses_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NIMA_WORKFLOW_EVENTS", raising=False)
    sink = io.StringIO()
    sink.close()
    monkeypatch.setattr(sys, "stderr", sink)
    with workflow_stage("prepare", uuid4()) as events:
        events.bind_run(uuid4())


@pytest.mark.parametrize("mode", ["", "STDERR", "stderr\nsecret", "credential_like_value"])
def test_invalid_mode_refuses_before_work(mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", mode)
    with (
        pytest.raises(WorkflowError, match="^diagnostics_configuration$"),
        workflow_stage("prepare", uuid4()),
    ):
        pytest.fail("Invalid diagnostics must fail before stage work")


def test_events_are_correlated_but_retries_have_new_invocations(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    request, run = uuid4(), uuid4()
    for _ in range(2):
        with workflow_stage("collect", request) as events:
            events.bind_run(run)
    output = capsys.readouterr()
    assert output.out == ""
    rows = records(output.err)
    assert [row["event"] for row in rows] == ["started", "run_selected", "succeeded"] * 2
    for offset in (0, 3):
        group = rows[offset : offset + 3]
        assert len({row["invocation_id"] for row in group}) == 1
        UUID(str(group[0]["invocation_id"]))
        for row in group:
            assert set(row) == {
                "schema_version",
                "source",
                "stage",
                "event",
                "request_id",
                "invocation_id",
                "run_id",
                "processed_at",
            }
            assert row["schema_version"] == "nima-workflow-stage-event-v1"
            assert row["source"] == "kimdis.contract"
            assert row["stage"] == "collect" and row["request_id"] == str(request)
            assert datetime.fromisoformat(str(row["processed_at"])).utcoffset() == timedelta(0)
        assert [row["run_id"] for row in group] == [None, str(run), str(run)]
    assert rows[0]["invocation_id"] != rows[3]["invocation_id"]


@pytest.mark.parametrize(
    ("failure", "reason", "retryable", "event"),
    [
        (WorkflowError("workflow_attempt_limit"), "workflow_attempt_limit", False, "failed"),
        (WorkflowError("database", True), "database", True, "failed"),
        (WorkflowError("http_403"), "http_403", False, "failed"),
        (WorkflowError("credential_like_value", True), "unrecognized_failure", False, "failed"),
        (WorkflowError("http_403_secret"), "unrecognized_failure", False, "failed"),
        (ValueError("private SQL and company"), "unexpected_error", False, "failed"),
        (psycopg.OperationalError("private DSN"), "database", True, "failed"),
        (OSError("private path"), "archive_invalid", False, "failed"),
        (KeyboardInterrupt("private text"), "interrupted", False, "interrupted"),
        (SystemExit("private text"), "interrupted", False, "interrupted"),
    ],
)
def test_failures_have_allowlisted_codes_and_preserve_original_exception(
    failure: BaseException,
    reason: str,
    retryable: bool,
    event: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    with pytest.raises(type(failure)) as caught, workflow_stage("project", uuid4()):
        raise failure
    assert caught.value is failure
    rows = records(capsys.readouterr().err)
    assert [row["event"] for row in rows] == ["started", event]
    assert rows[-1]["reason"] == reason and rows[-1]["retryable"] is retryable
    assert set(rows[-1]) == set(rows[0]) | {"reason", "retryable"}
    assert not any(word in json.dumps(rows) for word in ("secret", "private", "credential"))


class FailingSink(io.StringIO):
    def __init__(self, after: int = 0, *, on_flush: bool = False, short: bool = False):
        super().__init__()
        self.after, self.on_flush, self.short = after, on_flush, short
        self.writes = 0

    def write(self, text: str) -> int:
        self.writes += 1
        if self.writes > self.after and not self.on_flush:
            if self.short:
                return 0
            raise OSError("private sink path")
        return super().write(text)

    def flush(self) -> None:
        if self.on_flush and self.writes > self.after:
            raise OSError("private flush path")


@pytest.mark.parametrize("on_flush,short", [(False, False), (True, False), (False, True)])
def test_required_opening_event_failure_prevents_work(
    on_flush: bool,
    short: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    monkeypatch.setattr(sys, "stderr", FailingSink(on_flush=on_flush, short=short))
    with (
        pytest.raises(WorkflowError, match="^diagnostics_unavailable$"),
        workflow_stage("prepare", uuid4()),
    ):
        pytest.fail("Stage work must not start without the required opening event")


def test_failure_event_sink_error_keeps_primary_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    monkeypatch.setattr(sys, "stderr", FailingSink(after=1))
    failure = WorkflowError("source_busy", True)
    with pytest.raises(WorkflowError) as caught, workflow_stage("collect", uuid4()):
        raise failure
    assert caught.value is failure and failure.retryable
    assert failure.__notes__ == ["diagnostics_unavailable"]


def test_closed_sink_fails_with_fixed_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    sink = io.StringIO()
    sink.close()
    monkeypatch.setattr(sys, "stderr", sink)
    with (
        pytest.raises(WorkflowError, match="^diagnostics_unavailable$"),
        workflow_stage("finalize", uuid4()),
    ):
        pytest.fail("Closed stderr cannot acknowledge diagnostics")
