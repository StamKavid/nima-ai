"""Workflow CLI validates configuration and supports SQL-only status inspection."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from nima.__main__ import main
from nima.storage.postgres import migrate
from nima.storage.workflows import RequestStore
from tests.test_collection import QUERY


def test_workflow_status_needs_no_engine_or_key(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    migrate(pg_dsn)
    request = uuid4()
    RequestStore(pg_dsn).submit(request, QUERY, tmp_path / "raw")
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    monkeypatch.delenv("PREFECT_API_URL", raising=False)
    assert main(["workflows", "show", str(request)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "queued" and value["collection_complete"] is False
    assert pg_dsn not in str(value) and str(tmp_path) not in str(value)


def test_missing_local_engine_configuration_is_redacted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PREFECT_API_URL", raising=False)
    assert main(["workflows", "dispatch", str(uuid4())]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
