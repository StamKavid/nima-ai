"""The shared engine behaves identically for every source: collect, resume, replay, quarantine.

Parametrized over KIMDIS and the two invented sources. Nothing in the engine is told which source
it is running; each case brings only an adapter and the pages a source would serve. Passing for
all three, with no engine change, is what shows the adapter protocol is general rather than fitted
to one feed.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from nima.dataops.replay import prepare_replay
from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits, Summary
from nima.ingestion.resume import resume
from nima.sources.base import SourceAdapter
from nima.sources.kimdis import KimdisAdapter
from nima.storage.postgres import CheckpointError, PageStore, migrate
from nima.storage.runs import RunStore
from tests.synthetic_sources import (
    EventsAdapter,
    LedgerAdapter,
    event,
    events_page,
    ledger_page,
)
from tests.test_collection import QUERY, Clock, body


@dataclass(frozen=True)
class EngineCase:
    make: Callable[[], SourceAdapter]
    pages: tuple[bytes, ...]  # three pages; the second holds exactly one quarantined record
    bad_pointer: str  # where that quarantined record sits in the second page
    first_pointer: str  # where the first record of the first page sits
    repeated_id_pages: tuple[bytes, ...]  # two pages whose records share one source identifier


KIMDIS = EngineCase(
    make=lambda: KimdisAdapter(QUERY),
    pages=(body(0, 3), body(1, 3, title=42), body(2, 3)),
    bad_pointer="/content/0",
    first_pointer="/content/0",
    repeated_id_pages=(body(0, 2), body(1, 2, referenceNumber="TEST-0")),
)
LEDGER = EngineCase(
    make=LedgerAdapter,
    pages=(
        ledger_page(0, 3, 3, [("L-0001", "1.234,56", "a")]),
        ledger_page(1, 3, 3, [("L-0002", "oops", "b")]),
        ledger_page(2, 3, 3, [("L-0003", "3,00", "c")]),
    ),
    bad_pointer="line:3",
    first_pointer="line:3",
    repeated_id_pages=(
        ledger_page(0, 2, 2, [("L-0001", "1,00", "a")]),
        ledger_page(1, 2, 2, [("L-0001", "2,00", "b")]),
    ),
)
EVENTS = EngineCase(
    make=EventsAdapter,
    pages=(
        events_page(0, 3, 3, [event("acme", 1, 12345)]),
        events_page(1, 3, 3, [event("acme", 2, "oops")]),
        events_page(2, 3, 3, [event("acme", 3, 300, "JPY")]),
    ),
    bad_pointer="/data/0",
    first_pointer="/data/0",
    repeated_id_pages=(
        events_page(0, 2, 2, [event("acme", 1, 100)]),
        events_page(1, 2, 2, [event("acme", 1, 200)]),
    ),
)
CASES = [
    pytest.param(KIMDIS, id="kimdis"),
    pytest.param(LEDGER, id="ledger"),
    pytest.param(EVENTS, id="events"),
]


def serve(pages: tuple[bytes, ...], requests: list[int] | None = None) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params["page"])
        if requests is not None:
            requests.append(number)
        return httpx.Response(200, content=pages[number])

    return httpx.Client(transport=httpx.MockTransport(handle))


def run_collect(
    case: EngineCase, dsn: str, root: Path, requests: list[int] | None = None
) -> Summary:
    with serve(case.pages, requests) as client:
        return collect(
            QUERY,
            Limits(),
            Archive(root),
            client=client,
            clock=Clock(),
            database_dsn=dsn,
            adapter=case.make(),
        )


@pytest.mark.parametrize("case", CASES)
def test_collect_runs_to_a_quarantined_completion_and_counts_every_record(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    requests: list[int] = []
    summary = run_collect(case, pg_dsn, tmp_path / "raw", requests)
    assert requests == [0, 1, 2]
    assert summary.status == "quarantined" and summary.collection_complete
    assert not summary.normalization_complete
    assert (summary.pages, summary.records, summary.normalized, summary.quarantined) == (3, 3, 2, 1)
    assert (summary.expected_pages, summary.expected_records) == (3, 3)
    assert summary.duplicate_ids == 0 and summary.unidentified == 0


@pytest.mark.parametrize("case", CASES)
def test_the_database_keeps_the_adapters_identity_namespace_and_quarantine(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    adapter = case.make()
    migrate(pg_dsn)
    run_collect(case, pg_dsn, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT connector_version, normalizer_version FROM nima.ingest_runs"
        ).fetchall() == [(adapter.connector_version, adapter.normalizer_version)]
        versions = c.execute(
            "SELECT source_id, normalizer_version FROM nima.record_versions ORDER BY source_id"
        ).fetchall()
        assert len(versions) == 2
        assert all(
            sid.startswith(adapter.name + ":") and nv == adapter.normalizer_version
            for sid, nv in versions
        )
        assert c.execute("SELECT count(*) FROM nima.observations").fetchone() == (2,)
        quarantined = c.execute("SELECT record_index FROM nima.quarantine").fetchall()
        assert quarantined == [(0,)]
        assert c.execute("SELECT count(*) FROM nima.run_pages").fetchone() == (3,)
        assert c.execute(
            "SELECT sum(record_count), sum(quarantined_count) FROM nima.run_pages"
        ).fetchone() == (3, 1)


@pytest.mark.parametrize("case", CASES)
def test_archive_sidecars_point_at_the_exact_bytes_of_each_record(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    summary = run_collect(case, pg_dsn, tmp_path / "raw")
    run_dir = tmp_path / "raw" / "runs" / summary.run_id
    rows = [json.loads(x) for x in (run_dir / "normalized.jsonl").read_text().splitlines()]
    issues = [json.loads(x) for x in (run_dir / "quarantine.jsonl").read_text().splitlines()]
    assert len(rows) == 2 and len(issues) == 1
    assert rows[0]["evidence"] == {
        "response_sha256": hashlib.sha256(case.pages[0]).hexdigest(),
        "json_pointer": case.first_pointer,
    }
    assert rows[1]["evidence"]["response_sha256"] == hashlib.sha256(case.pages[2]).hexdigest()
    assert issues[0]["evidence"] == {
        "response_sha256": hashlib.sha256(case.pages[1]).hexdigest(),
        "json_pointer": case.bad_pointer,
    }
    assert isinstance(issues[0]["reason"], str) and issues[0]["reason"]


@pytest.mark.parametrize("case", CASES)
def test_resume_continues_from_the_committed_prefix_and_is_idempotent(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    from datetime import UTC, datetime

    adapter = case.make()
    migrate(pg_dsn)
    archive = Archive(tmp_path / "raw")
    run = uuid4()
    writer = RunStore(pg_dsn, archive, run, Limits(), adapter)
    with writer.lease():
        writer.begin(QUERY)
        writer.commit_page(run, case.pages[0], observed_at=datetime.now(UTC), owner=writer.owner)
    requests: list[int] = []
    with serve(case.pages, requests) as client:
        result = resume(pg_dsn, run, client=client, clock=Clock(), adapter=adapter)
        assert result.status == "quarantined" and result.collection_complete
        assert requests == [0, 1, 2]
        assert (result.records, result.normalized, result.quarantined) == (3, 2, 1)
        again = resume(pg_dsn, run, client=client, clock=Clock(), adapter=adapter)
    assert again.status == "quarantined" and requests == [0, 1, 2]
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima.record_versions").fetchone() == (2,)
        assert c.execute("SELECT count(*) FROM nima.quarantine").fetchone() == (1,)


@pytest.mark.parametrize("case", CASES)
def test_replay_from_the_archive_agrees_with_what_collect_stored(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    adapter = case.make()
    migrate(pg_dsn)
    summary = run_collect(case, pg_dsn, tmp_path / "raw")
    text, replay = prepare_replay(
        pg_dsn, UUID(summary.run_id), tmp_path / "raw", adapter.normalizer_version, adapter
    )
    document = json.loads(text)
    assert document["normalizer_version"] == adapter.normalizer_version
    assert (replay.normalized_count, replay.quarantined_count) == (2, 1)
    flat = [
        (r["record_index"], r["json_pointer"], r["status"])
        for page in document["pages"]
        for r in page["records"]
    ]
    assert flat == [
        (0, case.first_pointer, "normalized"),
        (0, case.bad_pointer, "quarantined"),
        (0, case.first_pointer, "normalized"),
    ]


@pytest.mark.parametrize("case", CASES)
def test_a_repeated_source_identifier_stops_the_run_before_it_claims_completeness(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    with serve(case.repeated_id_pages) as client:
        summary = collect(
            QUERY,
            Limits(),
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=case.make(),
        )
    assert summary.status == "failed" and summary.failure == "identity_coverage"
    assert not summary.collection_complete


def test_three_sources_share_one_database_without_mixing_identity(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    cases = {"kimdis": KIMDIS, "ledger": LEDGER, "events": EVENTS}
    runs = {
        name: run_collect(case, pg_dsn, tmp_path / f"raw-{name}") for name, case in cases.items()
    }
    assert len({s.run_id for s in runs.values()}) == 3
    with psycopg.connect(pg_dsn) as c:
        by_namespace: dict[str, int] = dict(
            c.execute(
                "SELECT split_part(source_id, ':', 1), count(*) FROM nima.record_versions "
                "GROUP BY 1"
            ).fetchall()
        )
        assert by_namespace == {"kimdis": 2, "ledger": 2, "events": 2}
        identities = set(
            c.execute("SELECT connector_version, normalizer_version FROM nima.ingest_runs")
        )
        assert len(identities) == 3


@pytest.mark.parametrize("other", [LEDGER, EVENTS], ids=["ledger", "events"])
def test_a_store_for_one_source_refuses_a_run_started_by_another(
    other: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = uuid4()
    PageStore(pg_dsn, Archive(tmp_path / "raw"), KimdisAdapter(QUERY)).start_run(run, QUERY)
    with pytest.raises(CheckpointError):
        PageStore(pg_dsn, Archive(tmp_path / "raw"), other.make()).start_run(run, QUERY)
