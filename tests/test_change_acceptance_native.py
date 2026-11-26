"""Real capture counter refusals, private publication, retry and relocation."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from nima.analytics.change_readout import prepare_change_result
from nima.dataops import cli
from nima.dataops.change_acceptance import ChangeAcceptanceError, export_change_acceptance
from tests.change_acceptance_samples import request_file
from tests.test_analytics_snapshot import reader, state
from tests.test_change_readout import admin, day, request_for, two_captures
from tests.test_citation_acceptance import subject
from tests.test_citation_cohort import tamper
from tests.test_graph_pilot_archive import state as file_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("U4 acceptance attempted HTTP")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def test_complete_empty_captures_require_their_original_pages(pg_dsn: str, tmp_path: Path) -> None:
    from uuid import uuid4

    from nima.ingestion.archive import Archive
    from nima.ingestion.config import Limits, Summary
    from nima.storage.postgres import migrate
    from nima.storage.runs import RunStore
    from tests.test_collection import QUERY

    migrate(pg_dsn)
    captures = []
    for n in (1, 2):
        run = uuid4()
        root = tmp_path / str(n)
        store = RunStore(pg_dsn, Archive(root), run, Limits())
        raw = json.dumps(
            dict(content=[], number=0, size=1, totalElements=0, totalPages=0, last=True)
        ).encode()
        with store.lease():
            store.begin(QUERY)
            store.commit_page(run, raw, observed_at=day(n), owner=store.owner)
            store.finish(Summary(status="complete"))
        captures.append((run, root))
    request = request_for([captures[0]], [captures[1]])
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        report = subject(tmp_path / "reports", prepare_change_result(dsn, request).body)
        result = export_change_acceptance(dsn, selection, report, tmp_path / "output")
    payload = json.loads((tmp_path / "output" / (result.artifact_sha256 + ".json")).read_bytes())
    assert result.decision == "ready"
    assert {c["name"]: c["value"] for c in payload["assessment"]["counts"]} == dict(
        observations=0,
        pages=2,
        page_records=0,
        quarantined=0,
        selected_records=0,
        ambiguous_records=0,
    )


def test_native_export_cli_retry_relocation_and_removed_original(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = two_captures(pg_dsn, tmp_path / "raw")
    path = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        report = subject(tmp_path / "reports", prepare_change_result(dsn, request).body)
        before = state(pg_dsn)
        inputs = file_state(tmp_path / "raw"), file_state(tmp_path / "reports"), path.read_bytes()
        output = tmp_path / "output"
        first = export_change_acceptance(dsn, path, report, output)
        artifact = output / (first.artifact_sha256 + ".json")
        saved = artifact.read_bytes(), artifact.stat().st_mtime_ns
        assert export_change_acceptance(dsn, path, report, output) == first
        assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == saved
        assert output.stat().st_mode & 0o777 == 0o700
        assert artifact.stat().st_mode & 0o777 == 0o600
        moved = tmp_path / "relocated"
        shutil.copytree(tmp_path / "raw", moved)
        relocated = replace(
            request,
            archive_bindings=tuple(
                replace(b, root=moved / b.root.name) for b in request.archive_bindings
            ),
        )
        from nima.dataops.change_acceptance import prepare_change_acceptance

        assert prepare_change_acceptance(dsn, relocated, report).body == saved[0]
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            cli.run(
                [
                    "assess-changes",
                    "--request",
                    str(path),
                    "--report",
                    str(report),
                    "--output-dir",
                    str(output),
                ]
            )
            == 0
        )
        out = capsys.readouterr()
        assert json.loads(out.out)["artifact_sha256"] == first.artifact_sha256
        assert dsn not in out.out + out.err and str(tmp_path) not in out.out + out.err
        assert (
            file_state(tmp_path / "raw"),
            file_state(tmp_path / "reports"),
            path.read_bytes(),
        ) == inputs
        next((tmp_path / "raw").rglob("*.body")).unlink()
        unchanged = file_state(output)
        with pytest.raises(ChangeAcceptanceError, match="^acceptance_evidence$"):
            export_change_acceptance(dsn, path, report, output)
        assert file_state(output) == unchanged
    assert state(pg_dsn) == before


@pytest.mark.parametrize(
    "fault", ["raw", "missing", "normalized", "membership", "page", "projection", "owner"]
)
def test_native_failed_proof_cannot_publish(pg_dsn: str, tmp_path: Path, fault: str) -> None:
    request = two_captures(pg_dsn, tmp_path / "raw")
    path = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        report = subject(tmp_path / "reports", prepare_change_result(dsn, request).body)
        original = next((tmp_path / "raw").rglob("*.body"))
        if fault == "raw":
            original.write_bytes(b"corrupt")
        elif fault == "missing":
            original.unlink()
        elif fault == "normalized":
            tamper(pg_dsn, "UPDATE nima.record_versions SET normalized='{}'")
        elif fault == "membership":
            tamper(pg_dsn, "UPDATE nima.observations SET record_index=9 WHERE record_index=0")
        elif fault == "page":
            tamper(pg_dsn, "UPDATE nima.run_pages SET record_count=9")
        elif fault == "projection":
            tamper(pg_dsn, "DELETE FROM nima.projection_receipts")
        before, files = state(pg_dsn), file_state(tmp_path)
        with pytest.raises(
            ChangeAcceptanceError,
            match="^acceptance_database$" if fault == "owner" else "^acceptance_evidence$",
        ):
            export_change_acceptance(
                pg_dsn if fault == "owner" else dsn, path, report, tmp_path / "output"
            )
        assert not (tmp_path / "output").exists()
        assert state(pg_dsn) == before and file_state(tmp_path) == files


@pytest.mark.parametrize(
    "reason",
    ["run_incomplete", "query_mismatch", "not_later", "quarantined_records", "no_runs", "all"],
)
def test_actual_incomparable_can_publish_blocked_without_originals(
    pg_dsn: str,
    tmp_path: Path,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = two_captures(pg_dsn, tmp_path / "raw")
    if reason in {"run_incomplete", "all"}:
        admin(
            pg_dsn,
            "UPDATE nima.ingest_runs SET status='failed' WHERE run_id=%s",
            request.later_run_ids[0],
        )
    if reason in {"query_mismatch", "all"}:
        admin(
            pg_dsn,
            'UPDATE nima.ingest_runs SET query=query || \'{"dateTo":"2026-11-07"}\'::jsonb '
            "WHERE run_id=%s",
            request.later_run_ids[0],
        )
    if reason in {"quarantined_records", "all"}:
        admin(
            pg_dsn,
            "INSERT INTO nima.quarantine (run_id,page_number,record_index,reason) "
            "VALUES (%s,0,99,'synthetic')",
            request.earlier_run_ids[0],
        )
    if reason in {"not_later", "all"}:
        request = replace(
            request, earlier_run_ids=request.later_run_ids, later_run_ids=request.earlier_run_ids
        )
    if reason == "no_runs":
        request = replace(
            request,
            earlier_run_ids=(),
            archive_bindings=tuple(
                b for b in request.archive_bindings if b.run_id in request.later_run_ids
            ),
        )
    for p in (tmp_path / "raw").rglob("*.body"):
        p.unlink()
    path = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        report = subject(tmp_path / "reports", prepare_change_result(dsn, request).body)
        before, files = state(pg_dsn), file_state(tmp_path / "raw")
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            cli.run(
                [
                    "assess-changes",
                    "--request",
                    str(path),
                    "--report",
                    str(report),
                    "--output-dir",
                    str(tmp_path / "output"),
                ]
            )
            == 3
        )
        summary = json.loads(capsys.readouterr().out)
        payload = json.loads(
            (tmp_path / "output" / (summary["artifact_sha256"] + ".json")).read_bytes()
        )
        assert payload["assessment"]["status"] == "blocked"
        assert payload["subject"]["verification_scope"] == "sql_comparability_only"
        assert payload["assessment"]["cohort_sha256"] is None
        assert payload["subject"]["run_profiles"] == []
        assert payload["assessment"]["counts"] == [
            {
                "name": "quarantined",
                "grain": "quarantined_record",
                "value": int(reason in {"quarantined_records", "all"}),
            }
        ]
        if reason == "all":
            assert payload["subject"]["reasons"] == [
                "not_later",
                "quarantined_records",
                "query_mismatch",
                "run_incomplete",
            ]
        else:
            assert reason in payload["subject"]["reasons"]
        assert state(pg_dsn) == before and file_state(tmp_path / "raw") == files
