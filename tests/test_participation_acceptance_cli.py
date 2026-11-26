"""U1 uses the same fixed acceptance terminal contract, including negative fitness."""

import json
from pathlib import Path

import pytest

from nima.dataops import acceptance_cli, cli
from nima.dataops.participation_acceptance import (
    ParticipationAcceptanceError,
    ParticipationAcceptanceExport,
)


@pytest.mark.parametrize(
    "decision,exit_code", [("ready", 0), ("limited", 0), ("blocked", 3), ("not_assessed", 3)]
)
def test_cli_route_private_arguments_and_policy_decisions(
    decision: str,
    exit_code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "PRIVATE_DSN")

    def exported(
        dsn: str, request: Path, report: Path, output: Path
    ) -> ParticipationAcceptanceExport:
        assert (dsn, request, report, output) == (
            "PRIVATE_DSN",
            Path("/PRIVATE/request"),
            Path("/PRIVATE/report"),
            Path("/PRIVATE/output"),
        )
        return ParticipationAcceptanceExport("a" * 64, "b" * 64, decision, "c" * 64)

    monkeypatch.setattr(acceptance_cli, "export_participation_acceptance", exported)
    assert (
        cli.run(
            [
                "assess-participation",
                "--request",
                "/PRIVATE/request",
                "--report",
                "/PRIVATE/report",
                "--output-dir",
                "/PRIVATE/output",
            ]
        )
        == exit_code
    )
    out = capsys.readouterr()
    assert json.loads(out.out)["decision"] == decision
    assert "PRIVATE" not in out.out + out.err
    assert [json.loads(s)["event"] for s in out.err.splitlines()] == ["started", "completed"]


@pytest.mark.parametrize(
    "reason,code",
    [
        ("acceptance_input", 2),
        ("acceptance_evidence", 1),
        ("acceptance_database", 1),
        ("acceptance_contract", 1),
        ("acceptance_limit", 1),
        ("acceptance_output", 1),
        ("interrupt", 130),
    ],
)
def test_u1_terminal_failure_is_closed(
    reason: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object) -> ParticipationAcceptanceExport:
        if reason == "interrupt":
            raise KeyboardInterrupt
        raise ParticipationAcceptanceError(reason)

    monkeypatch.setattr(acceptance_cli, "export_participation_acceptance", fail)
    assert (
        cli.run(
            [
                "assess-participation",
                "--request",
                "/PRIVATE/request",
                "--report",
                "/PRIVATE/report",
                "--output-dir",
                "/PRIVATE/output",
            ]
        )
        == code
    )
    out = capsys.readouterr()
    assert json.loads(out.out)["status"] == "failed"
    assert "PRIVATE" not in out.out + out.err


def test_help_lists_both_consumers(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run(["--help"]) == 0
    assert "assess-participation" in capsys.readouterr().out
    assert acceptance_cli.run(["assess-participation", "--help"]) == 0
    assert "--report" in capsys.readouterr().out
