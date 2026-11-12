"""Inspection/planning are SQL-only and never imply a source refresh happened."""

import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from nima.__main__ import main
from nima.storage.postgres import migrate
from tests.test_refresh_store import DAY


def test_create_plan_show_are_redacted_and_offline(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    migrate(pg_dsn)
    policy = uuid4()
    root = tmp_path / "private-evidence"
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    monkeypatch.setenv("NIMA_ARCHIVE_ROOT", str(root))
    monkeypatch.setenv("PREFECT_HOME", str(tmp_path / "control"))
    monkeypatch.setenv("PREFECT_API_URL", "http://127.0.0.1:1/api")
    assert (
        main(
            [
                "refresh",
                "create",
                "kimdis",
                "--policy-id",
                str(policy),
                "--start-date",
                (DAY - timedelta(days=2)).isoformat(),
                "--buyer-id",
                "21",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["state"] == "paused"
    monkeypatch.delenv("PREFECT_API_URL")
    assert main(["refresh", "plan", str(policy), "--as-of", DAY.isoformat()]) == 0
    result = capsys.readouterr().out
    assert len(json.loads(result)["query_dates"]) == 2
    assert main(["refresh", "show", str(policy)]) == 0
    result += capsys.readouterr().out
    assert pg_dsn not in result and str(root) not in result and not root.exists()


def test_invalid_refresh_configuration_is_fixed_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert main(["refresh", "show", str(uuid4())]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
