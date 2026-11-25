"""One verified two-source artifact; no network, source writes or hidden identity claims."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import commands
from nima.analytics import snapshot as session
from nima.analytics.citation_readout import export_citation_readout, prepare_citation_readout
from nima.analytics.result import ReadoutError
from nima.storage.connection import connect as database_connect
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_cohort import seed
from tests.test_graph_pilot_archive import state as archive_state


def test_known_answer_is_private_reproducible_and_independent_of_archive_location(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_http(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Offline readout attempted HTTP")

    monkeypatch.setattr(httpx.Client, "send", no_http)
    request = seed(pg_dsn, tmp_path / "originals")
    before = state(pg_dsn)
    originals = archive_state(tmp_path / "originals")
    connection_count = 0
    connect = database_connect

    def counted(dsn: str) -> Any:
        nonlocal connection_count
        connection_count += 1
        return connect(dsn)

    monkeypatch.setattr(session, "connect", counted)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_citation_readout(dsn, request)
        assert connection_count == 1
        assert prepare_citation_readout(dsn, request)[0] == body
    data = json.loads(body)
    assert result.outcome_counts["resolved"] == 1
    assert data["version"] == "nima-source-citations-v1"
    assert data["quality"]["coverage"] == "selected_complete_captures"
    assert data["request_sha256"] == request.request_sha256
    assert data["model"]["definition"]["status"] == "draft"
    assert len(data["evidence"]) == 2
    capture = next(c for c in data["captures"] if c["source"] == "diavgeia")
    assert capture["source_attribution"]["statements"] == [
        "Source: Diavgeia (diavgeia.gov.gr), CC BY 4.0; data retrieved on 2026-01-01"
    ]
    assert data["model"]["result"] == result.payload()
    for excluded in [
        "DO_NOT_EXPORT",
        "SUBJECT_DO_NOT_EXPORT",
        "SUPPLIER NAME",
        "123.45",
        "456.78",
        str(tmp_path),
    ]:
        assert excluded.encode() not in body
    moved = tmp_path / "relocated"
    shutil.copytree(tmp_path / "originals", moved)
    relocated = replace(
        request,
        archive_bindings=tuple(
            replace(b, root=moved / b.root.name) for b in request.archive_bindings
        ),
    )
    with reader(pg_dsn) as (dsn, _):
        assert prepare_citation_readout(dsn, relocated)[0] == body
    assert state(pg_dsn) == before
    assert archive_state(tmp_path / "originals") == originals
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps(
            {
                **request.semantic_payload(),
                "archive_bindings": [
                    {"source": b.source, "run_id": str(b.run_id), "root": str(b.root)}
                    for b in request.archive_bindings
                ],
            }
        )
    )
    request_file.chmod(0o600)
    with reader(pg_dsn) as (dsn, _):
        export = export_citation_readout(dsn, request_file, tmp_path / "output")
        assert export_citation_readout(dsn, request_file, tmp_path / "output") == export
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            commands.run(
                [
                    "source-citations",
                    "--request",
                    str(request_file),
                    "--output-dir",
                    str(tmp_path / "cli"),
                ]
            )
            == 0
        )
    artifact = tmp_path / "output" / (export.artifact_sha256 + ".json")
    assert artifact.read_bytes() == body
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "output").stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("option", ["partial", "quarantined", "no_pages"])
def test_partial_capture_is_disclosed_even_when_a_reference_resolves(
    pg_dsn: str, tmp_path: Path, option: str
) -> None:
    request = seed(pg_dsn, tmp_path, **{option: True})
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_citation_readout(dsn, request)
    data = json.loads(body)
    assert data["quality"]["coverage"] == "partial_capture"
    assert result.edges[0].outcome == ("unresolved" if option == "no_pages" else "resolved")
    assert data["quality"]["metric_eligibility"] == "not_assessed_v1_08"


def test_corrupt_target_is_checked_even_without_a_matching_source_reference(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = seed(pg_dsn, tmp_path)
    # A cutoff preceding all records yields no edges, but must not bypass original checks.
    request = replace(request, observation_cutoff=request.observation_cutoff.replace(year=2025))
    binding = next(b for b in request.archive_bindings if b.source == "diavgeia")
    path = next((binding.root / "objects").rglob("*.body"))
    path.write_bytes(b"corrupt")
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^citation_evidence$"):
        prepare_citation_readout(dsn, request)


def test_cli_errors_never_echo_configuration_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert (
        commands.run(
            [
                "source-citations",
                "--request",
                str(tmp_path / "private"),
                "--output-dir",
                str(tmp_path / "output"),
            ]
        )
        == 2
    )
    output = capsys.readouterr().out
    assert json.loads(output)["failure"] == "citation_input"
    assert str(tmp_path) not in output


def test_owner_cannot_be_used_as_the_readout_principal(pg_dsn: str, tmp_path: Path) -> None:
    request = seed(pg_dsn, tmp_path)
    before = state(pg_dsn)
    with pytest.raises(ReadoutError, match="^citation_database$"):
        prepare_citation_readout(pg_dsn, request)
    assert state(pg_dsn) == before
