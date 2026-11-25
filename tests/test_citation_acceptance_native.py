"""Actual originals, restricted PostgreSQL reader and no writes on any outcome."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import snapshot as session
from nima.analytics.citation_readout import prepare_citation_readout
from nima.analytics.citation_request import CitationRequest
from nima.dataops import cli
from nima.dataops.citation_acceptance import (
    CitationAcceptanceError,
    export_citation_acceptance,
    prepare_citation_acceptance,
)
from nima.identity.artifacts import encode
from nima.storage.connection import connect
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_acceptance import subject
from tests.test_citation_cohort import seed, tamper
from tests.test_graph_pilot_archive import state as archive_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Citation acceptance must not request source data")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def request_file(root: Path, request: CitationRequest) -> Path:
    path = root / "request.json"
    path.write_bytes(
        encode(
            {
                **request.semantic_payload(),
                "archive_bindings": [
                    {"source": b.source, "run_id": str(b.run_id), "root": str(b.root)}
                    for b in request.archive_bindings
                ],
            }
        )
    )
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("option", ["complete", "empty", "partial", "quarantined", "no_pages"])
def test_real_capture_accounting(pg_dsn: str, tmp_path: Path, option: str) -> None:
    options = {} if option == "complete" else {option: True}
    request = seed(pg_dsn, tmp_path / "raw", **options)
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_citation_readout(dsn, request)
        report = subject(tmp_path / "reports", body)
        before, files = state(pg_dsn), archive_state(tmp_path)
        prepared = prepare_citation_acceptance(dsn, request, report)
    assessment = prepared.assessment
    counts = {c.name: c.value for c in assessment.counts}
    assert counts["pages"] == (1 if option == "no_pages" else 2)
    assert counts["observations"] == (1 if option in {"empty", "no_pages"} else 2)
    assert counts["quarantined"] == int(option == "quarantined")
    assert counts["page_records"] == counts["observations"] + counts["quarantined"]
    assert counts["unresolved_citations"] == int(option in {"empty", "no_pages"})
    assert assessment.status == ("ready" if option == "complete" else "limited")
    check = next(c for c in assessment.checks if c.check_id == "capture_completeness")
    assert check.reason == (
        "ok"
        if option in {"complete", "empty"}
        else "quarantined_records"
        if option == "quarantined"
        else "incomplete_capture"
    )
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == files


def test_no_admitted_pages_does_not_claim_verified_bytes(pg_dsn: str, tmp_path: Path) -> None:
    request = seed(pg_dsn, tmp_path / "raw", source_no_pages=True, no_pages=True)
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_citation_readout(dsn, request)
        prepared = prepare_citation_acceptance(dsn, request, subject(tmp_path / "reports", body))
    assert prepared.assessment.status == "limited"
    assert json.loads(prepared.body)["subject"]["raw_bytes"] == "no_admitted_pages"
    assert all(c.value == 0 for c in prepared.assessment.counts)


def test_export_retry_relocation_and_cli_reconstruct_once_per_call(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = seed(pg_dsn, tmp_path / "raw")
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_citation_readout(dsn, request)
        report = subject(tmp_path / "reports", body)
        request_path = request_file(tmp_path, request)
        before = state(pg_dsn)
        originals = archive_state(tmp_path)
        calls = 0

        def counted(value: str) -> Any:
            nonlocal calls
            calls += 1
            return connect(value)

        monkeypatch.setattr(session, "connect", counted)
        output = tmp_path / "output"
        first = export_citation_acceptance(dsn, request_path, report, output)
        assert calls == 1
        artifact = output / (first.artifact_sha256 + ".json")
        stable = {k: v for k, v in archive_state(output).items() if k != "."}
        assert export_citation_acceptance(dsn, request_path, report, output) == first
        assert calls == 2
        assert {k: v for k, v in archive_state(output).items() if k != "."} == stable
        shutil.copytree(tmp_path / "raw", tmp_path / "moved")
        moved = replace(
            request,
            archive_bindings=tuple(
                replace(b, root=tmp_path / "moved" / b.root.name) for b in request.archive_bindings
            ),
        )
        assert prepare_citation_acceptance(dsn, moved, report).body == artifact.read_bytes()
        assert calls == 3
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            cli.run(
                [
                    "assess-citations",
                    "--request",
                    str(request_path),
                    "--report",
                    str(report),
                    "--output-dir",
                    str(output),
                ]
            )
            == 0
        )
        assert calls == 4
        result = capsys.readouterr()
        assert json.loads(result.out)["artifact_sha256"] == first.artifact_sha256
        assert [json.loads(s)["event"] for s in result.err.splitlines()] == ["started", "completed"]
        assert str(tmp_path) not in result.out + result.err
        assert dsn not in result.out + result.err
        assert len(artifact.read_bytes()) <= 64 * 1024
        assert output.stat().st_mode & 0o777 == 0o700
        assert artifact.stat().st_mode & 0o777 == 0o600
        for forbidden in (b"DO_NOT_EXPORT", b"SUBJECT_DO_NOT_EXPORT", b"123.45", b"ADA-1"):
            assert forbidden not in artifact.read_bytes()
        for name, value in originals.items():
            if name != ".":
                assert archive_state(tmp_path)[name] == value
        # An existing output cannot cache a pass after the originals disappear.
        next((tmp_path / "raw" / "diavgeia" / "objects").rglob("*.body")).unlink()
        with pytest.raises(CitationAcceptanceError, match="^acceptance_evidence$"):
            export_citation_acceptance(dsn, request_path, report, output)
        assert calls == 5
        assert {k: v for k, v in archive_state(output).items() if k != "."} == stable
    assert state(pg_dsn) == before


@pytest.mark.parametrize("fault", ["raw", "normalized", "membership", "pages", "owner"])
def test_broken_proof_never_publishes_an_assessment(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    request = seed(pg_dsn, tmp_path / "raw")
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_citation_readout(dsn, request)
        report = subject(tmp_path / "reports", body)
        path = request_file(tmp_path, request)
        if fault == "raw":
            next((tmp_path / "raw" / "diavgeia" / "objects").rglob("*.body")).write_bytes(b"bad")
        elif fault == "normalized":
            tamper(pg_dsn, "UPDATE nima.record_versions SET normalized='{}'")
        elif fault == "membership":
            tamper(pg_dsn, "DELETE FROM nima.observations WHERE source_id='diavgeia:ADA-1'")
        elif fault == "pages":
            tamper(pg_dsn, "UPDATE nima.run_pages SET record_count=9")
        before, files = state(pg_dsn), archive_state(tmp_path)
        expected = "acceptance_database" if fault == "owner" else "acceptance_evidence"
        with pytest.raises(CitationAcceptanceError, match=f"^{expected}$"):
            export_citation_acceptance(
                pg_dsn if fault == "owner" else dsn, path, report, tmp_path / "out"
            )
        assert not (tmp_path / "out").exists()
        assert state(pg_dsn) == before
        assert archive_state(tmp_path) == files
