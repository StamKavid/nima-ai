"""Replay and promotion take the source the run was collected from; KIMDIS stays the default."""

import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from nima.__main__ import main
from nima.sources.kimdis import KimdisAdapter
from nima.storage.postgres import NORMALIZER_VERSION, migrate
from tests.test_analytics_snapshot import reader, seed
from tests.test_collection import QUERY, body
from tests.test_replay_promotion import promoter
from tests.test_source_engine_conformance import (
    DIAVGEIA,
    DIAVGEIA_COMMITMENT,
    EngineCase,
    run_collect,
)

SOURCES = [
    pytest.param(DIAVGEIA, "diavgeia", "diavgeia-decision-v1", id="award"),
    pytest.param(DIAVGEIA_COMMITMENT, "diavgeia-commitment", "diavgeia-commitment-v1", id="commit"),
]


def collected(case: EngineCase, dsn: str, root: Path) -> UUID:
    migrate(dsn)
    run_collect(case, dsn, root)
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT run_id FROM nima.ingest_runs").fetchone()
    assert row is not None
    run: UUID = row[0]
    return run


def replay_args(run: UUID, root: Path, output: Path, version: str, *source: str) -> list[str]:
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
        version,
        *source,
    ]


def promote_args(run: UUID, root: Path, version: str, digest: str, *source: str) -> list[str]:
    return [
        "archive",
        "promote",
        "--run-id",
        str(run),
        "--archive-dir",
        str(root),
        "--normalizer-version",
        version,
        "--replay-sha256",
        digest,
        *source,
    ]


def output_of(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


@pytest.mark.parametrize(("case", "key", "version"), SOURCES)
def test_replay_with_its_source_rebuilds_every_record_and_repeats_exactly(
    case: EngineCase,
    key: str,
    version: str,
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = collected(case, pg_dsn, tmp_path / "raw")
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        for _ in range(2):
            args = replay_args(run, tmp_path / "raw", tmp_path / "out", version, "--source", key)
            assert main(args) == 0
            result = output_of(capsys)
    assert result == {
        "status": "complete",
        "outcome": "replayed_committed_pages",
        "page_count": 3,
        "record_count": 3,
        "normalized_count": 2,
        "quarantined_count": 1,
    }
    assert len(list((tmp_path / "out").glob("*.json"))) == 1


@pytest.mark.parametrize(("case", "key", "version"), SOURCES)
def test_a_source_that_is_not_the_runs_is_refused_with_a_fixed_reason(
    case: EngineCase,
    key: str,
    version: str,
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = collected(case, pg_dsn, tmp_path / "raw")
    other, other_version = (
        ("diavgeia-commitment", "diavgeia-commitment-v1")
        if key == "diavgeia"
        else ("diavgeia", "diavgeia-decision-v1")
    )
    attempts = [
        # The right normaliser version for the run, but not the source's: the version check fails.
        (version, ()),
        (version, ("--source", "kimdis")),
        (version, ("--source", other)),
        # The other source's own version: only the connector version tells it is not this run's.
        (other_version, ("--source", other)),
        (NORMALIZER_VERSION, ()),
    ]
    reasons = ["replay_version"] * 3 + ["replay_source"] * 2
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        for (used, source), reason in zip(attempts, reasons, strict=True):
            args = replay_args(run, tmp_path / "raw", tmp_path / "out", used, *source)
            assert main(args) == (2 if reason == "replay_version" else 1)
            assert output_of(capsys) == {"status": "failed", "failure": reason}
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("source", ["", "nosuch", "KIMDIS"])
def test_an_unknown_source_is_refused_before_any_database_access(
    source: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "postgresql://unreachable.invalid/none")
    replay = replay_args(
        UUID(int=1), tmp_path, tmp_path / "out", NORMALIZER_VERSION, "--source", source
    )
    promote = promote_args(UUID(int=1), tmp_path, NORMALIZER_VERSION, "0" * 64, "--source", source)
    for args in (replay, promote):
        assert main(args) == 2
        assert output_of(capsys) == {"status": "failed", "failure": "archive_configuration"}


def test_kimdis_is_the_default_and_naming_it_changes_nothing(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = seed(pg_dsn, tmp_path / "raw", project=False)
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        for name, source in (("a", ()), ("b", ("--source", "kimdis"))):
            args = replay_args(run, tmp_path / "raw", tmp_path / name, NORMALIZER_VERSION, *source)
            assert main(args) == 0
            capsys.readouterr()
    first = sorted(p.name for p in (tmp_path / "a").glob("*.json"))
    assert first and first == sorted(p.name for p in (tmp_path / "b").glob("*.json"))


@pytest.mark.parametrize(("case", "key", "version"), SOURCES)
def test_promotion_with_its_source_stores_once_and_a_retry_stores_nothing(
    case: EngineCase,
    key: str,
    version: str,
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "raw"
    run = collected(case, pg_dsn, root)
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(replay_args(run, root, tmp_path / "out", version, "--source", key)) == 0
    capsys.readouterr()
    digest = next((tmp_path / "out").glob("*.json")).stem
    with promoter(pg_dsn) as limited:
        monkeypatch.setenv("NIMA_DATABASE_URL", limited)
        assert main(promote_args(run, root, version, digest)) == 2
        assert output_of(capsys) == {"status": "failed", "failure": "replay_version"}
        for retried in (False, True):
            assert main(promote_args(run, root, version, digest, "--source", key)) == 0
            assert output_of(capsys) == {
                "status": "complete",
                "outcome": "promoted_replay",
                "page_count": 3,
                "record_count": 3,
                "normalized_count": 2,
                "quarantined_count": 1,
                "replayed": retried,
            }
    with psycopg.connect(pg_dsn) as connection:
        rows = connection.execute("SELECT count(*) FROM nima_processing.replay_results").fetchone()
    assert rows == (3,)


@pytest.mark.parametrize(("case", "key", "version"), SOURCES)
def test_a_replayed_record_carries_the_adapters_namespaced_source_id(
    case: EngineCase,
    key: str,
    version: str,
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = collected(case, pg_dsn, tmp_path / "raw")
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            main(replay_args(run, tmp_path / "raw", tmp_path / "out", version, "--source", key))
            == 0
        )
    document = json.loads(next((tmp_path / "out").glob("*.json")).read_text())
    normalized = [
        r["normalized"]
        for page in document["pages"]
        for r in page["records"]
        if r["status"] == "normalized"
    ]
    assert sorted(n["source_id"] for n in normalized) == [
        "diavgeia:ΑΒΓΔΕ-ΖΗ1",
        "diavgeia:ΑΒΓΔΕ-ΖΗ3",
    ]


def test_kimdis_records_already_carry_their_source_id_so_replay_adds_nothing() -> None:
    page = KimdisAdapter(QUERY).normalize_page(body(0, 1))
    assert page.records
    assert all(r.normalized["source_id"] == r.source_id for r in page.records)
