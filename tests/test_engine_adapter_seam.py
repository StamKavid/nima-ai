"""The engine works through the adapter protocol alone: a stand-in source needs no engine change.

A tiny adapter with its own name, versions, record shape and evidence pointers is run through the
real page store, collector and replay. Nothing here is KIMDIS, so these pass only if the engine
no longer depends on that source's fields.
"""

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg

from nima.dataops.replay import prepare_replay
from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from nima.sources.base import (
    DEFAULT_MAX_BYTES,
    NormalizedPage,
    NormalizedRecord,
    PageIssue,
    QueryPayload,
    SourceAdapter,
    SourcePageError,
    SourceProvenance,
    SourceRequest,
)
from nima.storage.postgres import PageStore, migrate
from tests.test_collection import QUERY, Clock
from tests.test_page_store import store as default_store


class StubAdapter:
    """A stand-in source whose pages look like {"page": n, "total": t, "rows": [{"id": ...}]}."""

    name = "stub"
    connector_version = "stub-connector-v7"
    normalizer_version = "stub-normalized-v3"
    provenance = SourceProvenance(
        endpoint="https://stub.example.invalid/rows",
        documentation_url="https://stub.example.invalid/docs",
        license="Synthetic test data, no real licence",
    )

    def query_payload(self) -> dict[str, object]:
        return {"stub": True}

    def request_for(self, page: int) -> SourceRequest:
        return SourceRequest("GET", self.provenance.endpoint, {"page": page}, None, "text/plain")

    def normalize_page(self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> NormalizedPage:
        if len(raw) > max_bytes:
            raise SourcePageError("too large")
        try:
            data = json.loads(raw)
            rows: list[Mapping[str, object]] = data["rows"]
            number, total = int(data["page"]), int(data["total"])
        except (ValueError, KeyError, TypeError):
            raise SourcePageError("bad stub page") from None
        hashes = tuple(
            hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest() for r in rows
        )
        records, issues, ids = [], [], []
        for index, row in enumerate(rows):
            if "id" in row:
                ids.append(f"stub:{row['id']}")
            if "amount" in row and isinstance(row["amount"], str):
                records.append(
                    NormalizedRecord(
                        index=index,
                        evidence_pointer=f"/rows/{index}",
                        source_id=f"stub:{row['id']}",
                        content_sha256=hashes[index],
                        normalized={"id": row["id"], "amount": row["amount"]},
                    )
                )
            else:
                issues.append(PageIssue(index, f"/rows/{index}", "missing_amount"))
        return NormalizedPage(
            number=number,
            size=len(rows),
            total_records=total,
            total_pages=1,
            last=True,
            record_count=len(rows),
            response_sha256=hashlib.sha256(raw).hexdigest(),
            records=tuple(records),
            issues=tuple(issues),
            source_ids=tuple(ids),
            record_hashes=hashes,
        )


PAGE = json.dumps(
    {
        "page": 0,
        "total": 3,
        "rows": [{"id": "a", "amount": "1.10"}, {"id": "b"}, {"id": "c", "amount": "2"}],
    }
).encode()
adapter: SourceAdapter = StubAdapter()


def test_page_store_persists_the_adapters_identity_records_and_issues(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = uuid4()
    database = PageStore(pg_dsn, Archive(tmp_path / "raw"), adapter)
    database.start_run(run, QueryPayload(adapter.query_payload()))
    assert database.commit_page(run, PAGE, observed_at=datetime.now(UTC))
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT connector_version, normalizer_version FROM nima.ingest_runs"
        ).fetchall() == [("stub-connector-v7", "stub-normalized-v3")]
        assert c.execute(
            "SELECT source_id, normalizer_version, normalized FROM nima.record_versions "
            "ORDER BY source_id"
        ).fetchall() == [
            ("stub:a", "stub-normalized-v3", {"id": "a", "amount": "1.10"}),
            ("stub:c", "stub-normalized-v3", {"id": "c", "amount": "2"}),
        ]
        assert c.execute(
            "SELECT record_index, source_id FROM nima.observations ORDER BY record_index"
        ).fetchall() == [(0, "stub:a"), (2, "stub:c")]
        assert c.execute("SELECT record_index, reason FROM nima.quarantine").fetchall() == [
            (1, "missing_amount")
        ]
        assert c.execute(
            "SELECT record_count, quarantined_count, source_ids FROM nima.run_pages"
        ).fetchall() == [(3, 1, ["stub:a", "stub:b", "stub:c"])]


def test_a_store_for_one_source_refuses_a_run_started_by_another(
    pg_dsn: str, tmp_path: Path
) -> None:
    import pytest

    from nima.storage.postgres import CheckpointError

    migrate(pg_dsn)
    run = uuid4()
    PageStore(pg_dsn, Archive(tmp_path / "raw"), adapter).start_run(
        run, QueryPayload(adapter.query_payload())
    )
    with pytest.raises(CheckpointError):
        default_store(pg_dsn, tmp_path).start_run(run, QUERY)


def test_collector_runs_a_stand_in_source_end_to_end(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=PAGE))
    with httpx.Client(transport=transport) as client:
        summary = collect(
            None,
            Limits(),
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=adapter,
        )
    assert summary.status == "quarantined" and summary.collection_complete
    assert (summary.records, summary.normalized, summary.quarantined) == (3, 2, 1)
    run_dir = tmp_path / "raw" / "runs" / summary.run_id
    rows = [json.loads(line) for line in (run_dir / "normalized.jsonl").read_text().splitlines()]
    digest = hashlib.sha256(PAGE).hexdigest()
    assert rows[0] == {
        "id": "a",
        "amount": "1.10",
        "evidence": {"response_sha256": digest, "json_pointer": "/rows/0"},
    }
    issue = json.loads((run_dir / "quarantine.jsonl").read_text())
    assert issue == {
        "reason": "missing_amount",
        "evidence": {"response_sha256": digest, "json_pointer": "/rows/1"},
    }


def test_replay_uses_the_adapters_name_versions_and_pointers(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=PAGE))
    with httpx.Client(transport=transport) as client:
        summary = collect(
            None,
            Limits(),
            Archive(tmp_path / "raw"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=adapter,
        )
    body, replay = prepare_replay(
        pg_dsn, UUID(summary.run_id), tmp_path / "raw", adapter.normalizer_version, adapter
    )
    document = json.loads(body)
    assert document["artifact_version"] == "stub-archive-replay-v1"
    assert document["source"] == "stub.contract"
    assert document["normalizer_version"] == "stub-normalized-v3"
    records = document["pages"][0]["records"]
    assert [(r["record_index"], r["json_pointer"], r["status"]) for r in records] == [
        (0, "/rows/0", "normalized"),
        (1, "/rows/1", "quarantined"),
        (2, "/rows/2", "normalized"),
    ]
    assert (replay.normalized_count, replay.quarantined_count) == (2, 1)
