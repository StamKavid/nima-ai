"""The database interface never emits driver messages or opens HTTP for inspection."""

import json
from pathlib import Path

import httpx
import psycopg
import pytest

from nima.__main__ import main
from nima.ingestion.collector import RunError
from tests.test_cli import arguments
from tests.test_collection import body


def test_migrate_collect_and_inspect(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    assert main(["db", "migrate"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "migrated"
    real_client = httpx.Client
    monkeypatch.setattr(
        "nima.__main__.httpx.Client",
        lambda: real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body(total=1)))
        ),
    )
    assert main([*arguments(tmp_path), "--database"]) == 0
    summary = json.loads(capsys.readouterr().out)

    def no_http() -> None:
        pytest.fail("Run inspection opened an HTTP client")

    monkeypatch.setattr("nima.__main__.httpx.Client", no_http)
    assert main(["runs", "show", summary["run_id"]]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["collection_complete"] is True and state["next_page"] == 1
    assert "archive_root" not in state and "password" not in str(state)


def test_database_configuration_is_required_before_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert main([*arguments(tmp_path), "--database"]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
    assert not (tmp_path / "raw").exists()


def test_driver_messages_are_redacted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private configuration")

    def fail(_: str) -> None:
        raise psycopg.OperationalError("private connection and password text")

    monkeypatch.setattr("nima.__main__.migrate", fail)
    assert main(["db", "migrate"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["failure"] == "database"
    assert "private" not in output.out + output.err


def test_missing_schema_and_unknown_run_have_explicit_failures(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    run_id = "00000000000000000000000000000001"
    assert main(["runs", "show", run_id]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "database_schema"
    assert main(["db", "migrate"]) == 0
    capsys.readouterr()
    assert main(["runs", "show", run_id]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "run_unavailable"


def test_failed_collection_keeps_an_inspectable_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RunError("1234", "database")

    monkeypatch.setattr("nima.__main__.collect", fail)
    assert main(arguments(tmp_path)) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["run_id"] == "1234" and output["failure"] == "database"


def test_resume_command_reconciles_a_completed_run(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    assert main(["db", "migrate"]) == 0
    capsys.readouterr()
    real_client = httpx.Client
    monkeypatch.setattr(
        "nima.__main__.httpx.Client",
        lambda: real_client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body(total=1)))
        ),
    )
    assert main([*arguments(tmp_path), "--database"]) == 0
    run_id = json.loads(capsys.readouterr().out)["run_id"]

    def no_source(_: httpx.Request) -> httpx.Response:
        pytest.fail("Completed run was refreshed during resume")

    monkeypatch.setattr(
        "nima.__main__.httpx.Client", lambda: real_client(transport=httpx.MockTransport(no_source))
    )
    assert main(["runs", "resume", run_id]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["collection_complete"] is True and state["records"] == 1
