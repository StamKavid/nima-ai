"""Actual SQL commands keep source values and selected hashes out of terminal output."""

import json
from pathlib import Path

import pytest

from nima.__main__ import main
from nima.metadata.export import prepare_metadata
from tests.test_metadata_export import kimdis_run
from tests.test_metadata_store import principal


def test_actual_promote_then_readonly_query_matches_existing_artifact(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, out = tmp_path / "archive", tmp_path / "out"
    run = kimdis_run(pg_dsn, root)
    raw, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    with principal(pg_dsn, write=True) as dsn:
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        args = [
            "metadata",
            "promote",
            "kimdis",
            "--run-id",
            str(run),
            "--archive-dir",
            str(root),
            "--snapshot-sha256",
            selected.artifact_sha256,
        ]
        assert main(args) == 0
        assert json.loads(capsys.readouterr().out)["reused"] is False
        assert main(args) == 0
        assert json.loads(capsys.readouterr().out)["reused"] is True
    with principal(pg_dsn) as dsn:
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            main(
                [
                    "metadata",
                    "query",
                    "--snapshot-sha256",
                    selected.artifact_sha256,
                    "--output-dir",
                    str(out),
                ]
            )
            == 0
        )
        terminal = capsys.readouterr().out
        assert (
            selected.artifact_sha256 not in terminal
            and str(run) not in terminal
            and "Άμυνα" not in terminal
        )
        assert (out / (selected.artifact_sha256 + ".json")).read_bytes() == raw


def test_bad_input_and_missing_snapshot_are_fixed_errors(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.storage.postgres import migrate

    migrate(pg_dsn)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    common = ["metadata", "query", "--output-dir", str(tmp_path / "out")]
    assert main([*common, "--snapshot-sha256", "private-value"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "failure": "metadata_input"}
    assert main([*common, "--snapshot-sha256", "0" * 64]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "failed",
        "failure": "metadata_unavailable",
    }
    assert not (tmp_path / "out").exists()


def test_missing_database_does_not_create_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert (
        main(
            [
                "metadata",
                "query",
                "--snapshot-sha256",
                "0" * 64,
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["failure"] == "metadata_input"
    assert not (tmp_path / "out").exists()
