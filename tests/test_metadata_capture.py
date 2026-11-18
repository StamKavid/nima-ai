"""The metadata consumer shares replay's frozen, verified original capture."""

import json
import shutil
from pathlib import Path

import pytest

from nima.dataops.replay import ReplayError, read_capture
from nima.storage.postgres import NORMALIZER_VERSION
from tests.test_analytics_snapshot import reader, seed, state


def test_capture_reuses_closed_sql_and_verified_bytes_without_changing_replay(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.dataops.replay import prepare_replay

    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        old_body, old_summary = prepare_replay(dsn, run, root, NORMALIZER_VERSION)
        capture = read_capture(dsn, run, root)
        assert capture.run["run_id"] == str(run)
        assert len(capture.pages) == len(capture.bodies) == 1
        assert capture.pages[0].observed_at == "2026-01-01T00:00:00+00:00"
        assert json.loads(capture.bodies[capture.pages[0].raw_sha256])["content"]
        relocated = tmp_path / "relocated"
        shutil.copytree(root, relocated)
        assert read_capture(dsn, run, relocated) == capture
        assert prepare_replay(dsn, run, relocated, NORMALIZER_VERSION) == (old_body, old_summary)
    assert state(pg_dsn) == before


def test_corrupt_capture_fails_without_repair(pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    target = next((root / "objects").rglob("*.body"))
    target.write_bytes(b"damaged")
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReplayError, match="^replay_evidence$"):
        read_capture(dsn, run, root)
    assert target.read_bytes() == b"damaged"
