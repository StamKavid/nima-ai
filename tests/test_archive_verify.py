"""Committed-page integrity uses real SQL snapshots and unmodified private originals."""

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Never, cast
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.__main__ import main
from nima.dataops import archive as verification
from nima.dataops.archive import VerificationError, verify_run
from nima.graph.pilot_archive import ArchiveBinding, ArchiveRecovery, RawReference, recover
from nima.ingestion.archive import Archive
from nima.storage.connection import connect
from nima.storage.postgres import PageStore, migrate, validate_schema
from tests.test_analytics_snapshot import reader, seed, state
from tests.test_collection import QUERY, body
from tests.test_graph_pilot_archive import state as file_state


def test_limited_reader_verifies_all_originals_without_changing_sql_or_files(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    sql_before, files_before = state(pg_dsn), file_state(root)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Integrity verification must not initialize archives or contact sources")

    monkeypatch.setattr("nima.ingestion.archive.Archive.__init__", forbidden)
    monkeypatch.setattr("httpx.Client.request", forbidden)
    with reader(pg_dsn) as (dsn, _):
        result = verify_run(dsn, run, root)
        assert asdict(result) == {
            "outcome": "verified_committed_pages",
            "scope": "kimdis_committed_pages_only",
            "run_status": "complete",
            "page_count": 1,
            "object_count": 1,
            "verified_bytes": next(root.rglob("*.body")).stat().st_size,
        }
        assert verify_run(dsn, run, root) == result
    assert state(pg_dsn) == sql_before and file_state(root) == files_before


@pytest.mark.parametrize("damage", ["missing", "corrupt", "oversized", "symlink", "hardlink"])
def test_original_integrity_and_shared_body_links_preserve_files(
    damage: str, pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    blob = next(root.rglob("*.body"))
    original = blob.read_bytes()
    if damage == "missing":
        blob.unlink()
    elif damage == "corrupt":
        blob.write_bytes(b"x" * len(original))
    elif damage == "oversized":
        blob.write_bytes(original + b" ")
    else:
        other = tmp_path / "other"
        other.write_bytes(original)
        other.chmod(0o600)
        blob.unlink()
        if damage == "symlink":
            blob.symlink_to(other)
        else:
            blob.hardlink_to(other)
    before = file_state(root)
    with reader(pg_dsn) as (dsn, _):
        if damage == "hardlink":
            assert blob.stat().st_nlink == 2
            assert verify_run(dsn, run, root).object_count == 1
        else:
            with pytest.raises(VerificationError, match="^archive_evidence$"):
                verify_run(dsn, run, root)
    assert file_state(root) == before


def test_cli_has_fixed_summary_and_no_database_url_flag(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(["archive", "verify", "--run-id", str(run), "--archive-dir", str(root)]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["status"] == "complete" and result["page_count"] == 1
    assert str(root) not in output.out and str(run) not in output.out and not output.err
    with pytest.raises(SystemExit) as help_exit:
        main(["archive", "verify", "--help"])
    assert help_exit.value.code == 0
    assert "--database-url" not in capsys.readouterr().out


def test_unknown_run_does_not_create_archive(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "existing", project=False)
    assert run
    missing = tmp_path / "private-sentinel"
    with reader(pg_dsn) as (dsn, _), pytest.raises(VerificationError, match="^archive_scope$"):
        verify_run(dsn, uuid4(), missing)
    assert not missing.exists()


def metadata_run(dsn: str, root: Path, pages: list[tuple[int, str, int]], checkpoint: int) -> UUID:
    """Synthetic SQL metadata for byte integrity; it is not a source-normalization fixture."""
    migrate(dsn)
    run = uuid4()
    PageStore(dsn, Archive(root)).start_run(run, QUERY)
    with psycopg.connect(dsn) as connection:
        for number, digest, size in pages:
            connection.execute(
                "INSERT INTO nima.raw_objects VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (digest, size),
            )
            connection.execute(
                """INSERT INTO nima.run_pages
                (run_id,page_number,raw_sha256,observed_at,record_count,quarantined_count)
                VALUES (%s,%s,%s,clock_timestamp(),0,0)""",
                (run, number, digest),
            )
        connection.execute(
            "UPDATE nima.ingest_runs SET next_page=%s WHERE run_id=%s", (checkpoint, run)
        )
    return run


def test_no_pages_is_not_a_verified_empty_response(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = metadata_run(pg_dsn, tmp_path / "archive", [], 0)
    missing = tmp_path / "not-created"
    with reader(pg_dsn) as (dsn, _):
        result = verify_run(dsn, run, missing)
        assert result.outcome == "no_committed_pages" and result.verified_bytes == 0
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(["archive", "verify", "--run-id", str(run), "--archive-dir", str(missing)]) == 3
    assert json.loads(capsys.readouterr().out)["outcome"] == "no_committed_pages"
    assert not missing.exists()
    root = tmp_path / "empty-response"
    run = seed(pg_dsn, root, empty=True, project=False)
    with reader(pg_dsn) as (dsn, _):
        result = verify_run(dsn, run, root)
        assert result.outcome == "verified_committed_pages"
        assert result.page_count == result.object_count == 1 and result.verified_bytes > 0


def test_relocated_archive_and_partial_run_are_explicit(pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "original"
    run = seed(pg_dsn, root, project=False)
    moved = tmp_path / "relocated"
    root.rename(moved)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("UPDATE nima.ingest_runs SET status='failed' WHERE run_id=%s", (run,))
    with reader(pg_dsn) as (dsn, _):
        result = verify_run(dsn, run, moved)
    assert result.run_status == "failed" and result.outcome == "verified_committed_pages"
    assert not root.exists() and result.scope == "kimdis_committed_pages_only"


@pytest.mark.parametrize(
    ("sizes", "checkpoint", "start", "reason"),
    [
        ([1], 2, 0, "archive_scope"),
        ([1], 1, 1, "archive_scope"),
        ([1] * 33, 33, 0, "archive_limit"),
        ([8 * 1024 * 1024 + 1], 1, 0, "archive_limit"),
        ([8 * 1024 * 1024] * 9, 9, 0, "archive_limit"),
    ],
)
def test_metadata_and_limits_fail_before_any_body_read(
    sizes: list[int],
    checkpoint: int,
    start: int,
    reason: str,
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "archive"
    rows = [
        (i + start, hashlib.sha256(str(i).encode()).hexdigest(), n) for i, n in enumerate(sizes)
    ]
    run = metadata_run(pg_dsn, root, rows, checkpoint)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid or over-budget SQL scope must fail before archive access")

    monkeypatch.setattr(verification, "recover", forbidden)
    with reader(pg_dsn) as (dsn, _), pytest.raises(VerificationError, match=f"^{reason}$"):
        verify_run(dsn, run, root)


def test_recorded_size_mismatch_fails_even_for_a_correct_body_hash(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "archive"
    archive = Archive(root)
    digest = archive.store(b"original")
    run = metadata_run(pg_dsn, root, [(0, digest, 9)], 1)
    with reader(pg_dsn) as (dsn, _), pytest.raises(VerificationError, match="^archive_evidence$"):
        verify_run(dsn, run, root)


def test_exact_page_limit_and_shared_locations_do_not_include_orphan_files(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "archive"
    archive = Archive(root)
    digest = archive.store(b"one shared original")
    orphan = archive.store(b"unreferenced original")
    orphan_path = root / "objects" / orphan[:2] / f"{orphan}.body"
    orphan_path.write_bytes(b"orphan outside this selected committed scope")
    run = metadata_run(pg_dsn, root, [(n, digest, 19) for n in range(32)], 32)
    before = file_state(root)
    with reader(pg_dsn) as (dsn, _):
        result = verify_run(dsn, run, root)
    assert result.page_count == 32 and result.object_count == 1 and result.verified_bytes == 19
    assert file_state(root) == before


def test_sql_closes_before_files_and_later_commits_are_outside_the_snapshot(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "archive"
    migrate(pg_dsn)
    store = PageStore(pg_dsn, Archive(root))
    run = uuid4()
    store.start_run(run, QUERY)
    now = datetime.now(UTC)
    store.commit_page(run, body(page=0), observed_at=now)
    connections: list[psycopg.Connection[tuple[object, ...]]] = []
    transaction_checks: list[bool] = []

    def tracked(dsn: str) -> psycopg.Connection[tuple[object, ...]]:
        connection = connect(dsn)
        connections.append(connection)
        return connection

    def checked_schema(connection: psycopg.Connection[tuple[object, ...]]) -> None:
        assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)
        assert connection.execute("SHOW transaction_isolation").fetchone() == ("repeatable read",)
        validate_schema(connection)
        transaction_checks.append(True)

    original_recovery = recover

    def concurrent_commit(
        references: tuple[RawReference, ...],
        bindings: tuple[ArchiveBinding, ...],
    ) -> ArchiveRecovery:
        assert connections and all(c.closed for c in connections)
        store.commit_page(run, body(page=1), observed_at=now)
        return original_recovery(references, bindings)

    monkeypatch.setattr(verification, "connect", tracked)
    monkeypatch.setattr(verification, "validate_schema", checked_schema)
    monkeypatch.setattr(verification, "recover", concurrent_commit)
    with reader(pg_dsn) as (dsn, _):
        result = verify_run(dsn, run, root)
    assert result.page_count == 1 and transaction_checks == [True]
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.run_pages").fetchone() == (2,)


@pytest.mark.parametrize("unsafe", ["root_symlink", "world_readable", "bad_marker", "fifo"])
def test_unsafe_archive_is_not_modified(unsafe: str, pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    selected = root
    if unsafe == "root_symlink":
        selected = tmp_path / "alias"
        selected.symlink_to(root, target_is_directory=True)
    elif unsafe == "world_readable":
        root.chmod(0o755)
    elif unsafe == "bad_marker":
        (root / ".nima-archive").write_text("changed")
    else:
        path = next(root.rglob("*.body"))
        path.unlink()
        os.mkfifo(path, 0o600)
    with reader(pg_dsn) as (dsn, _), pytest.raises(VerificationError, match="^archive_evidence$"):
        verify_run(dsn, run, selected)
    if unsafe == "world_readable":
        assert root.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        ["private-sentinel"],
        ["verify"],
        ["verify", "--run-id", "private-sentinel", "--archive-dir", "/private-sentinel"],
        [
            "verify",
            "--run-id",
            str(UUID(int=1)),
            "--archive-dir",
            "/private-sentinel",
            "--api-key",
            "private-sentinel",
        ],
        ["verify", "--run", str(UUID(int=1)), "--archive-dir", "/private-sentinel"],
    ],
)
def test_bad_cli_input_cannot_touch_private_io(
    tokens: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Bad parsing must precede database/filesystem access")

    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    monkeypatch.setattr(verification, "verify_run", forbidden)
    assert main(["archive", *tokens]) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": "archive_configuration"}
    assert not output.err and "private-sentinel" not in output.out


@pytest.mark.parametrize("configured", [None, " \t"])
def test_missing_environment_has_fixed_error(
    configured: str | None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if configured is None:
        monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("NIMA_DATABASE_URL", configured)
    assert (
        main(["archive", "verify", "--run-id", str(UUID(int=1)), "--archive-dir", "/not-read"]) == 2
    )
    assert json.loads(capsys.readouterr().out)["failure"] == "archive_configuration"


@pytest.mark.parametrize(
    ("error", "code", "reason"),
    [
        (VerificationError("archive_input"), 2, "archive_input"),
        (VerificationError("archive_database"), 1, "archive_database"),
        (OSError("private-sentinel"), 1, "archive_evidence"),
        (KeyboardInterrupt(), 130, "archive_interrupted"),
    ],
)
def test_operational_errors_are_sanitized(
    error: BaseException,
    code: int,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failed(*args: object, **kwargs: object) -> Never:
        raise error

    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    monkeypatch.setattr(verification, "verify_run", failed)
    assert (
        main(["archive", "verify", "--run-id", str(UUID(int=1)), "--archive-dir", "/not-read"])
        == code
    )
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": reason}
    assert "private-sentinel" not in output.out and not output.err


def test_installed_module_executes_real_readonly_verification(pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    with reader(pg_dsn) as (dsn, _):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "nima",
                "archive",
                "verify",
                "--run-id",
                str(run),
                "--archive-dir",
                str(root),
            ],
            env={**os.environ, "NIMA_DATABASE_URL": dsn},
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout)["outcome"] == "verified_committed_pages"


@pytest.mark.parametrize(
    ("dsn", "run_id", "path"),
    [
        ("", UUID(int=1), Path("/not-read")),
        ("private-sentinel", "private-sentinel", Path("/not-read")),
        ("private-sentinel", UUID(int=1), Path("relative")),
        ("private-sentinel", UUID(int=1), Path("/tmp/../not-read")),
        ("private-sentinel", UUID(int=1), Path("/tmp/.git/not-read")),
        ("private-sentinel", UUID(int=1), Path("/tmp/\x00not-read")),
    ],
)
def test_invalid_programmatic_selection_precedes_sql(
    dsn: str, run_id: object, path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid programmatic selections must not open a connection")

    monkeypatch.setattr(verification, "connect", forbidden)
    with pytest.raises(VerificationError, match="^archive_input$"):
        verify_run(dsn, cast(UUID, run_id), path)


def test_unmigrated_database_has_fixed_failure(pg_dsn: str, tmp_path: Path) -> None:
    with pytest.raises(VerificationError, match="^archive_schema$"):
        verify_run(pg_dsn, uuid4(), tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_missing_select_privilege_has_fixed_failure(pg_dsn: str, tmp_path: Path) -> None:
    from psycopg import sql

    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    with reader(pg_dsn) as (dsn, role):
        with psycopg.connect(pg_dsn) as admin:
            admin.execute(
                sql.SQL("REVOKE SELECT ON nima.run_pages FROM {}").format(sql.Identifier(role))
            )
        with pytest.raises(VerificationError, match="^archive_database$"):
            verify_run(dsn, run, root)
