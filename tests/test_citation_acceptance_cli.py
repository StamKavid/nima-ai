"""Fixed DataOps terminal output, including negative policy decisions and interruption."""

import json
from pathlib import Path

import pytest

from nima.dataops import acceptance_cli, cli
from nima.dataops.citation_acceptance import CitationAcceptanceError, CitationAcceptanceExport


@pytest.mark.parametrize(
    "decision,code", [("ready", 0), ("limited", 0), ("blocked", 3), ("not_assessed", 3)]
)
def test_route_and_verdict_exit_codes(
    decision: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "PRIVATE_DSN")

    def export(dsn: str, request: Path, report: Path, output: Path) -> CitationAcceptanceExport:
        assert (dsn, request, report, output) == (
            "PRIVATE_DSN",
            Path("/PRIVATE/request"),
            Path("/PRIVATE/report"),
            Path("/PRIVATE/output"),
        )
        return CitationAcceptanceExport("a" * 64, "b" * 64, decision, "c" * 64)

    monkeypatch.setattr(acceptance_cli, "export_citation_acceptance", export)
    assert (
        cli.run(
            [
                "assess-citations",
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
    assert json.loads(out.out)["decision"] == decision
    assert "PRIVATE" not in out.out + out.err
    assert [json.loads(s)["event"] for s in out.err.splitlines()] == ["started", "completed"]


@pytest.mark.parametrize(
    "reason,code",
    [
        ("acceptance_input", 2),
        ("acceptance_limit", 1),
        ("acceptance_database", 1),
        ("acceptance_evidence", 1),
        ("acceptance_contract", 1),
        ("acceptance_output", 1),
        ("interrupt", 130),
        ("PRIVATE_UNEXPECTED_VALUE", 1),
    ],
)
def test_failure_events_are_closed(
    reason: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object) -> CitationAcceptanceExport:
        if reason == "interrupt":
            raise KeyboardInterrupt
        raise CitationAcceptanceError(reason)

    monkeypatch.setattr(acceptance_cli, "export_citation_acceptance", fail)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert (
        cli.run(
            [
                "assess-citations",
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
    assert "PRIVATE" not in out.out + out.err
    assert json.loads(out.out)["status"] == "failed"


@pytest.mark.parametrize(
    "args", [[], ["wrong"], ["assess-citations"], ["assess-citations", "--PRIVATE_TOKEN"]]
)
def test_parser_errors_are_private(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert acceptance_cli.run(args) == 2
    out = capsys.readouterr()
    assert json.loads(out.out) == {"status": "failed", "failure": "acceptance_input"}
    assert "PRIVATE_TOKEN" not in out.out + out.err


def test_help_needs_no_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    assert acceptance_cli.run(["assess-citations", "--help"]) == 0
    assert "--report" in capsys.readouterr().out
    assert cli.run(["--help"]) == 0
    assert "assess-citations" in capsys.readouterr().out
