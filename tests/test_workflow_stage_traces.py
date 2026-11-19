"""Real SQL state, fixture HTTP and stage traces agree without changing budgets."""

import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from nima.orchestration.pipeline import (
    collect_request,
    finalize_request,
    prepare_request,
    project_request,
)
from nima.storage.postgres import migrate
from nima.storage.workflows import RequestStore, WorkflowError
from tests.test_collection import QUERY, Clock, body
from tests.test_workflow_events import FailingSink, records


def test_four_stage_trace_preserves_state_and_repeat_results(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    request = uuid4()
    store = RequestStore(pg_dsn)
    store.submit(request, QUERY, tmp_path / "private-archive")
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    prepared = prepare_request(pg_dsn, request)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=body(total=1, title="private-source-marker"),
            )
        )
    ) as client:
        collected = collect_request(pg_dsn, request, client=client, clock=Clock())
        assert collected["records"] == 1
        assert project_request(pg_dsn, request)["remaining_events"] == 0
        final = finalize_request(pg_dsn, request)
        assert final["status"] == "complete"
        enabled = capsys.readouterr()
        rows = records(enabled.err)
        assert enabled.out == ""
        assert len(rows) == 12
        assert [row["stage"] for row in rows] == [
            stage for stage in ("prepare", "collect", "project", "finalize") for _ in range(3)
        ]
        for start in range(0, 12, 3):
            assert [row["event"] for row in rows[start : start + 3]] == [
                "started",
                "run_selected",
                "succeeded",
            ]
            assert rows[start + 2]["run_id"] == prepared["run_id"]
        assert len({row["invocation_id"] for row in rows}) == 4
        assert all(row["request_id"] == str(request) for row in rows)
        assert "private-source-marker" not in enabled.err
        assert str(tmp_path) not in enabled.err and pg_dsn not in enabled.err
        monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "off")
        assert prepare_request(pg_dsn, request) == prepared
        assert collect_request(pg_dsn, request, client=client, clock=Clock()) == collected
        assert project_request(pg_dsn, request)["remaining_events"] == 0
        assert finalize_request(pg_dsn, request) == final
        assert capsys.readouterr() == ("", "")
    assert store.show(request)["attempts"] == 1


def test_failed_collection_is_traced_then_same_request_can_resume(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    request, store = uuid4(), RequestStore(pg_dsn)
    store.submit(request, QUERY, tmp_path / "raw")
    run = prepare_request(pg_dsn, request)["run_id"]
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    403,
                    content=b"private source denial",
                )
            )
        ) as client,
        pytest.raises(WorkflowError, match="^http_403$"),
    ):
        collect_request(pg_dsn, request, client=client, clock=Clock())
    failed = records(capsys.readouterr().err)
    assert [row["event"] for row in failed] == ["started", "run_selected", "failed"]
    assert failed[-1]["reason"] == "http_403" and failed[-1]["retryable"] is False
    assert store.show(request)["status"] == "partial"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=body(total=0),
            )
        )
    ) as client:
        assert collect_request(pg_dsn, request, client=client, clock=Clock())["records"] == 0
    resumed = records(capsys.readouterr().err)
    assert resumed[-1]["event"] == "succeeded"
    assert resumed[-1]["run_id"] == failed[-1]["run_id"] == run
    assert resumed[-1]["invocation_id"] != failed[-1]["invocation_id"]
    assert store.show(request)["attempts"] == 2
    assert store.show(request)["executions"] == 2


def test_terminal_sink_failure_can_follow_durable_prepare(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrate(pg_dsn)
    request, store = uuid4(), RequestStore(pg_dsn)
    store.submit(request, QUERY, tmp_path / "raw")
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    sink = FailingSink(after=2)
    with monkeypatch.context() as context:
        context.setattr(sys, "stderr", sink)
        with pytest.raises(WorkflowError, match="^diagnostics_unavailable$"):
            prepare_request(pg_dsn, request)
    run = store.show(request)["run_id"]
    UUID(str(run))
    assert store.show(request)["attempts"] == 0
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "off")
    assert prepare_request(pg_dsn, request)["run_id"] == run
    assert json.loads(sink.getvalue().splitlines()[-1])["run_id"] == run


@pytest.mark.parametrize("stage", ["prepare", "collect", "project", "finalize"])
def test_unavailable_request_traces_fixed_failure_before_run_selection(
    stage: str,
    pg_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    monkeypatch.setenv("NIMA_WORKFLOW_EVENTS", "stderr")
    request = uuid4()
    with pytest.raises(WorkflowError, match="^request_unavailable$"):
        if stage == "collect":
            with httpx.Client(
                transport=httpx.MockTransport(
                    lambda _: pytest.fail("No source call without a request"),
                )
            ) as client:
                collect_request(pg_dsn, request, client=client, clock=Clock())
        else:
            {"prepare": prepare_request, "project": project_request, "finalize": finalize_request}[
                stage
            ](pg_dsn, request)
    rows = records(capsys.readouterr().err)
    assert [row["event"] for row in rows] == ["started", "failed"]
    assert rows[-1]["reason"] == "request_unavailable" and rows[-1]["run_id"] is None
