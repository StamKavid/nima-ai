"""Private analytics parsing, real limited SQL reads and installed-module execution."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Never

import psycopg
import pytest

from nima.__main__ import main
from nima.analytics import commands
from nima.analytics.result import ReadoutError
from tests.test_analytics_reconcile import captured, seed_cohort
from tests.test_analytics_snapshot import reader, state
from tests.test_market_analytics import request_file
from tests.test_semantics import TAX


def arguments(request: Path, output: Path) -> list[str]:
    return ["analytics", "supplier-buyers", "--request", str(request), "--output-dir", str(output)]


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ([], "analytics"),
        (["analytics"], "supplier-buyers"),
        (["analytics", "supplier-buyers"], "--request"),
    ],
)
def test_help_exposes_only_the_offline_readout(
    route: list[str], expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main([*route, "--help"])
    assert stopped.value.code == 0
    output = capsys.readouterr()
    assert not output.err
    assert expected in output.out
    if len(route) == 2:
        assert "--output-dir" in output.out
        assert "--database-url" not in output.out and "--api-key" not in output.out


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        ["private-sentinel"],
        ["supplier-buyers"],
        ["--private-sentinel", "supplier-buyers"],
        ["supplier-buyers", "--request", "private-sentinel"],
        ["supplier-buyers", "--req", "private-sentinel", "--output-dir", "private-sentinel"],
        [
            "supplier-buyers",
            "--request",
            "private-sentinel",
            "--output-dir",
            "private-sentinel",
            "private-sentinel",
        ],
        [
            "supplier-buyers",
            "--request",
            "private-sentinel",
            "--output-dir",
            "private-sentinel",
            "--database-url",
            "private-sentinel",
        ],
        ["supplier-buyers", "--request", "--output-dir", "private-sentinel"],
    ],
)
def test_parser_errors_are_fixed_before_private_io(
    tokens: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Bad parsing must precede private file or database access")

    monkeypatch.setattr(commands, "export_readout", forbidden)
    assert main(["analytics", *tokens]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": "analytics_configuration"}
    assert not output.err and "private-sentinel" not in output.out


@pytest.mark.parametrize("configured", [None, "  \t"])
def test_missing_environment_fails_before_private_io(
    configured: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if configured is None:
        monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("NIMA_DATABASE_URL", configured)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Missing configuration must precede input access")

    monkeypatch.setattr(commands, "export_readout", forbidden)
    assert main(arguments(tmp_path / "private-sentinel", tmp_path / "out")) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": "analytics_configuration"}
    assert not output.err and not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "reason",
    [
        "analytics_input",
        "analytics_input_file",
        "analytics_archive",
        "analytics_evidence",
        "analytics_projection",
        "analytics_coverage",
        "analytics_version",
        "analytics_role",
        "analytics_schema",
        "analytics_database",
        "analytics_metric",
        "analytics_limit",
        "analytics_output",
    ],
)
def test_readout_failure_codes_remain_fixed(
    reason: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def fail(*args: object, **kwargs: object) -> Never:
        raise ReadoutError(reason)

    monkeypatch.setattr(commands, "export_readout", fail)
    assert main(arguments(tmp_path / "private-sentinel", tmp_path / "out")) == (
        2 if reason == "analytics_input" else 1
    )
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": reason}
    assert not output.err and "private-sentinel" not in output.out


@pytest.mark.parametrize(
    ("error", "code", "reason"),
    [
        (psycopg.OperationalError("private-sentinel"), 1, "analytics_database"),
        (OSError("private-sentinel"), 1, "analytics_output"),
        (ValueError("private-sentinel"), 2, "analytics_configuration"),
        (KeyboardInterrupt("private-sentinel"), 130, "analytics_interrupted"),
    ],
)
def test_boundary_exceptions_never_echo_driver_or_private_values(
    error: BaseException,
    code: int,
    reason: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def fail(*args: object, **kwargs: object) -> Never:
        raise error

    monkeypatch.setattr(commands, "export_readout", fail)
    assert main(arguments(tmp_path / "private-sentinel", tmp_path / "out")) == code
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": reason}
    assert not output.err and "private-sentinel" not in output.out


@pytest.mark.parametrize("fault", ["missing", "public", "symlink", "malformed"])
def test_actual_private_input_failures_precede_database_access(
    fault: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "private-sentinel.json"
    path.write_bytes(b'{"private-sentinel":true}')
    path.chmod(0o600)
    if fault == "missing":
        path.unlink()
    elif fault == "public":
        path.chmod(0o644)
    elif fault == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Bad private input must precede SQL access")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    assert main(arguments(path, tmp_path / "out")) == (2 if fault == "malformed" else 1)
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "failed",
        "failure": "analytics_input" if fault == "malformed" else "analytics_input_file",
    }
    assert not output.err and "private-sentinel" not in output.out
    assert not (tmp_path / "out").exists()


def test_actual_cli_keeps_data_private_and_preserves_sql_and_artifacts(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "originals")
    path = request_file(request, tmp_path / "request.json")
    output = tmp_path / "reports"
    before = state(pg_dsn)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Offline readout must not create an HTTP client")

    monkeypatch.setattr("httpx.Client", forbidden)
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(arguments(path, output)) == 0
        terminal = capsys.readouterr()
        summary = json.loads(terminal.out)
        assert set(summary) == {
            "status",
            "artifact_sha256",
            "record_count",
            "buyer_count",
            "outcome",
        }
        assert summary["record_count"] == 5 and summary["buyer_count"] == 2
        assert summary["status"] == "complete" and summary["outcome"] == "observed_participation"
        assert not terminal.err
        for private in (TAX, dsn, str(path), str(output), "Συνθετική"):
            assert private not in terminal.out
        final = output / (summary["artifact_sha256"] + ".json")
        previous = final.read_bytes(), final.stat().st_mtime_ns
        assert hashlib.sha256(previous[0]).hexdigest() == summary["artifact_sha256"]
        assert main(arguments(path, output)) == 0
        assert json.loads(capsys.readouterr().out) == summary
        assert previous == (final.read_bytes(), final.stat().st_mtime_ns)
    assert state(pg_dsn) == before


def test_installed_module_uses_environment_only_configuration(pg_dsn: str, tmp_path: Path) -> None:
    request, _ = captured(pg_dsn, tmp_path / "originals")
    path = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        result = subprocess.run(
            [sys.executable, "-m", "nima", *arguments(path, tmp_path / "out")],
            env={**os.environ, "NIMA_DATABASE_URL": dsn},
            capture_output=True,
            text=True,
            timeout=30,
        )
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout)["record_count"] == 1
    assert (
        TAX not in result.stdout and dsn not in result.stdout and str(tmp_path) not in result.stdout
    )
