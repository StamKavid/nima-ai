"""Offline command paths, redaction and no-network boundaries."""

import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Never
from uuid import uuid4

import psycopg
import pytest

from nima.__main__ import main
from tests.test_publicity_evidence_intake import inputs


def arguments(tmp_path: Path) -> tuple[list[str], str, Path]:
    metadata, source, archive = inputs(tmp_path)
    request_id = str(uuid4())
    return (
        [
            "evidence",
            "intake",
            "publicity",
            "--request-id",
            request_id,
            "--manifest",
            str(metadata),
            "--input-dir",
            str(source),
            "--archive-dir",
            str(archive),
        ],
        request_id,
        archive,
    )


def test_end_to_end_commands_are_offline_and_report_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args, request_id, archive = arguments(tmp_path)

    def forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("Offline evidence must not connect")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["evidence_complete"] is True
    assert result["origin_verified"] is result["identity_verified"] is False
    assert main(["evidence", "verify", request_id, "--archive-dir", str(archive)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["reused"] is True


@pytest.mark.parametrize(
    "args",
    [
        ["evidence", "private-company-name"],
        ["evidence", "verify", "private-company-name", "--archive-dir", "/private/path"],
        ["evidence", "intake", "publicity", "--unexpected", "private-company-name"],
    ],
)
def test_argument_errors_never_echo_user_values(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(args) == 2
    output = capsys.readouterr()
    assert "private-company-name" not in output.out + output.err
    assert "private/path" not in output.out + output.err
    assert json.loads(output.out)["failure"] == "input"


def test_missing_input_and_integrity_failure_use_redacted_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, request_id, archive = arguments(tmp_path)
    assert main(args) == 0
    capsys.readouterr()
    for blob in (archive / "objects").glob("*.body"):
        blob.unlink()
    assert main(["evidence", "verify", request_id, "--archive-dir", str(archive)]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "integrity"
    (tmp_path / "input/input.json").unlink()
    assert main(args) == 2
    output = capsys.readouterr()
    assert str(tmp_path) not in output.out + output.err


def test_help_and_interrupt_are_honest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.evidence import cli

    assert main(["evidence", "--help"]) == 0
    assert "intake" in capsys.readouterr().out
    args, _, _ = arguments(tmp_path)

    def interrupted(*args: object, **kwargs: object) -> Never:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "intake", interrupted)
    assert main(args) == 130
    assert json.loads(capsys.readouterr().out)["failure"] == "interrupted"


def test_module_startup_and_intake_do_not_create_sockets(tmp_path: Path) -> None:
    args, _, _ = arguments(tmp_path)
    script = """
import sys
def guard(event, arguments):
    if event.startswith('socket.'):
        raise AssertionError('unexpected socket operation')
sys.addaudithook(guard)
from nima.__main__ import main
raise SystemExit(main(sys.argv[1:]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "staged"
