"""Actual U2 archives and projections, restricted SQL, refusal and publication."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from nima.analytics import snapshot as sessions
from nima.analytics.cpv_readout import prepare_cpv_result
from nima.analytics.cpv_request import CpvRequest
from nima.dataops import cli
from nima.dataops.cpv_acceptance import (
    CpvAcceptanceError,
    export_cpv_acceptance,
    prepare_cpv_acceptance,
)
from nima.graph.pilot_archive import ArchiveBinding
from nima.identity.artifacts import encode
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.storage.connection import connect
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.cpv_acceptance_samples import CUTOFF, request_file
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_acceptance import subject
from tests.test_citation_cohort import tamper
from tests.test_collection import QUERY, body
from tests.test_cpv_readout import body_path, request_for, seed
from tests.test_graph_pilot_archive import state as file_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("U2 acceptance attempted HTTP")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def test_complete_empty_has_its_original_page(pg_dsn: str, tmp_path: Path) -> None:
    from tests.test_analytics_reconcile import captured

    saved, _ = captured(pg_dsn, tmp_path / "raw", empty=True)
    request = CpvRequest(saved.run_ids, CUTOFF, saved.archive_bindings)
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_cpv_result(dsn, request)
        prepared = prepare_cpv_acceptance(dsn, request, subject(tmp_path / "reports", fresh.body))
    assert prepared.assessment.status == "ready"
    assert prepared.assessment.provider_status == "empty_capture"
    counts = {c.name: c.value for c in prepared.assessment.counts}
    assert counts["pages"] == 1 and counts["observations"] == counts["page_records"] == 0


def test_export_cli_retry_and_relocation_reverify_once_without_source_changes(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "raw"
    request = request_for(seed(pg_dsn, root), root)
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_cpv_result(dsn, request)
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
        first = export_cpv_acceptance(dsn, selection, report, output)
        assert calls == 2
        artifact = output / (first.artifact_sha256 + ".json")
        stable = artifact.read_bytes(), artifact.stat().st_mtime_ns
        assert export_cpv_acceptance(dsn, selection, report, output) == first
        assert calls == 4 and (artifact.read_bytes(), artifact.stat().st_mtime_ns) == stable
        moved = tmp_path / "relocated"
        shutil.copytree(tmp_path / "raw", moved)
        relocated = replace(
            request, archive_bindings=(replace(request.archive_bindings[0], root=moved),)
        )
        assert prepare_cpv_acceptance(dsn, relocated, report).body == stable[0]
        assert calls == 6
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            cli.run(
                [
                    "assess-cpv",
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
        with pytest.raises(CpvAcceptanceError, match="^acceptance_evidence$"):
            export_cpv_acceptance(dsn, selection, report, output)
        assert calls == 9 and file_state(output) == output_state
    assert state(pg_dsn) == before


@pytest.mark.parametrize(
    "fault", ["raw", "missing", "normalized", "membership", "page", "projection", "owner"]
)
def test_failed_actual_proof_never_publishes(pg_dsn: str, tmp_path: Path, fault: str) -> None:
    root = tmp_path / "raw"
    request = request_for(seed(pg_dsn, root), root)
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_cpv_result(dsn, request)
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
        with pytest.raises(CpvAcceptanceError, match=f"^{expected}$"):
            export_cpv_acceptance(
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
    request = CpvRequest((run,), CUTOFF, (ArchiveBinding("kimdis", run, root),))
    selection = request_file(request, tmp_path / "request.json")
    # No U2 report can exist for this cohort. An untrusted cached flag is never proof.
    report = subject(tmp_path / "reports", encode({"verified": True, "status": "ready"}))
    before, files = state(pg_dsn), file_state(tmp_path)
    with (
        reader(pg_dsn) as (dsn, _),
        pytest.raises(CpvAcceptanceError, match="^acceptance_evidence$"),
    ):
        export_cpv_acceptance(dsn, selection, report, tmp_path / "output")
    assert state(pg_dsn) == before and file_state(tmp_path) == files


@pytest.mark.parametrize(
    "selection",
    [{}, {"cpv_base_code": "99999999"}, {"period_from": "2026-05", "period_to": "2026-05"}],
)
def test_native_overlaps_reobservations_ties_and_filters_have_hand_computed_counts(
    pg_dsn: str, tmp_path: Path, selection: dict[str, str]
) -> None:
    from datetime import UTC, datetime

    from tests.test_cpv_readout import multi_request, record

    def row(
        name: str, date: str | None, codes: list[str] | None, cancelled: bool | None
    ) -> dict[str, Any]:
        return {**record(name, date, codes), "cancelled": cancelled}

    date = "2026-03-10T08:00:00.123"
    first = row("A", date, ["45000000-7"], False)
    original = [
        first,
        row("B", date, ["45000000-7", "45100000-8"], True),
        row("C", date, None, None),
        row("D", "not a date", ["45000000-7"], False),
    ]
    batches = [
        (original, datetime(2026, 1, 1, tzinfo=UTC)),
        ([first], datetime(2026, 1, 2, tzinfo=UTC)),
        ([row("TIE", None, None, None)], datetime(2026, 1, 3, tzinfo=UTC)),
        ([row("TIE", None, ["45000000-7"], None)], datetime(2026, 1, 3, tzinfo=UTC)),
        ([row("FUTURE", date, ["45000000-7"], False)], datetime(2026, 7, 1, tzinfo=UTC)),
    ]
    pairs = []
    for i, (rows, observed) in enumerate(batches):
        root = tmp_path / f"originals{i}"
        pairs.append((seed(pg_dsn, root, rows, observed), root))
    request = replace(
        multi_request(pairs, CUTOFF.isoformat()),
        cpv_base_code=selection.get("cpv_base_code"),
        period_from=selection.get("period_from"),
        period_to=selection.get("period_to"),
    )
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_cpv_result(dsn, request)
        report = subject(tmp_path / "reports", fresh.body)
        result = prepare_cpv_acceptance(dsn, request, report)
    assert {c.name: c.value for c in result.assessment.counts} == {
        "observations": 8,
        "pages": 5,
        "page_records": 8,
        "quarantined": 0,
        "selected_records": 4,
        "ambiguous_records": 1,
        "unknown_dates": 1,
        "unclassified_cpv": 1,
        "unknown_cancellations": 1,
        "cancelled_records": 1,
    }
    assert result.assessment.status == "limited"
    assert result.assessment.provider_status == (
        "selection_unresolved" if selection else "observed_activity"
    )
    assert sum(c.record_count for c in fresh.metric.cells) == (0 if selection else 5)
    assert sum(c.cancelled_count for c in fresh.metric.cells) == (0 if selection else 2)
    assert state(pg_dsn) == before
