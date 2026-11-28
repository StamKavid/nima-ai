"""View CLI exports draft evidence with explicit states and private-safe failures."""

import json
from pathlib import Path
from typing import Any

import pytest

from nima.__main__ import main
from nima.views import cli as commands
from nima.views.buyer_evidence import BuyerViewExport
from nima.views.request import ViewError

ARGS = ["buyer-evidence-view", "--config", "/private/view.json", "--output-dir", "/private/views"]


def test_cli_delegates_once_and_reports_entry_states(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = []

    def export(*args: object) -> BuyerViewExport:
        calls.append(args)
        return BuyerViewExport("a" * 64, ("review_required", "insufficient_evidence"))

    monkeypatch.setattr(commands, "export_buyer_evidence_view", export)
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-dsn")
    assert main(["analytics", *ARGS]) == 0
    assert calls == [("private-dsn", Path("/private/view.json"), Path("/private/views"))]
    assert json.loads(capsys.readouterr().out) == {
        "status": "complete",
        "artifact_sha256": "a" * 64,
        "entry_states": ["review_required", "insufficient_evidence"],
    }


@pytest.mark.parametrize(
    "reason,code",
    [
        ("input", 2),
        ("limit", 1),
        ("database", 1),
        ("contract", 1),
        ("evidence", 1),
        ("output", 1),
        ("interrupted", 130),
    ],
)
def test_closed_failures_and_interruptions(
    reason: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object) -> Any:
        if reason == "interrupted":
            raise KeyboardInterrupt
        raise ViewError("view_" + reason)

    monkeypatch.setattr(commands, "export_buyer_evidence_view", fail)
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-dsn")
    assert main(["analytics", *ARGS]) == code
    captured = capsys.readouterr()
    assert json.loads(captured.out)["failure"] == "view_" + reason
    assert "private" not in captured.out + captured.err


def test_help_needs_no_database_and_unknown_flags_do_not_echo_private_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert main(["analytics", "buyer-evidence-view", "--help"]) == 0
    assert "--config" in capsys.readouterr().out
    assert main(["analytics", *ARGS, "--certify", "PRIVATE-VALUE"]) == 2
    output = capsys.readouterr()
    assert "PRIVATE-VALUE" not in output.out + output.err


def test_unexpected_non_help_parser_exit_is_an_input_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed(*args: Any, **kwargs: Any) -> Any:
        raise SystemExit(2)

    monkeypatch.setattr(commands._Parser, "parse_args", failed)
    assert commands.run([]) == 2


def test_missing_reader_configuration_fails_before_private_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object) -> Any:
        pytest.fail("Missing reader configuration reached private input")

    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    monkeypatch.setattr(commands, "export_buyer_evidence_view", forbidden)
    assert main(["analytics", *ARGS]) == 2
