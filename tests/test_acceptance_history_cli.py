"""Closed summaries, separate journal configuration and honest process exits."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from nima.contracts.acceptance_history import HistoryError, Intent, Outcome, Record
from nima.dataops import acceptance_history_cli as command
from nima.dataops.cli import run


@pytest.mark.parametrize("decision", ["ready", "limited", "blocked", "not_assessed", "refused"])
def test_record_decision_exit_and_private_events(
    decision: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def record(*args: Any) -> dict[str, object]:
        assert args[:2] == ("SOURCE_PRIVATE", "JOURNAL_PRIVATE")
        return {
            "execution_state": "refused" if decision == "refused" else "assessed",
            "outcome": {"data_fitness": None if decision == "refused" else decision},
            "reused": False,
        }

    monkeypatch.setenv("NIMA_DATABASE_URL", "SOURCE_PRIVATE")
    monkeypatch.setenv("NIMA_ACCEPTANCE_DATABASE_URL", "JOURNAL_PRIVATE")
    monkeypatch.setattr(command, "record_citation_acceptance", record)
    code = run(
        [
            "record-citation-acceptance",
            "--attempt-id",
            str(uuid4()),
            "--request",
            "/PRIVATE/request.json",
            "--report",
            "/PRIVATE/report.json",
        ]
    )
    assert code == (0 if decision in {"ready", "limited"} else 3)
    output = capsys.readouterr()
    assert [json.loads(s)["event"] for s in output.err.splitlines()] == ["started", "completed"]
    assert "PRIVATE" not in output.out + output.err


@pytest.mark.parametrize("state", ["pending", "refused"])
def test_inspection_does_not_approve_fitness_or_require_source(
    state: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    intent, attempt = Intent("a" * 64, "b" * 64), uuid4()
    clock = datetime.now(UTC)
    outcome = (
        None
        if state == "pending"
        else Outcome(intent.digest, "refused", None, None, "acceptance_evidence")
    )
    record = Record(attempt, intent, clock, outcome, None if outcome is None else clock)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    monkeypatch.setattr(command, "show_acceptance", lambda *_: record)
    assert run(["acceptance-show", "--attempt-id", str(attempt)]) == 0
    assert json.loads(capsys.readouterr().out) == record.payload()


@pytest.mark.parametrize(
    "fault,code",
    [
        ("configuration", 2),
        ("busy", 1),
        ("interrupt", 130),
        ("unknown", 1),
        ("limit", 1),
        ("help", 0),
        ("args", 2),
        ("uuid", 2),
        ("uuidcaps", 2),
        ("exit", 2),
    ],
)
def test_fixed_failures_and_limits(
    fault: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: Any) -> Any:
        if fault == "interrupt":
            raise KeyboardInterrupt
        if fault == "unknown":
            raise RuntimeError("PRIVATE DSN")
        if fault == "exit":
            raise SystemExit(2)
        if fault == "limit":
            return {
                "execution_state": "assessed",
                "reused": False,
                "outcome": {"data_fitness": "ready"},
                "detail": "x" * 16384,
            }
        raise HistoryError("acceptance_history_" + fault)

    monkeypatch.setattr(command, "record_citation_acceptance", fail)
    args = [
        "record-citation-acceptance",
        "--attempt-id",
        str(uuid4()),
        "--request",
        "/PRIVATE/request",
        "--report",
        "/PRIVATE/report",
    ]
    if fault == "help":
        args = ["acceptance-show", "--help"]
    elif fault == "args":
        args += ["--unknown", "PRIVATE"]
    elif fault == "uuid":
        args[2] = "{PRIVATE}"
    elif fault == "uuidcaps":
        args[2] = "AAAAAAAA-1111-4111-8111-111111111111"
    assert run(args) == code
    output = capsys.readouterr()
    assert "PRIVATE" not in output.out + output.err


def test_invalid_command_and_dataops_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert command.run(["other"]) == 2
    capsys.readouterr()
    assert run(["--help"]) == 0
    assert "record-citation-acceptance" in capsys.readouterr().out
