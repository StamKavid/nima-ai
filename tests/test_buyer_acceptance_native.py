"""Actual U3 archives and projections, restricted SQL, refusal and publication."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from nima.analytics import snapshot as sessions
from nima.analytics.buyer_readout import prepare_buyer_result
from nima.analytics.buyer_request import BuyerRequest
from nima.dataops import cli
from nima.dataops.buyer_acceptance import (
    BuyerAcceptanceError,
    export_buyer_acceptance,
    prepare_buyer_acceptance,
)
from nima.graph.pilot_archive import ArchiveBinding
from nima.identity.artifacts import encode
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.storage.connection import connect
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.buyer_acceptance_samples import request_file
from tests.test_analytics_snapshot import reader, state
from tests.test_buyer_concentration import CUTOFF
from tests.test_buyer_readout import RECORDS, body_path, request_for
from tests.test_citation_acceptance import subject
from tests.test_citation_cohort import tamper
from tests.test_collection import QUERY, body
from tests.test_cpv_readout import seed
from tests.test_graph_pilot_archive import state as file_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("U3 acceptance attempted HTTP")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def test_complete_empty_has_its_original_page(pg_dsn: str, tmp_path: Path) -> None:
    from tests.test_analytics_reconcile import captured

    saved, _ = captured(pg_dsn, tmp_path / "raw", empty=True)
    request = BuyerRequest(saved.run_ids, CUTOFF, "B1", saved.archive_bindings)
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_buyer_result(dsn, request)
        prepared = prepare_buyer_acceptance(dsn, request, subject(tmp_path / "reports", fresh.body))
    assert prepared.assessment.status == "ready"
    assert prepared.assessment.provider_status == "empty_capture"
    counts = {c.name: c.value for c in prepared.assessment.counts}
    assert counts["pages"] == 1 and counts["observations"] == counts["page_records"] == 0


def test_export_cli_retry_and_relocation_reverify_once_without_source_changes(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "raw"
    request = request_for(seed(pg_dsn, root, RECORDS), root)
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_buyer_result(dsn, request)
        report = subject(tmp_path / "reports", fresh.body)
        before = state(pg_dsn)
        raw, report_files = file_state(tmp_path / "raw"), file_state(tmp_path / "reports")
        request_stat = selection.stat()
        calls = 0

        def counted(value: str) -> Any:
            nonlocal calls
            calls += 1
            return connect(value)

        monkeypatch.setattr(sessions, "connect", counted)
        output = tmp_path / "output"
        first = export_buyer_acceptance(dsn, selection, report, output)
        assert calls == 2
        artifact = output / (first.artifact_sha256 + ".json")
        stable = artifact.read_bytes(), artifact.stat().st_mtime_ns
        assert export_buyer_acceptance(dsn, selection, report, output) == first
        assert calls == 4 and (artifact.read_bytes(), artifact.stat().st_mtime_ns) == stable
        moved = tmp_path / "relocated"
        shutil.copytree(tmp_path / "raw", moved)
        relocated = replace(
            request, archive_bindings=(replace(request.archive_bindings[0], root=moved),)
        )
        assert prepare_buyer_acceptance(dsn, relocated, report).body == stable[0]
        assert calls == 6
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            cli.run(
                [
                    "assess-buyer",
                    "--request",
                    str(selection),
                    "--report",
                    str(report),
                    "--output-dir",
                    str(output),
                ]
            )
            == 0
        )
        assert calls == 8
        out = capsys.readouterr()
        assert json.loads(out.out)["artifact_sha256"] == first.artifact_sha256
        assert dsn not in out.out + out.err and str(tmp_path) not in out.out + out.err
        assert len(artifact.read_bytes()) <= 64 * 1024 and b"012345678" not in artifact.read_bytes()
        assert artifact.stat().st_mode & 0o777 == 0o600 and output.stat().st_mode & 0o777 == 0o700
        assert (
            file_state(tmp_path / "raw") == raw and file_state(tmp_path / "reports") == report_files
        )
        assert selection.stat().st_mtime_ns == request_stat.st_mtime_ns
        original_file = body_path(request, pg_dsn)
        original_file.unlink()
        output_state = file_state(output)
        with pytest.raises(BuyerAcceptanceError, match="^acceptance_evidence$"):
            export_buyer_acceptance(dsn, selection, report, output)
        assert calls == 9 and file_state(output) == output_state
    assert state(pg_dsn) == before


@pytest.mark.parametrize(
    "fault", ["raw", "missing", "normalized", "membership", "page", "projection", "owner"]
)
def test_failed_actual_proof_never_publishes(pg_dsn: str, tmp_path: Path, fault: str) -> None:
    root = tmp_path / "raw"
    request = request_for(seed(pg_dsn, root, RECORDS), root)
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_buyer_result(dsn, request)
        report = subject(tmp_path / "reports", fresh.body)
        if fault == "raw":
            body_path(request, pg_dsn).write_bytes(b"corrupt")
        elif fault == "missing":
            body_path(request, pg_dsn).unlink()
        elif fault == "normalized":
            tamper(pg_dsn, "UPDATE nima.record_versions SET normalized='{}'")
        elif fault == "membership":
            tamper(pg_dsn, "UPDATE nima.observations SET record_index=9 WHERE record_index=0")
        elif fault == "page":
            tamper(pg_dsn, "UPDATE nima.run_pages SET record_count=9")
        elif fault == "projection":
            tamper(pg_dsn, "DELETE FROM nima.projection_receipts")
        before, files = state(pg_dsn), file_state(tmp_path)
        expected = "acceptance_database" if fault == "owner" else "acceptance_evidence"
        with pytest.raises(BuyerAcceptanceError, match=f"^{expected}$"):
            export_buyer_acceptance(
                pg_dsn if fault == "owner" else dsn, selection, report, tmp_path / "output"
            )
        assert not (tmp_path / "output").exists()
        assert state(pg_dsn) == before and file_state(tmp_path) == files


@pytest.mark.parametrize("kind", ["partial", "quarantined", "no_pages"])
def test_strict_numeric_boundary_refuses_real_incomplete_runs(
    pg_dsn: str, tmp_path: Path, kind: str
) -> None:
    migrate(pg_dsn)
    run = uuid4()
    root = tmp_path / "raw"
    store = RunStore(pg_dsn, Archive(root), run, Limits())
    with store.lease():
        store.begin(QUERY)
        if kind != "no_pages":
            raw = body(total=2 if kind == "partial" else 1)
            if kind == "quarantined":
                value = json.loads(raw)
                value["content"] = [None]
                raw = encode(value)
            store.commit_page(run, raw, observed_at=CUTOFF, owner=store.owner)
        store.finish(
            Summary(
                status="interrupted"
                if kind == "partial"
                else "quarantined"
                if kind == "quarantined"
                else "failed"
            )
        )
    request = BuyerRequest((run,), CUTOFF, "B1", (ArchiveBinding("kimdis", run, root),))
    selection = request_file(request, tmp_path / "request.json")
    # No U3 report can exist for this cohort. An untrusted cached flag is never proof.
    report = subject(tmp_path / "reports", encode({"verified": True, "status": "ready"}))
    before, files = state(pg_dsn), file_state(tmp_path)
    with (
        reader(pg_dsn) as (dsn, _),
        pytest.raises(BuyerAcceptanceError, match="^acceptance_evidence$"),
    ):
        export_buyer_acceptance(dsn, selection, report, tmp_path / "output")
    assert state(pg_dsn) == before and file_state(tmp_path) == files


@pytest.mark.parametrize("buyer", ["B1", "B2", "MISSING"])
def test_native_sparse_evidence_and_joint_unresolved_counts_match_by_hand(
    pg_dsn: str, tmp_path: Path, buyer: str
) -> None:
    from datetime import UTC, datetime

    from tests.test_buyer_readout import S1, S2, multi_request, record

    def day(n: int) -> datetime:
        return datetime(2026, 1, n, tzinfo=UTC)

    def row(
        name: str, key: str | None, taxes: list[str] | None, cancelled: bool | None
    ) -> dict[str, Any]:
        value = record(name, key or "", taxes)
        if key is None:
            value.pop("organization")
        return {**value, "cancelled": cancelled}

    first = row("R1", "B1", [S1], False)
    partial = row("P", "B1", [S1, "000000000", "234567891"], False)
    partial["contractingDataDetails"]["contractingMembersDataList"][2]["country"]["key"] = "DE"
    original = [
        first,
        row("R2", "B1", [S1, S2], True),
        row("R3", "B1", [S2], False),
        row("R4", "B1", None, None),
        row("R5", "B1", ["bad"], False),
        partial,
        row("Q", "B2", [S2], False),
        row("U", None, [S1], False),
    ]
    batches = [
        (original, day(1)),
        ([row("T", "B2", None, None)], day(2)),
        ([row("T", "B2", [S2], None)], day(2)),
        ([first], day(3)),
        ([row("F", "B1", [S1], False)], day(11)),
        ([row("R1", "B1", [S1], True)], day(12)),
    ]
    pairs = []
    for i, (rows, observed) in enumerate(batches):
        root = tmp_path / f"originals{i}"
        pairs.append((seed(pg_dsn, root, rows, observed), root))
    request = replace(multi_request(pairs, CUTOFF.isoformat()), buyer=buyer)
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_buyer_result(dsn, request)
        original = json.loads(fresh.body)
        result = prepare_buyer_acceptance(dsn, request, subject(tmp_path / "reports", fresh.body))
    expected = {
        "observations": 13,
        "pages": 6,
        "page_records": 13,
        "quarantined": 0,
        "selected_records": 8,
        "ambiguous_records": 1,
        "buyer_records": 6,
        "resolved_records": 4,
        "unresolved_suppliers": 2,
        "partial_suppliers": 1,
        "joint_records": 1,
        "supplier_participations": 5,
        "unknown_cancellations": 1,
        "cancelled_records": 1,
    }
    if buyer != "B1":
        expected.update(
            buyer_records=int(buyer == "B2"),
            resolved_records=int(buyer == "B2"),
            unresolved_suppliers=0,
            partial_suppliers=0,
            joint_records=0,
            supplier_participations=int(buyer == "B2"),
            unknown_cancellations=0,
            cancelled_records=0,
        )
    assert {c.name: c.value for c in result.assessment.counts} == expected
    assert result.assessment.status == "limited"
    assert result.assessment.provider_status == (
        "selection_unresolved" if buyer == "MISSING" else "observed_concentration"
    )
    assert len(original["evidence"]) == {"B1": 10, "B2": 3, "MISSING": 2}[buyer]
    if buyer == "B1":
        assert original["metric"]["result"]["top_share"] == {"numerator": 3, "denominator": 4}
        assert original["metric"]["result"]["unresolved_share"] == {
            "numerator": 2,
            "denominator": 6,
        }
        assert sum(s.cancelled_count for s in fresh.metric.suppliers) == 2
        assert (
            sum(
                r.ineligible_occurrences
                for r in fresh.metric.records
                if r.source_id in fresh.metric.partial_source_ids
            )
            == 2
        )
    assert state(pg_dsn) == before
