"""A producer defect stops a page atomically, with raw evidence retained."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql

from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from nima.sources import kimdis
from nima.sources import kimdis_contracts as gates
from nima.storage.postgres import PageStore, migrate
from tests.test_analytics_snapshot import state
from tests.test_collection import QUERY, Clock, body
from tests.test_kimdis_contracts import source_page
from tests.test_kimdis_pages import page_body, record


@pytest.mark.parametrize("fault", ["type", "evidence"])
def test_bad_normalizer_output_stops_sql_page_but_keeps_raw_and_can_retry(
    pg_dsn: str, tmp_path: Path, fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    archive = Archive(tmp_path / "archive")
    store = PageStore(pg_dsn, archive)
    run = uuid4()
    store.start_run(run, QUERY)
    before = state(pg_dsn)
    raw = body(total=1)
    digest = hashlib.sha256(raw).hexdigest()
    original = kimdis._contract

    def poisoned(value: object, evidence: kimdis.Evidence) -> kimdis.Contract:
        result = original(value, evidence)
        if fault == "type":
            return replace(result, bidder_count=True)
        return replace(result, evidence=replace(evidence, json_pointer="/content/999"))

    monkeypatch.setattr(kimdis, "_contract", poisoned)
    with pytest.raises(kimdis.InvalidRecord, match="^normalized_contract$"):
        store.commit_page(run, raw, observed_at=datetime.now(UTC))
    assert state(pg_dsn) == before
    assert (archive.root / "objects" / digest[:2] / (digest + ".body")).read_bytes() == raw
    monkeypatch.setattr(kimdis, "_contract", original)
    assert store.commit_page(run, raw, observed_at=datetime.now(UTC))
    assert not store.commit_page(run, raw, observed_at=datetime.now(UTC))
    with psycopg.connect(pg_dsn) as db:
        assert db.execute("SELECT next_page FROM nima.ingest_runs").fetchone() == (1,)
        for name in ("run_pages", "record_versions", "observations", "outbox"):
            assert db.execute(
                sql.SQL("SELECT count(*) FROM nima.{}").format(sql.Identifier(name))
            ).fetchone() == (1,)
        assert db.execute("SELECT count(*) FROM nima.quarantine").fetchone() == (0,)


def test_source_bad_items_remain_quarantined_with_original_indices() -> None:
    raw = page_body(42, {"title": "Missing ID"}, record())
    page = kimdis.normalize_page(raw)
    assert len(page.issues) == 2 and len(page.contracts) == 1
    assert page.contracts[0].evidence.json_pointer == "/content/2"
    assert page.record_count == len(page.issues) + len(page.contracts) == 3


@pytest.mark.parametrize("boundary", ["source", "normalized"])
def test_changed_packaged_policy_is_not_misreported_as_a_source_issue(
    boundary: gates.Boundary, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = gates.policy

    def changed(selected: gates.Boundary) -> dict[str, str]:
        result = original(selected)
        if selected == boundary:
            result["normalizer_version"] = "unreviewed-version"
        return result

    gates._compiled.cache_clear()
    monkeypatch.setattr(gates, "policy", changed)
    try:
        with pytest.raises(kimdis.InvalidRecord, match=f"^{boundary}_contract$"):
            kimdis.normalize_page(body(total=1))
    finally:
        gates._compiled.cache_clear()


def test_unknown_raw_fields_still_change_version_hash_without_changing_normalized_value() -> None:
    raw = body(total=1)
    extra = json.loads(raw)
    extra["content"][0]["new_unprojected_field"] = {"reported": "retained"}
    original = kimdis.normalize_page(raw)
    changed = kimdis.normalize_page(json.dumps(extra).encode())
    assert original.record_hashes != changed.record_hashes
    assert (
        replace(original.contracts[0], evidence=changed.contracts[0].evidence)
        == changed.contracts[0]
    )


def test_single_record_entry_point_rejects_producer_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    original = kimdis._contract

    def poisoned(value: object, evidence: kimdis.Evidence) -> kimdis.Contract:
        return replace(original(value, evidence), bidder_count=True)

    monkeypatch.setattr(kimdis, "_contract", poisoned)
    with pytest.raises(kimdis.InvalidRecord, match="^normalized_contract$"):
        kimdis.normalize_contract(source_page())


def test_collector_reports_failure_without_misclassifying_producer_as_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = kimdis._contract
    raw = body(total=1)

    def poisoned(value: object, evidence: kimdis.Evidence) -> kimdis.Contract:
        return replace(original(value, evidence), bidder_count=True)

    monkeypatch.setattr(kimdis, "_contract", poisoned)
    archive = Archive(tmp_path / "archive")
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw))
    ) as c:
        result = collect(QUERY, Limits(), archive, client=c, clock=Clock())
    assert result.status == "failed" and result.failure == "invalid_page"
    assert result.normalized == result.quarantined == 0
    digest = hashlib.sha256(raw).hexdigest()
    assert (archive.root / "objects" / digest[:2] / (digest + ".body")).read_bytes() == raw
