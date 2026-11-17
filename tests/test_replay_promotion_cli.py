"""Explicit SQL replay promotion is reachable through the real installed CLI."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Never
from uuid import UUID

import pytest

from nima.__main__ import main
from nima.dataops import promotion
from nima.storage.postgres import NORMALIZER_VERSION
from tests.test_replay_promotion import promoter, selection


def arguments(run: UUID, root: Path, digest: str) -> list[str]:
    return [
        "archive",
        "promote",
        "--run-id",
        str(run),
        "--archive-dir",
        str(root),
        "--normalizer-version",
        NORMALIZER_VERSION,
        "--replay-sha256",
        digest,
    ]


def test_installed_cli_promotes_as_limited_role_and_retries_idempotently(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    with promoter(pg_dsn) as limited:
        for retried in (False, True):
            result = subprocess.run(
                [sys.executable, "-m", "nima", *arguments(run, root, digest)],
                env={**os.environ, "NIMA_DATABASE_URL": limited},
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            assert result.returncode == 0 and not result.stderr
            assert json.loads(result.stdout) == {
                "status": "complete",
                "outcome": "promoted_replay",
                "page_count": 1,
                "record_count": 1,
                "normalized_count": 1,
                "quarantined_count": 0,
                "replayed": retried,
            }
            assert (
                str(root) not in result.stdout
                and digest not in result.stdout
                and str(run) not in result.stdout
            )


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        ["--run-id", "private-sentinel"],
        [
            "--run-id",
            str(UUID(int=1)),
            "--archive-dir",
            "/private-sentinel",
            "--normalizer-version",
            NORMALIZER_VERSION,
        ],
        [
            "--run-id",
            str(UUID(int=1)),
            "--archive-dir",
            "/private-sentinel",
            "--normalizer-version",
            NORMALIZER_VERSION,
            "--replay-sha256",
            "0" * 64,
            "--database-url",
            "private-sentinel",
        ],
    ],
)
def test_invalid_arguments_do_not_access_private_io(
    tokens: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid CLI cannot open SQL/files")

    monkeypatch.setattr(promotion, "promote_run", forbidden)
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    assert main(["archive", "promote", *tokens]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": "archive_configuration"}
    assert "private-sentinel" not in output.out and not output.err


@pytest.mark.parametrize(
    ("error", "code", "reason"),
    [
        (promotion.PromotionError("promotion_input"), 2, "promotion_input"),
        (promotion.PromotionError("promotion_selection"), 1, "promotion_selection"),
        (promotion.PromotionError("promotion_database"), 1, "promotion_database"),
        (KeyboardInterrupt(), 130, "archive_interrupted"),
    ],
)
def test_promotion_failures_have_fixed_private_safe_results(
    error: BaseException,
    code: int,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failed(*args: object, **kwargs: object) -> Never:
        raise error

    monkeypatch.setattr(promotion, "promote_run", failed)
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    assert main(arguments(UUID(int=1), Path("/private-sentinel"), "0" * 64)) == code
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": reason}
    assert "private-sentinel" not in output.out and not output.err
