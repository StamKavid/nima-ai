"""Offline CLI never requires GEMI credentials and returns redacted failures."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from nima.__main__ import main
from nima.storage.postgres import migrate
from tests.test_gemi_import_archive import archive_run, edit


def test_import_cli_succeeds_without_key_or_http(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    monkeypatch.delenv("NIMA_GEMI_API_KEY", raising=False)
    monkeypatch.setattr("httpx.Client", lambda **_: pytest.fail("Unexpected HTTP"))
    for reused in (False, True):
        assert main(["gemi", "import", str(run), "--archive-dir", str(root)]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["reused"] is reused and result["profiles"] == result["not_found"] == 1
        assert result["import_version"] == "gemi-import-v1"
        assert "001234567" not in str(result) and "Άλφα" not in str(result)
    edit(root, run, "summary.failure", "private-person-and-secret")
    assert main(["gemi", "import", str(run), "--archive-dir", str(root)]) == 1
    failure = capsys.readouterr().out
    assert "run_incomplete" in failure and "private-person-and-secret" not in failure


def test_missing_database_configuration_fails_without_creating_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    root = tmp_path / "absent"
    assert main(["gemi", "import", str(UUID(int=1)), "--archive-dir", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
    assert not root.exists()


def test_import_interruption_is_reported_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "synthetic-placeholder")

    def interrupt(*_: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("nima.__main__.import_gemi", interrupt)
    assert main(["gemi", "import", str(UUID(int=1)), "--archive-dir", str(tmp_path)]) == 130
    assert json.loads(capsys.readouterr().out)["failure"] == "interrupted"
