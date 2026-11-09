"""Page history and replay exercise a real PostgreSQL transaction boundary."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from nima.ingestion.archive import Archive
from nima.storage.postgres import CheckpointError, PageStore, migrate
from tests.test_collection import QUERY, body


def store(pg_dsn: str, tmp_path: Path) -> PageStore:
    migrate(pg_dsn)
    return PageStore(pg_dsn, Archive(tmp_path / "archive"))


def counts(dsn: str) -> tuple[object, ...] | None:
    with psycopg.connect(dsn) as connection:
        return connection.execute("""SELECT
            (SELECT count(*) FROM nima.run_pages),
            (SELECT count(*) FROM nima.record_versions),
            (SELECT count(*) FROM nima.observations),
            (SELECT count(*) FROM nima.outbox)""").fetchone()


def test_page_replay_and_reverted_content_keep_observation_history(
    pg_dsn: str, tmp_path: Path
) -> None:
    database = store(pg_dsn, tmp_path)
    now = datetime.now(UTC)
    for index, title in enumerate(("A", "B", "A", "A")):
        run = uuid4()
        database.start_run(run, QUERY)
        raw = body(total=1, title=title, totalCostWithoutVAT="123456789012345678.90")
        assert database.commit_page(run, raw, observed_at=now + timedelta(seconds=index))
        assert not database.commit_page(run, raw, observed_at=now + timedelta(seconds=100))
    assert counts(pg_dsn) == (4, 2, 4, 4)
    with psycopg.connect(pg_dsn) as connection:
        rows = connection.execute("""SELECT v.normalized->>'title', p.observed_at,
            v.normalized->>'net_amount' FROM nima.observations o
            JOIN nima.record_versions v USING (source_id, normalizer_version, content_sha256)
            JOIN nima.run_pages p USING (run_id, page_number)
            ORDER BY o.observation_id""").fetchall()
        assert [r[0] for r in rows] == ["A", "B", "A", "A"]
        assert [r[1] for r in rows] == [now + timedelta(seconds=i) for i in range(4)]
        assert all(r[2] == "123456789012345678.90" for r in rows)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute("UPDATE nima.record_versions SET normalized = '{}'::jsonb")


def test_quarantine_keeps_original_row_locations(pg_dsn: str, tmp_path: Path) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.start_run(run, QUERY)
    assert database.commit_page(run, body(total=1, title=42), observed_at=datetime.now(UTC))
    assert counts(pg_dsn) == (1, 0, 0, 0)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT record_index FROM nima.quarantine").fetchone() == (0,)
        assert connection.execute("SELECT next_page FROM nima.ingest_runs").fetchone() == (1,)


def test_checkpoint_rejects_changed_pages_gaps_and_shapes(pg_dsn: str, tmp_path: Path) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    now = datetime.now(UTC)
    with pytest.raises(CheckpointError):
        database.commit_page(run, body(page=1), observed_at=now)
    database.commit_page(run, body(), observed_at=now)
    with pytest.raises(CheckpointError):
        database.commit_page(run, body(title="Changed"), observed_at=now)
    with pytest.raises(CheckpointError):
        database.commit_page(run, body(page=1, total=3), observed_at=now)
    database.commit_page(run, body(page=1), observed_at=now)
    assert counts(pg_dsn) == (2, 2, 2, 2)


def test_duplicate_source_rolls_back_every_page_effect(pg_dsn: str, tmp_path: Path) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, body(), observed_at=datetime.now(UTC))
    with pytest.raises(psycopg.errors.UniqueViolation):
        database.commit_page(
            run, body(page=1, referenceNumber="TEST-0"), observed_at=datetime.now(UTC)
        )
    assert counts(pg_dsn) == (1, 1, 1, 1)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT next_page FROM nima.ingest_runs").fetchone() == (1,)
