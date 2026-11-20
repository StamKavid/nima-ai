"""The shared engine behaves identically for every source: collect, resume, replay, quarantine.

Parametrized over KIMDIS and the two invented sources. Nothing in the engine is told which source
it is running; each case brings only an adapter and the pages a source would serve. Passing for
all three, with no engine change, is what shows the adapter protocol is general rather than fitted
to one feed.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from nima.dataops.replay import prepare_replay
from nima.ingestion.archive import Archive
from nima.ingestion.collector import RunError, collect
from nima.ingestion.config import Limits, Summary
from nima.ingestion.resume import resume
from nima.sources import registry
from nima.sources.base import (
    DEFAULT_MAX_BYTES,
    NormalizedPage,
    QueryPayload,
    SourceAdapter,
    SourceProvenance,
    SourceRequest,
    SourceRequestError,
)
from nima.sources.kimdis import KimdisAdapter
from nima.sources.registry import RegisteredSource
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
    page_param: str  # the query parameter this source's requests carry the page number in


KIMDIS = EngineCase(
    make=lambda: KimdisAdapter(QUERY),
    pages=(body(0, 3), body(1, 3, title=42), body(2, 3)),
    bad_pointer="/content/0",
    first_pointer="/content/0",
    repeated_id_pages=(body(0, 2), body(1, 2, referenceNumber="TEST-0")),
    page_param="page",
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
    page_param="p",
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
    page_param="seq",
)
CASES = [
    pytest.param(KIMDIS, id="kimdis"),
    pytest.param(LEDGER, id="ledger"),
    pytest.param(EVENTS, id="events"),
]


def serve(
    case: EngineCase,
    pages: tuple[bytes, ...] | None = None,
    requests: list[int] | None = None,
    sent: list[httpx.Request] | None = None,
) -> httpx.Client:
    """A mock of the source: it answers by the page number in the parameter the source uses."""
    served = case.pages if pages is None else pages

    def handle(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params[case.page_param])
        if requests is not None:
            requests.append(number)
        if sent is not None:
            sent.append(request)
        return httpx.Response(200, content=served[number])

    return httpx.Client(transport=httpx.MockTransport(handle))


def run_collect(
    case: EngineCase,
    dsn: str,
    root: Path,
    requests: list[int] | None = None,
    sent: list[httpx.Request] | None = None,
) -> Summary:
    with serve(case, requests=requests, sent=sent) as client:
        return collect(
            None,
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
        writer.begin(QueryPayload(adapter.query_payload()))
        writer.commit_page(run, case.pages[0], observed_at=datetime.now(UTC), owner=writer.owner)
    requests: list[int] = []
    with serve(case, requests=requests) as client:
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
    with serve(case, case.repeated_id_pages) as client:
        summary = collect(
            None,
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
    kimdis = KimdisAdapter(QUERY)
    PageStore(pg_dsn, Archive(tmp_path / "raw"), kimdis).start_run(run, QUERY)
    with pytest.raises(CheckpointError):
        PageStore(pg_dsn, Archive(tmp_path / "raw"), other.make()).start_run(
            run, QueryPayload(other.make().query_payload())
        )


@pytest.mark.parametrize("case", CASES)
def test_every_request_goes_to_the_sources_own_endpoint_in_its_own_shape(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    adapter = case.make()
    migrate(pg_dsn)
    sent: list[httpx.Request] = []
    run_collect(case, pg_dsn, tmp_path / "raw", sent=sent)
    assert len(sent) == 3
    for number, request in enumerate(sent):
        expected = adapter.request_for(number)
        assert request.method == expected.method
        assert str(request.url.copy_with(query=None)) == adapter.provenance.endpoint
        assert request.url.params[case.page_param] == str(number)
        assert request.headers["accept"] == expected.accept
        assert request.headers["accept-encoding"] == "identity"
        assert request.headers["user-agent"].startswith("Nima/")
        assert (json.loads(request.content) if request.content else None) == expected.json
    assert len({str(r.url.copy_with(query=None)) for r in sent}) == 1


def test_the_three_sources_use_different_methods_bodies_and_media_types() -> None:
    shapes = {case.page_param: case.make().request_for(0) for case in (KIMDIS, LEDGER, EVENTS)}
    assert {k: (v.method, v.json is None, v.accept) for k, v in shapes.items()} == {
        "page": ("POST", False, "application/json"),
        "p": ("GET", True, "text/csv"),
        "seq": ("POST", False, "application/json"),
    }


@pytest.mark.parametrize("case", CASES)
def test_the_manifest_records_the_sources_own_provenance(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    adapter = case.make()
    migrate(pg_dsn)
    summary = run_collect(case, pg_dsn, tmp_path / "raw")
    manifest = json.loads(
        (tmp_path / "raw" / "runs" / summary.run_id / "manifest.json").read_bytes()
    )
    assert manifest["endpoint"] == adapter.provenance.endpoint
    assert manifest["source"] == adapter.provenance.documentation_url
    assert manifest["license"] == adapter.provenance.license
    assert manifest["connector_version"] == adapter.connector_version


def test_no_source_borrows_anothers_provenance_in_its_manifest(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    seen: set[tuple[object, object, object]] = set()
    for name, case in {"kimdis": KIMDIS, "ledger": LEDGER, "events": EVENTS}.items():
        summary = run_collect(case, pg_dsn, tmp_path / f"raw-{name}")
        manifest = json.loads(
            (tmp_path / f"raw-{name}" / "runs" / summary.run_id / "manifest.json").read_bytes()
        )
        seen.add((manifest["endpoint"], manifest["source"], manifest["license"]))
    assert len({endpoint for endpoint, _, _ in seen}) == 3


class MiswiredAdapter:
    """Delegates to a real adapter but changes one thing the guard must catch."""

    def __init__(
        self,
        inner: SourceAdapter,
        *,
        endpoint: str | None = None,
        request_url: str | None = None,
        from_page: int = 0,
        query: dict[str, object] | None = None,
    ) -> None:
        self._inner, self._endpoint, self._request_url = inner, endpoint, request_url
        self._from_page, self._query = from_page, query
        self.name = inner.name
        self.connector_version = inner.connector_version
        self.normalizer_version = inner.normalizer_version

    @property
    def provenance(self) -> SourceProvenance:
        base = self._inner.provenance
        return SourceProvenance(
            self._endpoint or base.endpoint, base.documentation_url, base.license
        )

    def query_payload(self) -> dict[str, object]:
        return self._inner.query_payload() if self._query is None else self._query

    def request_for(self, page: int) -> SourceRequest:
        request = self._inner.request_for(page)
        misrouted = self._request_url is not None and page >= self._from_page
        url = self._request_url if misrouted and self._request_url else request.url
        return SourceRequest(request.method, url, request.params, request.json, request.accept)

    def normalize_page(self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> NormalizedPage:
        return self._inner.normalize_page(raw, max_bytes=max_bytes)


@pytest.mark.parametrize(
    ("endpoint", "request_url"),
    [
        ("https://declared.example.invalid/api", "https://other.example.invalid/steal"),
        ("http://plain.example.invalid/api", "http://plain.example.invalid/api"),
    ],
    ids=["request-leaves-declared-endpoint", "insecure-endpoint"],
)
@pytest.mark.parametrize("case", CASES)
def test_a_miswired_adapter_is_refused_before_any_run_file_or_request_exists(
    case: EngineCase, endpoint: str, request_url: str, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    sent: list[httpx.Request] = []
    root = tmp_path / "raw"
    adapter = MiswiredAdapter(case.make(), endpoint=endpoint, request_url=request_url)
    with serve(case, sent=sent) as client, pytest.raises(SourceRequestError):
        collect(
            None,
            Limits(),
            Archive(root),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=adapter,
        )
    assert sent == []
    assert not (root / "runs").exists() or not list((root / "runs").iterdir())
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima.ingest_runs").fetchone() == (0,)


@pytest.mark.parametrize("case", CASES)
def test_a_request_that_goes_wrong_on_a_later_page_is_refused_before_it_is_sent(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    served: list[int] = []
    adapter = MiswiredAdapter(
        case.make(), request_url="https://other.example.invalid/steal", from_page=2
    )
    with serve(case, requests=served) as client, pytest.raises(SourceRequestError):
        collect(
            None,
            Limits(),
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=adapter,
        )
    assert served == [0, 1]


def register(monkeypatch: pytest.MonkeyPatch, case: EngineCase) -> None:
    """Make a synthetic source known to the registry for one test, as if it shipped."""
    adapter = case.make()
    if adapter.name in registry.known_sources():
        return

    def from_payload(payload: Mapping[str, object]) -> SourceAdapter:
        if dict(payload) != adapter.query_payload():
            raise ValueError("Invalid saved query")
        return case.make()

    monkeypatch.setitem(
        registry._SOURCES,
        adapter.name,
        RegisteredSource(adapter.connector_version, lambda query: case.make(), from_payload),
    )


def start_run_with_first_page(case: EngineCase, dsn: str, root: Path) -> UUID:
    adapter = case.make()
    run = uuid4()
    writer = RunStore(dsn, Archive(root), run, Limits(), adapter)
    with writer.lease():
        writer.begin(QueryPayload(adapter.query_payload()))
        writer.commit_page(run, case.pages[0], observed_at=datetime.now(UTC), owner=writer.owner)
    return run


@pytest.mark.parametrize("case", CASES)
def test_the_run_query_is_the_adapters_own_in_the_database_and_the_manifest(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    adapter = case.make()
    migrate(pg_dsn)
    summary = run_collect(case, pg_dsn, tmp_path / "raw")
    manifest = json.loads(
        (tmp_path / "raw" / "runs" / summary.run_id / "manifest.json").read_bytes()
    )
    assert manifest["query"] == adapter.query_payload()
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT query FROM nima.ingest_runs").fetchall() == [
            (adapter.query_payload(),)
        ]


@pytest.mark.parametrize("case", CASES)
def test_a_query_that_disagrees_with_the_adapter_is_refused_before_anything_exists(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    sent: list[httpx.Request] = []
    with serve(case, sent=sent) as client, pytest.raises(ValueError, match="disagree"):
        collect(
            QueryPayload({"somethingElse": True}),
            Limits(),
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=case.make(),
        )
    assert sent == []
    assert list((tmp_path / "raw" / "runs").iterdir()) == []
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima.ingest_runs").fetchone() == (0,)


@pytest.mark.parametrize("case", CASES)
def test_an_equal_query_and_adapter_are_accepted_and_neither_alone_is_required(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    adapter = case.make()
    migrate(pg_dsn)
    with serve(case) as client:
        summary = collect(
            QueryPayload(adapter.query_payload()),
            Limits(),
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=adapter,
        )
    assert summary.status == "quarantined"


def test_collect_needs_a_query_or_an_adapter() -> None:
    with pytest.raises(ValueError, match="query or an adapter"):
        collect(None, Limits(), Archive(Path("unused")), client=httpx.Client())


@pytest.mark.parametrize("case", CASES)
def test_resume_rebuilds_the_adapter_from_the_saved_run_through_the_registry(
    case: EngineCase, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(monkeypatch, case)
    migrate(pg_dsn)
    run = start_run_with_first_page(case, pg_dsn, tmp_path / "raw")
    requests: list[int] = []
    with serve(case, requests=requests) as client:
        result = resume(pg_dsn, run, client=client, clock=Clock())
    assert result.status == "quarantined" and result.collection_complete
    assert requests == [0, 1, 2]
    assert (result.records, result.normalized, result.quarantined) == (3, 2, 1)


@pytest.mark.parametrize("case", [LEDGER, EVENTS], ids=["ledger", "events"])
def test_resuming_a_run_whose_source_is_not_registered_stops_before_any_request(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = start_run_with_first_page(case, pg_dsn, tmp_path / "raw")
    sent: list[httpx.Request] = []
    with serve(case, sent=sent) as client, pytest.raises(CheckpointError):
        resume(pg_dsn, run, client=client, clock=Clock())
    assert sent == []


def test_resuming_a_kimdis_run_with_a_reshaped_saved_query_stops_before_any_request(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = uuid4()
    bad = QueryPayload({"dateFrom": "2026-11-06", "dateTo": "2026-11-06", "organizations": []})
    writer = RunStore(pg_dsn, Archive(tmp_path / "raw"), run, Limits(), KimdisAdapter(bad))
    with writer.lease():
        writer.begin(bad)
    sent: list[httpx.Request] = []
    with serve(KIMDIS, sent=sent) as client, pytest.raises(CheckpointError):
        resume(pg_dsn, run, client=client, clock=Clock())
    assert sent == []


@pytest.mark.parametrize("case", CASES)
def test_resuming_with_an_adapter_whose_query_differs_from_the_saved_one_is_refused(
    case: EngineCase, pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = start_run_with_first_page(case, pg_dsn, tmp_path / "raw")
    other = MiswiredAdapter(case.make(), query={"another": "query"})
    sent: list[httpx.Request] = []
    with serve(case, sent=sent) as client, pytest.raises(RunError) as refused:
        resume(pg_dsn, run, client=client, clock=Clock(), adapter=other)
    assert refused.value.reason == "database"
    assert sent == []
