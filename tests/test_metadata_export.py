"""Bounded private metadata through actual archives, SQL principals and CLI."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from nima.__main__ import main
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.metadata.export import export_metadata
from nima.metadata.extract import MetadataError
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.test_analytics_snapshot import reader, state
from tests.test_collection import QUERY, body
from tests.test_gemi_import_archive import archive_run, snapshot


def kimdis_run(dsn: str, root: Path) -> UUID:
    migrate(dsn)
    run = uuid4()
    store = RunStore(dsn, Archive(root), run, Limits())
    with store.lease():
        store.begin(QUERY)
        store.commit_page(
            run,
            body(
                total=1,
                contractingAuthorityActivity={"key": "8", "value": "Άμυνα"},
                objectDetailsList=[{"cpvs": [{"key": "33141120-7", "value": "Συνθετικό"}]}],
            ),
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            owner=store.owner,
        )
        store.finish(Summary(status="complete"))
    return run


def test_kimdis_select_only_cli_and_filtered_coverage(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, out = tmp_path / "archive", tmp_path / "output"
    run = kimdis_run(pg_dsn, root)
    before, original = state(pg_dsn), snapshot(root)
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            main(
                [
                    "metadata",
                    "kimdis",
                    "--run-id",
                    str(run),
                    "--archive-dir",
                    str(root),
                    "--output-dir",
                    str(out),
                    "--dimension",
                    "buyer_function",
                    "--code",
                    "8",
                ]
            )
            == 0
        )
        terminal = capsys.readouterr().out
        assert "Άμυνα" not in terminal and str(run) not in terminal and str(root) not in terminal
        data = json.loads(next(out.glob("*.json")).read_bytes())
        assert data["coverage"]["assertion_count"] == 4
        assert data["matched_assertion_count"] == 1
        record = data["records"][0]
        assert record["observed_at"] == "2026-01-01T00:00:00+00:00"
        assert record["assertions"][0]["label"] == "Άμυνα"
        assert len(record["raw_sha256"]) == len(record["content_sha256"]) == 64
        result = export_metadata(
            "kimdis", run, root, out, dsn=dsn, dimension="buyer_function", code="8"
        )
        assert result.matched_assertion_count == 1 and len(list(out.glob("*.json"))) == 1
        relocated = tmp_path / "relocated"
        shutil.copytree(root, relocated)
        assert (
            export_metadata(
                "kimdis",
                run,
                relocated,
                tmp_path / "second",
                dsn=dsn,
                dimension="buyer_function",
                code="8",
            )
            == result
        )
    assert state(pg_dsn) == before and snapshot(root) == original


def test_gemi_without_database_or_key_keeps_not_found_and_missing_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, out = tmp_path / "gemi", tmp_path / "output"
    run = archive_run(root)
    original = snapshot(root)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    monkeypatch.delenv("NIMA_GEMI_API_KEY", raising=False)
    assert (
        main(
            [
                "metadata",
                "gemi",
                "--run-id",
                str(run),
                "--archive-dir",
                str(root),
                "--output-dir",
                str(out),
            ]
        )
        == 0
    )
    data = json.loads(next(out.glob("*.json")).read_bytes())
    assert len(data["records"]) == 2 and data["coverage"]["unavailable_record_count"] == 1
    assert data["records"][0]["assertions"][0]["dimension"] == "supplier_kad"
    assert "001234567" not in capsys.readouterr().out
    assert snapshot(root) == original


def test_missing_archive_is_not_initialized_or_output_created(tmp_path: Path) -> None:
    with pytest.raises(MetadataError):
        export_metadata("gemi", uuid4(), tmp_path / "missing", tmp_path / "out")
    assert not (tmp_path / "missing").exists() and not (tmp_path / "out").exists()


def test_output_inside_archive_and_code_without_dimension_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    for output, code in [(root / "output", None), (tmp_path / "out", "8")]:
        with pytest.raises(MetadataError, match="^metadata_input$"):
            export_metadata("gemi", uuid4(), root, output, code=code)
    assert not root.exists()


def test_corruption_blocks_publication(pg_dsn: str, tmp_path: Path) -> None:
    root, out = tmp_path / "archive", tmp_path / "out"
    run = kimdis_run(pg_dsn, root)
    target = next((root / "objects").rglob("*.body"))
    target.write_bytes(b"damaged")
    with reader(pg_dsn) as (dsn, _), pytest.raises(MetadataError, match="^metadata_evidence$"):
        export_metadata("kimdis", run, root, out, dsn=dsn)
    assert not out.exists() and target.read_bytes() == b"damaged"


def test_no_match_keeps_full_quality_scope(pg_dsn: str, tmp_path: Path) -> None:
    root, out = tmp_path / "archive", tmp_path / "out"
    run = kimdis_run(pg_dsn, root)
    with reader(pg_dsn) as (dsn, _):
        result = export_metadata(
            "kimdis", run, root, out, dsn=dsn, dimension="procurement_cpv", code="99999999-9"
        )
    data = json.loads(next(out.glob("*.json")).read_bytes())
    assert result.record_count == 1 and result.matched_assertion_count == 0
    assert data["records"] == [] and data["coverage"]["assertion_count"] == 4
    assert data["coverage"]["quality_counts"] == {"missing": 2, "reported": 2}


def test_global_limit_is_not_a_per_page_truncation(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.metadata import extract

    root = tmp_path / "raw"
    migrate(pg_dsn)
    run = uuid4()
    store = RunStore(pg_dsn, Archive(root), run, Limits())
    with store.lease():
        store.begin(QUERY)
        for page in range(2):
            store.commit_page(
                run,
                body(page, total=2),
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                owner=store.owner,
            )
        store.finish(Summary(status="complete"))
    monkeypatch.setattr(extract, "MAX_ASSERTIONS", 6)
    with reader(pg_dsn) as (dsn, _), pytest.raises(MetadataError, match="^metadata_limit$"):
        export_metadata("kimdis", run, root, tmp_path / "out", dsn=dsn)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("source,dsn", [("other", ""), ("kimdis", "")])
def test_invalid_source_or_missing_database_has_no_effects(
    tmp_path: Path, source: str, dsn: str
) -> None:
    with pytest.raises(MetadataError, match="^metadata_input$"):
        export_metadata(source, uuid4(), tmp_path / "root", tmp_path / "out", dsn=dsn)
    assert not (tmp_path / "out").exists()


def test_cli_invalid_query_is_private_fixed_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "metadata",
                "gemi",
                "--run-id",
                str(uuid4()),
                "--archive-dir",
                str(tmp_path / "private-input"),
                "--output-dir",
                str(tmp_path / "private-output"),
                "--code",
                "private-code",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "failure": "metadata_input"}


def test_gemi_tampered_body_cannot_publish(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run = archive_run(root)
    for target in (root / "objects").rglob("*.body"):
        target.write_bytes(b"changed")
    with pytest.raises(MetadataError, match="^metadata_evidence$"):
        export_metadata("gemi", run, root, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "source,dimension",
    [("kimdis", "supplier_kad"), ("gemi", "buyer_function"), ("gemi", "procurement_cpv")],
)
def test_dimension_unavailable_from_source_is_not_a_zero(
    tmp_path: Path, source: str, dimension: str
) -> None:
    with pytest.raises(MetadataError, match="^metadata_input$"):
        export_metadata(
            source,
            uuid4(),
            tmp_path / "absent",
            tmp_path / "out",
            dimension=dimension,
            dsn="synthetic",
        )
    assert not (tmp_path / "out").exists()
