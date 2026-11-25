"""The KIMDIS projection leaves other sources' outbox events alone instead of stalling on them.

The outbox holds events of every source, and the projector reads one. An unscoped drain must not
claim, fail on or count another source's event: otherwise one Diavgeia event blocks every later
KIMDIS event, and the backlog never reaches zero. An event of its own source that it cannot
project (an unknown normalizer version, a bad shape) must still stop visibly; `test_participation`
pins that.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from nima.projections.worker import ProjectionFailure, drain
from nima.storage.postgres import migrate
from tests.test_collection import QUERY
from tests.test_kimdis_pages import page_body, record
from tests.test_page_store import store
from tests.test_source_engine_conformance import DIAVGEIA, run_collect


def kimdis_run(dsn: str, path: Path, count: int) -> None:
    database = store(dsn, path)
    run = uuid4()
    database.start_run(run, QUERY)
    rows = [record(f"26SYMV00000000{i}") for i in range(count)]
    database.commit_page(run, page_body(*rows), observed_at=datetime(2026, 11, 6, tzinfo=UTC))


def outbox(dsn: str) -> dict[str, tuple[int, int]]:
    """Per source namespace: (events, delivered events)."""
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT split_part(o.source_id, ':', 1), count(*), count(q.delivered_at) "
            "FROM nima.outbox q JOIN nima.observations o USING (observation_id) "
            "GROUP BY 1 ORDER BY 1"
        ).fetchall()
    return {name: (total, delivered) for name, total, delivered in rows}


def test_an_unscoped_drain_projects_kimdis_events_that_follow_another_sources_events(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run_collect(DIAVGEIA, pg_dsn, tmp_path / "diavgeia")  # first, so its events have lower ids
    kimdis_run(pg_dsn, tmp_path / "kimdis", 3)
    before = outbox(pg_dsn)
    assert before["diavgeia"] == (2, 0) and before["kimdis"] == (3, 0)
    result = drain(pg_dsn)
    assert result["processed_events"] == 3 and result["remaining_events"] == 0
    assert result["status"] == "complete"
    # The other source's events stay undelivered for their own consumer.
    assert outbox(pg_dsn) == {"diavgeia": (2, 0), "kimdis": (3, 3)}
    assert drain(pg_dsn)["processed_events"] == 0


def test_a_database_with_only_another_sources_events_has_nothing_to_project(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run_collect(DIAVGEIA, pg_dsn, tmp_path / "diavgeia")
    result = drain(pg_dsn)
    assert (result["processed_events"], result["remaining_events"]) == (0, 0)
    assert result["status"] == "complete" and outbox(pg_dsn) == {"diavgeia": (2, 0)}


def test_explicitly_asking_for_another_sources_run_still_fails_visibly(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run_collect(DIAVGEIA, pg_dsn, tmp_path / "diavgeia")
    with psycopg.connect(pg_dsn) as connection:
        row = connection.execute("SELECT run_id FROM nima.ingest_runs").fetchone()
    assert row is not None
    with pytest.raises(ProjectionFailure) as caught:
        drain(pg_dsn, run_id=row[0])
    assert caught.value.reason == "invalid_projection"
