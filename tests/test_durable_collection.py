"""The real collector writes attempts and pages into disposable PostgreSQL."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import psycopg
import pytest

from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from nima.storage.postgres import CheckpointError, PageStore, migrate
from nima.storage.runs import inspect_run
from tests.test_collection import QUERY, Clock, body


def test_http_retries_and_pages_are_durable(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    archive = Archive(tmp_path / "raw")
    replies = iter(
        [
            httpx.Response(429, content=b"busy", headers={"retry-after": "2"}),
            httpx.Response(200, content=body()),
            httpx.Response(200, content=body(page=1)),
        ]
    )
    with httpx.Client(transport=httpx.MockTransport(lambda _: next(replies))) as client:
        summary = collect(
            QUERY, Limits(), archive, client=client, clock=Clock(), database_dsn=pg_dsn
        )
    state = inspect_run(pg_dsn, UUID(summary.run_id))
    assert state["status"] == "complete" and state["collection_complete"] is True
    assert state["pages"] == state["records"] == state["normalized"] == state["next_page"] == 2
    assert state["attempts"] == 3 and state["pending_attempts"] == 0
    assert state["worker_liveness"] == "unknown"
    with psycopg.connect(pg_dsn) as connection:
        receipts = connection.execute(
            "SELECT receipt FROM nima.http_attempts ORDER BY attempt_id"
        ).fetchall()
        assert [r[0]["status"] for r in receipts] == [429, 200, 200]
        assert connection.execute("SELECT count(*) FROM nima.outbox").fetchone() == (2,)
    for row in receipts:
        digest = row[0]["sha256"]
        assert (archive.root / "objects" / digest[:2] / f"{digest}.body").exists()
    with pytest.raises(CheckpointError):
        PageStore(pg_dsn, archive).commit_page(
            UUID(summary.run_id), body(), observed_at=datetime.now(UTC)
        )


@pytest.mark.parametrize(
    ("responses", "limits", "failure", "pages"),
    [
        ([httpx.Response(403, content=b"denied")], Limits(), "http_403", 0),
        ([httpx.Response(200, content=b"invalid")], Limits(), "invalid_page", 0),
        ([httpx.Response(200, content=body())], Limits(max_pages=1), "page_limit", 1),
    ],
)
def test_incomplete_run_inspection_is_honest(
    pg_dsn: str,
    tmp_path: Path,
    responses: list[httpx.Response],
    limits: Limits,
    failure: str,
    pages: int,
) -> None:
    migrate(pg_dsn)
    replies = iter(responses)
    with httpx.Client(transport=httpx.MockTransport(lambda _: next(replies))) as client:
        summary = collect(
            QUERY,
            limits,
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
        )
    state = inspect_run(pg_dsn, UUID(summary.run_id))
    assert state["status"] == "failed" and state["failure"] == failure
    assert state["pages"] == pages and state["collection_complete"] is False


@pytest.mark.parametrize(
    ("record", "complete", "unknown"),
    [
        ({"title": 42}, True, 0),
        ({"referenceNumber": None}, False, 1),
    ],
)
def test_quarantine_counts_come_from_committed_pages(
    pg_dsn: str, tmp_path: Path, record: dict[str, object], complete: bool, unknown: int
) -> None:
    migrate(pg_dsn)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                content=body(
                    total=1,
                    title=record.get("title", "Synthetic"),
                    referenceNumber=record.get("referenceNumber", "TEST-0"),
                ),
            )
        )
    ) as client:
        summary = collect(
            QUERY,
            Limits(),
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
        )
    state = inspect_run(pg_dsn, UUID(summary.run_id))
    assert state["collection_complete"] is complete
    assert state["quarantined"] == 1 and state["unidentified"] == unknown
    assert state["normalization_complete"] is False
