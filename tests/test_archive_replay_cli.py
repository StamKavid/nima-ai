"""Replay is available through the installed offline CLI with private-safe summaries."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Never
from uuid import UUID

import pytest

from nima.__main__ import main
from nima.dataops import replay
from nima.storage.postgres import NORMALIZER_VERSION
from tests.test_analytics_snapshot import reader, seed


def arguments(run: UUID, root: Path, output: Path) -> list[str]:
    return [
        "archive",
        "replay",
        "--run-id",
        str(run),
        "--archive-dir",
        str(root),
        "--output-dir",
        str(output),
        "--normalizer-version",
        NORMALIZER_VERSION,
    ]


def test_installed_replay_cli_uses_real_reader_and_publishes_private_dataset(
    pg_dsn: str, tmp_path: Path
) -> None:
    root, output = tmp_path / "raw", tmp_path / "result"
    run = seed(pg_dsn, root, project=False)
    with reader(pg_dsn) as (dsn, _):
        result = subprocess.run(
            [sys.executable, "-m", "nima", *arguments(run, root, output)],
            env={**os.environ, "NIMA_DATABASE_URL": dsn},
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout) == {
        "status": "complete",
        "outcome": "replayed_committed_pages",
        "page_count": 1,
        "record_count": 1,
        "normalized_count": 1,
        "quarantined_count": 0,
    }
    assert str(root) not in result.stdout and str(run) not in result.stdout
    assert len(list(output.glob("*.json"))) == 1


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        ["--run-id", str(UUID(int=1))],
        [
            "--run-id",
            "private-sentinel",
            "--archive-dir",
            "/private-sentinel",
            "--output-dir",
            "/private-sentinel",
            "--normalizer-version",
            NORMALIZER_VERSION,
        ],
        [
            "--run-id",
            str(UUID(int=1)),
            "--archive-dir",
            "/private-sentinel",
            "--output-dir",
            "/private-sentinel",
        ],
        [
            "--run-id",
            str(UUID(int=1)),
            "--archive-dir",
            "/private-sentinel",
            "--output-dir",
            "/private-sentinel",
            "--normalizer-version",
            NORMALIZER_VERSION,
            "--api-key",
            "private-sentinel",
        ],
    ],
)
def test_bad_replay_cli_never_opens_private_io(
    tokens: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid arguments must precede SQL/files")

    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    monkeypatch.setattr(replay, "replay_run", forbidden)
    assert main(["archive", "replay", *tokens]) == 2
    text = capsys.readouterr()
    assert json.loads(text.out) == {"status": "failed", "failure": "archive_configuration"}
    assert "private-sentinel" not in text.out and not text.err


@pytest.mark.parametrize(
    ("error", "code", "reason"),
    [
        (replay.ReplayError("replay_version"), 2, "replay_version"),
        (replay.ReplayError("replay_input"), 2, "replay_input"),
        (replay.ReplayError("replay_empty"), 3, "replay_empty"),
        (replay.ReplayError("replay_database"), 1, "replay_database"),
        (KeyboardInterrupt(), 130, "archive_interrupted"),
    ],
)
def test_replay_operational_failures_are_sanitized(
    error: BaseException,
    code: int,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def failed(*args: object, **kwargs: object) -> Never:
        raise error

    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    monkeypatch.setattr(replay, "replay_run", failed)
    assert main(arguments(UUID(int=1), tmp_path / "raw", tmp_path / "out")) == code
    text = capsys.readouterr()
    assert json.loads(text.out) == {"status": "failed", "failure": reason}
    assert "private-sentinel" not in text.out and not text.err
