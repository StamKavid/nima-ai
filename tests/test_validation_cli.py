"""Actual explicit verifier/inspection routes expose fixed private-safe results."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from nima.__main__ import main
from nima.analytics.export import export_readout
from tests.test_analytics_reconcile import seed_cohort
from tests.test_analytics_snapshot import reader
from tests.test_market_analytics import request_file
from tests.test_validation_store import journal_role


def test_actual_routes_record_and_inspect_without_source_http(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "raw")
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (source, _), journal_role(pg_dsn) as journal:
        summary = export_readout(source, selection, tmp_path / "reports")
        report = tmp_path / "reports" / (summary.artifact_sha256 + ".json")
        monkeypatch.setenv("NIMA_DATABASE_URL", source)
        monkeypatch.setenv("NIMA_VALIDATION_DATABASE_URL", journal)

        def forbidden(*args: object, **kwargs: object) -> None:
            pytest.fail("No source HTTP belongs in post-publication verification")

        monkeypatch.setattr(httpx.Client, "request", forbidden)
        attempt = str(uuid4())
        args = [
            "dataops",
            "validate-readout",
            "--attempt-id",
            attempt,
            "--request",
            str(selection),
            "--report",
            str(report),
        ]
        assert main(args) == 0
        terminal = capsys.readouterr()
        value = json.loads(terminal.out)
        assert value["status"] == "passed" and value["reused"] is False
        assert [json.loads(line)["event"] for line in terminal.err.splitlines()] == [
            "started",
            "completed",
        ]
        assert str(tmp_path) not in terminal.out + terminal.err
        assert (
            source not in terminal.out + terminal.err and journal not in terminal.out + terminal.err
        )
        report.unlink()
        monkeypatch.delenv("NIMA_DATABASE_URL")
        assert main(["dataops", "validation-show", "--attempt-id", attempt]) == 0
        assert json.loads(capsys.readouterr().out)["outcome_sha256"] == value["outcome_sha256"]


@pytest.mark.parametrize(
    "args",
    [
        ["validation-show"],
        ["validation-show", "--attempt-id", "private-sentinel"],
        ["validate-readout", "--attempt-id", str(uuid4())],
        ["validation-show", "--attempt-id", str(uuid4()), "--unknown", "private-sentinel"],
    ],
)
def test_cli_configuration_does_not_echo_values(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["dataops", *args]) == 2
    terminal = capsys.readouterr()
    assert json.loads(terminal.out) == {"status": "failed", "failure": "validation_configuration"}
    assert "private-sentinel" not in terminal.out + terminal.err
