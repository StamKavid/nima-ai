"""Re-derive a frozen cohort from real private original bytes, without SQL writes."""

import hashlib
import json
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never, cast
from uuid import uuid4

import psycopg
import pytest

from nima.analytics.reconcile import ReconciliationError, reconcile
from nima.analytics.request import ReadoutRequest, decode_request
from nima.analytics.snapshot import ReadoutSnapshot, read_snapshot, validate_snapshot
from nima.graph.pilot_archive import (
    ArchiveBinding,
    ArchiveRecovery,
    RawReference,
    RecoveryLimits,
    recover,
)
from nima.identity.artifacts import encode
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.projections.contracts import project_contract
from nima.projections.worker import drain
from nima.semantics.participation import Observation, definition_sha256, evaluate
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.test_analytics_snapshot import reader, seed, state
from tests.test_collection import QUERY
from tests.test_semantics import CUTOFF, TAX


def captured(
    dsn: str, root: Path, *, empty: bool = False
) -> tuple[ReadoutRequest, ReadoutSnapshot]:
    run = seed(dsn, root, empty=empty)
    request = decode_request(
        json.dumps(
            {
                "version": "nima-participation-request-v1",
                "source": "kimdis.contract",
                "run_ids": [str(run)],
                "observation_cutoff": CUTOFF.isoformat(),
                "supplier_country": "GR",
                "supplier_tax_id": TAX,
                "archive_bindings": [{"run_id": str(run), "root": str(root)}],
            }
        ).encode()
    )
    with reader(dsn) as (limited, _):
        snapshot = read_snapshot(limited, (run,), tax_id=TAX, cutoff=CUTOFF)
    return request, snapshot


def body_path(request: ReadoutRequest, snapshot: ReadoutSnapshot) -> Path:
    digest = cast(str, json.loads(snapshot.document_json)["pages"][0]["raw_sha256"])
    return request.archive_bindings[0].root / "objects" / digest[:2] / (digest + ".body")


def test_reconciles_originals_and_preserves_database_and_files(pg_dsn: str, tmp_path: Path) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    before = state(pg_dsn)
    body = body_path(request, snapshot).read_bytes()
    verified = reconcile(snapshot, request)
    assert verified.snapshot == snapshot
    assert verified.request_sha256 == request.request_sha256
    assert len(verified.pages) == 1
    assert (
        verified.pages[0].raw_sha256 == json.loads(snapshot.document_json)["pages"][0]["raw_sha256"]
    )
    assert verified.snapshot.metric.total == 1
    assert state(pg_dsn) == before
    assert body_path(request, snapshot).read_bytes() == body


def seed_cohort(dsn: str, root: Path) -> ReadoutRequest:
    """Synthetic known-answer input shared by byte verification and report tests."""
    fixture = json.loads(Path("tests/fixtures/participation.json").read_text())
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    seen: dict[tuple[int, str], int] = {}
    for row in fixture["observations"]:
        key = row["day"], row["record"]
        count = seen.get(key, 0)
        seen[key] = count + 1
        groups.setdefault((row["day"], count), []).append(row)
    migrate(dsn)
    bindings = []
    for (day, _), rows in sorted(groups.items()):
        run = uuid4()
        archive = root / str(run)
        store = RunStore(dsn, Archive(archive), run, Limits())
        content = [
            {
                "referenceNumber": row["record"],
                "title": "Συνθετική δημοσίευση",
                "organization": None
                if row["buyer"] is None
                else {"key": row["buyer"], "value": "Συνθετικός αγοραστής"},
                "cancelled": row["cancelled"],
                "contractingDataDetails": {
                    "contractingMembersDataList": [
                        {"vatNumber": tax, "country": None if country is None else {"key": country}}
                        for tax, country in row["suppliers"]
                    ]
                },
            }
            for row in rows
        ]
        raw = json.dumps(
            {
                "content": content,
                "number": 0,
                "size": len(rows),
                "totalElements": len(rows),
                "totalPages": 1,
                "last": True,
            }
        ).encode()
        with store.lease():
            store.begin(QUERY)
            store.commit_page(
                run, raw, observed_at=datetime(2026, 1, day, tzinfo=UTC), owner=store.owner
            )
            store.finish(Summary(status="complete"))
        drain(dsn, run_id=run)
        bindings.append({"run_id": str(run), "root": str(archive)})
    return decode_request(
        json.dumps(
            {
                "version": "nima-participation-request-v1",
                "source": "kimdis.contract",
                "run_ids": [binding["run_id"] for binding in bindings],
                "observation_cutoff": CUTOFF.isoformat(),
                "supplier_country": "GR",
                "supplier_tax_id": TAX,
                "archive_bindings": bindings,
            }
        ).encode()
    )


def test_known_cohort_reconciles_all_pages_and_revisions(pg_dsn: str, tmp_path: Path) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "cohort")
    with reader(pg_dsn) as (dsn, _):
        snapshot = read_snapshot(dsn, request.run_ids, tax_id=TAX, cutoff=CUTOFF)
    verified = reconcile(snapshot, request)
    assert len(verified.pages) == 4
    assert sum(page.record_count for page in verified.pages) == 11
    assert verified.snapshot.metric.total == 5
    assert [(row.buyer_key, row.record_count) for row in snapshot.metric.buyers] == [
        ("kimdis.buyer-key:B1", 3),
        ("kimdis.buyer-key:B2", 1),
    ]
    assert verified.snapshot.metric.ambiguous_source_ids == ("kimdis:G",)


def test_empty_capture_requires_original_page(pg_dsn: str, tmp_path: Path) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive", empty=True)
    assert reconcile(snapshot, request).snapshot.metric.status == "empty_capture"
    body_path(request, snapshot).unlink()
    with pytest.raises(ReconciliationError, match="^analytics_archive$"):
        reconcile(snapshot, request)


def test_corruption_and_oversized_objects_are_refused(pg_dsn: str, tmp_path: Path) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    path = body_path(request, snapshot)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ReconciliationError, match="^analytics_archive$"):
        reconcile(snapshot, request)
    with path.open("r+b") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    with pytest.raises(ReconciliationError, match="^analytics_limit$"):
        reconcile(snapshot, request)


def test_request_and_snapshot_cannot_be_swapped(pg_dsn: str, tmp_path: Path) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    with pytest.raises(ReconciliationError, match="^analytics_evidence$"):
        reconcile(snapshot, replace(request, supplier_tax_id="987654321"))


def refreeze(
    snapshot: ReadoutSnapshot,
    request: ReadoutRequest,
    document: dict[str, Any],
    observations: tuple[Observation, ...] | None = None,
) -> ReadoutSnapshot:
    rows = snapshot.observations if observations is None else observations
    metric = evaluate(rows, tax_id=request.supplier_tax_id, cutoff=request.observation_cutoff)
    identity = {
        "document": document,
        "run_ids": [str(run) for run in request.run_ids],
        "tax_id": request.supplier_tax_id,
        "country": "GR",
        "cutoff": request.observation_cutoff.isoformat(),
        "definition_sha256": definition_sha256(),
    }
    return ReadoutSnapshot(
        encode(document).decode(), rows, metric, hashlib.sha256(encode(identity)).hexdigest()
    )


@pytest.mark.parametrize(
    "kind",
    [
        "record_hash",
        "normalized",
        "page_size",
        "byte_length",
        "bad_page_json",
        "record_index",
        "page_number",
    ],
)
def test_internally_consistent_sql_cannot_override_original_bytes(
    pg_dsn: str,
    tmp_path: Path,
    kind: str,
) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    document = json.loads(snapshot.document_json)
    record = document["records"][0]
    observations = snapshot.observations
    if kind == "record_hash":
        record["content_sha256"] = "f" * 64
        record["projection"]["content_sha256"] = "f" * 64
        for mention in record["mentions"]:
            mention["content_sha256"] = "f" * 64
        observations = (replace(observations[0], content_sha256="f" * 64),)
    elif kind == "normalized":
        record["normalized"]["title"] = "A different title"
        record["projection"]["title"] = "A different title"
        record["projection"]["projection_sha256"] = project_contract(record["normalized"]).digest()
    elif kind == "page_size":
        document["runs"][0]["page_size"] = 2
    elif kind == "byte_length":
        document["pages"][0]["byte_length"] += 1
    elif kind == "record_index":
        record["record_index"] = False
    elif kind == "page_number":
        document["pages"][0]["page_number"] = False
    else:
        digest = Archive(request.archive_bindings[0].root).store(b"{}")
        document["pages"][0].update(raw_sha256=digest, byte_length=2)
    forged = refreeze(snapshot, request, document, observations)
    assert validate_snapshot(forged, request.run_ids, tax_id=TAX, cutoff=CUTOFF) == document
    with pytest.raises(ReconciliationError, match="^analytics_evidence$"):
        reconcile(forged, request)


def test_relocation_preserves_verified_semantic_inputs(pg_dsn: str, tmp_path: Path) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    verified = reconcile(snapshot, request)
    moved = tmp_path / "μεταφορά"
    request.archive_bindings[0].root.rename(moved)
    relocated = replace(
        request, archive_bindings=(replace(request.archive_bindings[0], root=moved),)
    )
    assert reconcile(snapshot, relocated) == verified


def test_reconciliation_does_not_reopen_sql_initialize_or_fetch(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")

    def forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("unexpected SQL/source/archive initialization")

    with monkeypatch.context() as patch:
        patch.setattr(psycopg, "connect", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        patch.setattr(Archive, "__init__", forbidden)
        assert reconcile(snapshot, request).snapshot.metric.total == 1


def test_recovery_total_budget_failure_is_not_repaired(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.analytics import reconcile as module

    request, snapshot = captured(pg_dsn, tmp_path / "archive")

    def bounded(
        refs: tuple[RawReference, ...], bindings: tuple[ArchiveBinding, ...]
    ) -> ArchiveRecovery:
        return recover(refs, bindings, limits=RecoveryLimits(max_total_bytes=1))

    monkeypatch.setattr(module, "recover", bounded)
    with pytest.raises(ReconciliationError, match="^analytics_limit$"):
        reconcile(snapshot, request)


@pytest.mark.parametrize("after_cutoff", [False, True])
def test_excluded_records_still_require_their_original_pages(
    pg_dsn: str,
    tmp_path: Path,
    after_cutoff: bool,
) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    changed = (
        replace(request, observation_cutoff=datetime(2025, 1, 1, tzinfo=UTC))
        if after_cutoff
        else replace(request, supplier_tax_id="987654321")
    )
    with reader(pg_dsn) as (dsn, _):
        selected = read_snapshot(
            dsn, changed.run_ids, tax_id=changed.supplier_tax_id, cutoff=changed.observation_cutoff
        )
    assert reconcile(selected, changed).snapshot.metric.total == 0
    body_path(request, snapshot).unlink()
    with pytest.raises(ReconciliationError, match="^analytics_archive$"):
        reconcile(selected, changed)


def test_cross_source_binding_is_rejected_before_archive_access(
    pg_dsn: str, tmp_path: Path
) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    changed = replace(
        request, archive_bindings=(replace(request.archive_bindings[0], source="gemi"),)
    )
    with pytest.raises(ReconciliationError, match="^analytics_input$"):
        reconcile(snapshot, changed)
