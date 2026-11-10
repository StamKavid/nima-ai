"""Real PostgreSQL evidence cohorts and private report publication boundaries."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.identity import AssessmentError
from nima.identity.report import Report, assess_run
from nima.projections.worker import PROJECTION_VERSION, drain
from nima.storage.postgres import Connection
from tests.test_collection import QUERY, body
from tests.test_kimdis_pages import page_body, record
from tests.test_page_store import counts, store


def seed(dsn: str, path: Path, *rows: object) -> UUID:
    database = store(dsn, path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, page_body(*rows), observed_at=datetime(2026, 11, 6, tzinfo=UTC))
    drain(dsn)
    return run


def read_report(directory: Path) -> Report:
    return cast(Report, json.loads(next(directory.glob("*.json")).read_text()))


def test_cohort_evidence_replay_namespaces_and_issue_groups(pg_dsn: str, tmp_path: Path) -> None:
    rows = [
        {
            **record(str(i)),
            "organization": {"key": "001234567", "value": "Δήμος"},
            "organizationVatNumber": str(i),
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": name, "vatNumber": "001234567", "country": {"key": "GR"}}
                ]
            },
        }
        for i, name in enumerate(("ΑΛΦΑ", "ΑΛΦΑ ΑΕ"))
    ]
    run = seed(pg_dsn, tmp_path, *rows, {**record("bad"), "title": 4})
    seed(pg_dsn, tmp_path, record("unrelated"))
    directory = tmp_path / "reports"
    before = counts(pg_dsn)
    summary = assess_run(pg_dsn, run, PROJECTION_VERSION, directory)
    assert summary == assess_run(pg_dsn, run, PROJECTION_VERSION, directory)
    assert counts(pg_dsn) == before and summary["mention_count"] == 4
    assert len(list(directory.glob("*.json"))) == 1
    report = read_report(directory)
    assert report["automatic_identity_links"] == 0 and report["archive_integrity"] == "not_checked"
    assert report["coverage"]["quarantine_count"] == 1
    assert report["coverage"]["stored_run_status"] == "unmanaged"
    members = report["occurrences"]
    assert len(members) == 4 and {m["source_id"] for m in members} == {"kimdis:0", "kimdis:1"}
    assert members[0]["evidence"]["json_pointer"] == "/content/0"
    assert len(members[0]["evidence"]["raw_sha256"]) == 64
    assert members[0]["evidence"]["observed_at"].startswith("2026-11-06")
    groups = {g["namespace"]: g for g in report["groups"]}
    assert set(groups) == {"kimdis.buyer-key", "kimdis.reported-country-tax"}
    assert groups["kimdis.buyer-key"]["issues"] == ["tax_number_variation"]
    assert groups["kimdis.reported-country-tax"]["issues"] == ["name_variation"]
    assert os.stat(directory).st_mode & 0o777 == 0o700
    assert os.stat(next(directory.glob("*.json"))).st_mode & 0o777 == 0o600


def test_limits_missing_receipts_and_unknown_versions_fail_without_report(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    for limit in (0, 10001, True):
        with pytest.raises(ValueError):
            assess_run(pg_dsn, run, PROJECTION_VERSION, tmp_path / "out", max_mentions=limit)
    with pytest.raises(AssessmentError, match="projection_version"):
        assess_run(pg_dsn, run, "unsupported", tmp_path / "out")
    with pytest.raises(AssessmentError, match="run_unavailable"):
        assess_run(pg_dsn, uuid4(), PROJECTION_VERSION, tmp_path / "out")
    database = store(pg_dsn, tmp_path)
    pending = uuid4()
    database.start_run(pending, QUERY)
    database.commit_page(pending, page_body(record("pending")), observed_at=datetime.now(UTC))
    with pytest.raises(AssessmentError, match="projection_incomplete"):
        assess_run(pg_dsn, pending, PROJECTION_VERSION, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_empty_unknown_and_known_empty_suppliers_are_not_entities(
    pg_dsn: str, tmp_path: Path
) -> None:
    empty = seed(pg_dsn, tmp_path)
    summary = assess_run(pg_dsn, empty, PROJECTION_VERSION, tmp_path / "empty")
    assert summary["mention_count"] == summary["candidate_group_count"] == 0
    run = seed(
        pg_dsn,
        tmp_path,
        record("unknown"),
        {**record("empty"), "contractingDataDetails": {"contractingMembersDataList": []}},
    )
    assess_run(pg_dsn, run, PROJECTION_VERSION, tmp_path / "unknown")
    report = read_report(tmp_path / "unknown")
    assert report["coverage"]["unknown_supplier_lists"] == 1
    assert report["coverage"]["empty_supplier_lists"] == 1
    assert report["groups"] == [] and len(report["occurrences"]) == 2


def test_cohort_limits_do_not_truncate_or_publish(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path, record("one"), record("two"))
    with pytest.raises(AssessmentError, match="assessment_limit"):
        assess_run(pg_dsn, run, PROJECTION_VERSION, tmp_path / "out", max_mentions=1)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind", ["unsupported_run", "missing_mentions"])
def test_inconsistent_projection_or_processing_identity_is_rejected(
    pg_dsn: str, tmp_path: Path, kind: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    with psycopg.connect(pg_dsn) as connection:
        if kind == "unsupported_run":
            connection.execute("UPDATE nima.ingest_runs SET connector_version='unsupported'")
        else:
            connection.execute("ALTER TABLE nima.projection_mentions DISABLE TRIGGER USER")
            connection.execute("DELETE FROM nima.projection_mentions")
            connection.execute("ALTER TABLE nima.projection_mentions ENABLE TRIGGER USER")
    reason = "cohort_version" if kind == "unsupported_run" else "projection_incomplete"
    with pytest.raises(AssessmentError, match=reason):
        assess_run(pg_dsn, run, PROJECTION_VERSION, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("module", ["cohort", "artifacts"])
def test_input_and_serialized_byte_budgets_fail_before_publication(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    monkeypatch.setattr(f"nima.identity.{module}.MAX_REPORT_BYTES", 1)
    with pytest.raises(AssessmentError, match="assessment_limit"):
        assess_run(pg_dsn, run, PROJECTION_VERSION, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_snapshot_excludes_later_collection_and_projection(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.identity import cohort

    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, body(), observed_at=datetime.now(UTC))
    drain(pg_dsn)
    original = cohort._coverage

    def concurrent_append(
        connection: Connection, selected: UUID, version: str
    ) -> dict[str, object]:
        assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction), connection.transaction():
            connection.execute("UPDATE nima.ingest_runs SET next_page=next_page")
        snapshot = original(connection, selected, version)
        database.commit_page(run, body(page=1), observed_at=datetime.now(UTC))
        drain(pg_dsn)
        return snapshot

    monkeypatch.setattr(cohort, "_coverage", concurrent_append)
    assess_run(pg_dsn, run, PROJECTION_VERSION, tmp_path / "out")
    report = read_report(tmp_path / "out")
    assert report["coverage"]["page_count"] == report["coverage"]["observation_count"] == 1
    assert len(report["occurrences"]) == 1
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.observations").fetchone() == (2,)


@pytest.mark.parametrize(
    "hazard",
    [
        "symlink_directory",
        "parent_symlink",
        "public_directory",
        "symlink_file",
        "corrupt_file",
        "public_file",
        "fifo",
        "traversal",
        "git_directory",
    ],
)
def test_unsafe_report_paths_and_collisions_are_not_overwritten(
    pg_dsn: str, tmp_path: Path, hazard: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    directory = tmp_path / "out"
    assess_run(pg_dsn, run, PROJECTION_VERSION, directory)
    final = next(directory.glob("*.json"))
    original = final.read_bytes()
    target = tmp_path / "unrelated"
    target.write_bytes(b"private unrelated contents")
    output = directory
    if hazard == "symlink_directory":
        output = tmp_path / "alias"
        output.symlink_to(directory, target_is_directory=True)
    elif hazard == "parent_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        output = alias / "out"
    elif hazard == "public_directory":
        directory.chmod(0o755)
    elif hazard == "public_file":
        final.chmod(0o644)
    elif hazard == "traversal":
        output = directory / ".." / "out"
    elif hazard == "git_directory":
        output = tmp_path / ".git"
    else:
        final.unlink()
        if hazard == "symlink_file":
            final.symlink_to(target)
        elif hazard == "fifo":
            os.mkfifo(final, 0o600)
        else:
            final.write_bytes(b"corrupt")
            final.chmod(0o600)
    with pytest.raises(AssessmentError):
        assess_run(pg_dsn, run, PROJECTION_VERSION, output)
    assert target.read_bytes() == b"private unrelated contents"
    if hazard not in {"fifo", "symlink_file", "corrupt_file"}:
        assert final.read_bytes() == original


def test_cli_is_offline_and_redacts_output_failures(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.__main__ import main

    run = seed(pg_dsn, tmp_path, record())
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    args = [
        "identities",
        "assess",
        str(run),
        "--projection-version",
        PROJECTION_VERSION,
        "--output-dir",
        str(tmp_path / "out"),
    ]

    def no_http() -> None:
        pytest.fail("Assessment opened an HTTP client")

    monkeypatch.setattr("nima.__main__.httpx.Client", no_http)
    assert main(args) == 0
    output = capsys.readouterr()
    assert "tax_id" not in output.out and "ΔΟΚΙΜΑΣΤΙΚΗ" not in output.out
    assert json.loads(output.out)["mention_count"] == 1
    assert main([*args, "--max-mentions", "0"]) == 2
    capsys.readouterr()

    def fail(*_: object) -> str:
        raise OSError("private connection and person details")

    monkeypatch.setattr("nima.identity.report.publish", fail)
    assert main(args) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["failure"] == "output_io"
    assert "private" not in output.out + output.err
