"""Insight CLI preserves business refusals and private-safe operational exit codes."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from nima.__main__ import main
from nima.insights import cli
from nima.insights.buyer_participation import InsightError, InsightExport, Status

ARGS = [
    "buyer-participation",
    "--request",
    "/private/request.json",
    "--report",
    "/private/report.json",
    "--output-dir",
    "/private/insights",
]


@pytest.mark.parametrize(
    "status,code", [("answered", 0), ("review_required", 3), ("insufficient_evidence", 3)]
)
def test_delegates_once_and_prints_actual_insight_status(
    status: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = []

    def export(*args: object) -> InsightExport:
        calls.append(args)
        return InsightExport("a" * 64, cast(Status, status), "b" * 64)

    monkeypatch.setattr(cli, "export_buyer_insight", export)
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-dsn")
    assert main(["insights", *ARGS]) == code
    assert calls == [
        (
            "private-dsn",
            Path("/private/request.json"),
            Path("/private/report.json"),
            Path("/private/insights"),
        )
    ]
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "artifact_sha256": "a" * 64,
        "subject_sha256": "b" * 64,
        "status": status,
    }
    events = [json.loads(line) for line in captured.err.splitlines()]
    assert [e["event"] for e in events] == ["started", "completed"]
    assert "private-dsn" not in captured.out + captured.err


@pytest.mark.parametrize(
    "reason,code",
    [
        ("input", 2),
        ("limit", 1),
        ("database", 1),
        ("evidence", 1),
        ("contract", 1),
        ("output", 1),
        ("interrupted", 130),
    ],
)
def test_fixed_failures_and_interruptions_have_no_private_details(
    reason: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object) -> Any:
        if reason == "interrupted":
            raise KeyboardInterrupt
        raise InsightError("insight_" + reason)

    monkeypatch.setattr(cli, "export_buyer_insight", fail)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert cli.run(ARGS) == code
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "failure": "insight_" + reason}
    assert "/private" not in captured.out + captured.err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["other"],
        ["buyer-participation"],
        ARGS + ["--allow-draft"],
        ARGS + ["--force"],
        ["buyer-participation", "--req", "PRIVATE"],
    ],
)
def test_parser_errors_are_sanitized(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run(argv) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "failure": "insight_input"}
    assert "PRIVATE" not in captured.out + captured.err


@pytest.mark.parametrize("argv", [["--help"], ["buyer-participation", "--help"]])
def test_help_needs_no_reader_or_source(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object) -> Any:
        pytest.fail("help verified data")

    monkeypatch.setattr(cli, "export_buyer_insight", forbidden)
    assert main(["insights", *argv]) == 0
    assert "buyer-participation" in capsys.readouterr().out


def test_non_help_parser_exit_is_an_input_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def exit_error(*args: Any, **kwargs: Any) -> Any:
        raise SystemExit(2)

    monkeypatch.setattr(cli._Parser, "parse_args", exit_error)
    assert cli.run(ARGS) == 2
