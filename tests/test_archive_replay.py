"""Offline normalization replay retains capture lineage and leaves evidence untouched."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never, cast
from uuid import uuid4

import psycopg
import pytest

from nima.dataops import replay
from nima.ingestion.archive import Archive
from nima.storage.postgres import NORMALIZER_VERSION, PageStore, migrate
from tests.test_analytics_snapshot import reader, seed, state
from tests.test_collection import QUERY, body
from tests.test_graph_pilot_archive import state as file_state


def document(output: Path, result: replay.Replay) -> dict[str, Any]:
    path = output / (result.artifact_sha256 + ".json")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result.artifact_sha256
    assert path.stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o700
    return cast(dict[str, Any], json.loads(raw))


def test_limited_reader_replays_exact_money_and_original_capture_without_writes(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, output = tmp_path / "archive", tmp_path / "replays"
    run = seed(pg_dsn, root, project=False)
    sql_before, files_before = state(pg_dsn), file_state(root)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Replay cannot initialize originals or contact a source")

    monkeypatch.setattr("nima.ingestion.archive.Archive.__init__", forbidden)
    monkeypatch.setattr("httpx.Client.request", forbidden)
    with reader(pg_dsn) as (dsn, _):
        result = replay.replay_run(dsn, run, root, output, NORMALIZER_VERSION)
        assert replay.replay_run(dsn, run, root, output, NORMALIZER_VERSION) == result
    value = document(output, result)
    assert (
        value["normalizer_version"]
        == value["source_run"]["normalizer_version"]
        == NORMALIZER_VERSION
    )
    assert value["source_run"]["run_id"] == str(run)
    assert value["source_run"]["status"] == "complete"
    page = value["pages"][0]
    item = page["records"][0]
    assert page["observed_at"] == "2026-01-01T00:00:00+00:00"
    assert item["normalized"]["net_amount"] == "1E+2"
    assert item["normalized"]["buyer"]["name"] == "Συνθετικός αγοραστής"
    assert item["json_pointer"] == "/content/0"
    assert len(item["content_sha256"]) == len(page["raw_sha256"]) == 64
    assert (
        result.page_count,
        result.record_count,
        result.normalized_count,
        result.quarantined_count,
    ) == (1, 1, 1, 0)
    assert str(root) not in json.dumps(value) and "archive_root" not in value["source_run"]
    assert state(pg_dsn) == sql_before and file_state(root) == files_before


def test_historical_normalizer_identity_is_retained_not_a_target_requirement(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import postgres

    root, output = tmp_path / "archive", tmp_path / "replays"
    migrate(pg_dsn)
    run = uuid4()
    with monkeypatch.context() as old:
        old.setattr(postgres, "NORMALIZER_VERSION", "historic-test-version")
        store = PageStore(pg_dsn, Archive(root))
        store.start_run(run, QUERY)
        store.commit_page(run, body(total=1), observed_at=datetime(2025, 1, 1, tzinfo=UTC))
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        result = replay.replay_run(dsn, run, root, output, NORMALIZER_VERSION)
    value = document(output, result)
    assert value["source_run"]["normalizer_version"] == "historic-test-version"
    assert value["normalizer_version"] == NORMALIZER_VERSION
    assert value["pages"][0]["observed_at"] == "2025-01-01T00:00:00+00:00"
    assert state(pg_dsn) == before


def test_relocated_replay_matches_bytes_and_failed_capture_stays_explicit(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "original"
    run = seed(pg_dsn, root, project=False)
    with psycopg.connect(pg_dsn) as c:
        c.execute("UPDATE nima.ingest_runs SET status='failed' WHERE run_id=%s", (run,))
    with reader(pg_dsn) as (dsn, _):
        first = replay.replay_run(dsn, run, root, tmp_path / "one", NORMALIZER_VERSION)
        moved = tmp_path / "relocated"
        root.rename(moved)
        second = replay.replay_run(dsn, run, moved, tmp_path / "two", NORMALIZER_VERSION)
    assert first == second
    assert document(tmp_path / "two", second)["source_run"]["status"] == "failed"


def test_quarantine_keeps_original_index_and_valid_records_exact(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "archive"
    migrate(pg_dsn)
    run = uuid4()
    store = PageStore(pg_dsn, Archive(root))
    store.start_run(run, QUERY)
    envelope = json.loads(body(total=1))
    envelope.update(
        content=[
            {"referenceNumber": "A", "title": "Ελληνικά", "totalCostWithoutVAT": "12.3400"},
            {"referenceNumber": "B", "title": False},
        ],
        size=2,
        totalElements=2,
    )
    store.commit_page(
        run, json.dumps(envelope).encode(), observed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    with reader(pg_dsn) as (dsn, _):
        result = replay.replay_run(dsn, run, root, tmp_path / "out", NORMALIZER_VERSION)
    records = document(tmp_path / "out", result)["pages"][0]["records"]
    assert (result.normalized_count, result.quarantined_count) == (1, 1)
    assert records[0]["normalized"]["net_amount"] == "12.3400"
    assert records[1]["record_index"] == 1 and records[1]["json_pointer"] == "/content/1"
    assert records[1]["status"] == "quarantined" and records[1]["reason"]
    assert "normalized" not in records[1] and len(records[1]["content_sha256"]) == 64


def test_empty_committed_page_is_a_dataset_but_zero_pages_is_not(
    pg_dsn: str, tmp_path: Path
) -> None:
    from tests.test_archive_verify import metadata_run

    root = tmp_path / "empty"
    run = seed(pg_dsn, root, empty=True, project=False)
    with reader(pg_dsn) as (dsn, _):
        result = replay.replay_run(dsn, run, root, tmp_path / "valid", NORMALIZER_VERSION)
    assert result.page_count == 1 and result.record_count == 0
    assert document(tmp_path / "valid", result)["pages"][0]["records"] == []
    missing = tmp_path / "not-created"
    run = metadata_run(pg_dsn, tmp_path / "unread", [], 0)
    with reader(pg_dsn) as (dsn, _), pytest.raises(replay.ReplayError, match="^replay_empty$"):
        replay.replay_run(dsn, run, missing, tmp_path / "no-output", NORMALIZER_VERSION)
    assert not missing.exists()


@pytest.mark.parametrize("version", ["future-version", "", None, []])
def test_unknown_target_fails_before_database_or_files(
    version: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Unavailable targets cannot access private I/O")

    monkeypatch.setattr(replay, "connect", forbidden)
    with pytest.raises(replay.ReplayError, match="^replay_version$"):
        replay.replay_run(
            "not-read", uuid4(), tmp_path / "raw", tmp_path / "out", cast(str, version)
        )
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "damage",
    ["missing", "corrupt", "tampered_valid_json", "length", "symlink", "marker", "world_readable"],
)
def test_invalid_originals_fail_without_a_dataset(damage: str, pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    blob = next(root.rglob("*.body"))
    if damage == "missing":
        blob.unlink()
    elif damage == "corrupt":
        blob.write_bytes(b"x" * blob.stat().st_size)
    elif damage == "tampered_valid_json":
        original = blob.read_bytes()
        changed = original.replace(b"TEST-0", b"FAKE-0")
        assert changed != original and len(changed) == len(original)
        json.loads(changed)
        blob.write_bytes(changed)
    elif damage == "length":
        blob.write_bytes(blob.read_bytes() + b" ")
    elif damage == "symlink":
        alternate = tmp_path / "alternate"
        blob.rename(alternate)
        blob.symlink_to(alternate)
    elif damage == "marker":
        (root / ".nima-archive").write_text("invalid")
    else:
        root.chmod(0o755)
    before = state(pg_dsn), file_state(root)
    with reader(pg_dsn) as (dsn, _), pytest.raises(replay.ReplayError, match="^replay_evidence$"):
        replay.replay_run(dsn, run, root, tmp_path / "out", NORMALIZER_VERSION)
    assert not (tmp_path / "out").exists()
    assert (state(pg_dsn), file_state(root)) == before


@pytest.mark.parametrize(
    "invalid",
    [
        "checkpoint",
        "page_gap",
        "page_limit",
        "object_limit",
        "total_limit",
        "record_limit",
        "length",
        "envelope",
        "page_number",
        "record_count",
        "shape",
        "source",
    ],
)
def test_invalid_metadata_and_envelopes_cannot_publish(
    invalid: str, pg_dsn: str, tmp_path: Path
) -> None:
    from tests.test_archive_verify import metadata_run

    root = tmp_path / "archive"
    raw = body(total=1)
    if invalid == "envelope":
        raw = b"{}"
    digest = Archive(root).store(raw)
    count = 33 if invalid == "page_limit" else 9 if invalid == "total_limit" else 1
    size = (
        8 * 1024 * 1024 + 1
        if invalid == "object_limit"
        else 8 * 1024 * 1024
        if invalid == "total_limit"
        else len(raw) + 1
        if invalid == "length"
        else len(raw)
    )
    rows = [
        (
            i + 1 if invalid == "page_gap" else i,
            digest if invalid != "total_limit" else hashlib.sha256(str(i).encode()).hexdigest(),
            size,
        )
        for i in range(count)
    ]
    run = metadata_run(pg_dsn, root, rows, 2 if invalid == "checkpoint" else count)
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "UPDATE nima.ingest_runs SET total_records=1,total_pages=1,page_size=1 WHERE run_id=%s",
            (run,),
        )
        if invalid == "source":
            c.execute(
                "UPDATE nima.ingest_runs SET connector_version='unknown' WHERE run_id=%s", (run,)
            )
        if invalid == "shape":
            c.execute("UPDATE nima.ingest_runs SET total_records=2 WHERE run_id=%s", (run,))
        c.execute("ALTER TABLE nima.run_pages DISABLE TRIGGER pages_immutable")
        if invalid == "record_limit":
            c.execute("UPDATE nima.run_pages SET record_count=5001 WHERE run_id=%s", (run,))
        elif invalid != "record_count":
            c.execute("UPDATE nima.run_pages SET record_count=1 WHERE run_id=%s", (run,))
        c.execute("ALTER TABLE nima.run_pages ENABLE TRIGGER pages_immutable")
        if invalid == "page_number":
            # Metadata prefix is valid; the hash-verified envelope reports another page.
            other = Archive(root).store(body(page=1, total=2))
            c.execute(
                "INSERT INTO nima.raw_objects VALUES (%s,%s)", (other, len(body(page=1, total=2)))
            )
            c.execute("ALTER TABLE nima.run_pages DISABLE TRIGGER pages_immutable")
            c.execute("UPDATE nima.run_pages SET raw_sha256=%s WHERE run_id=%s", (other, run))
            c.execute("ALTER TABLE nima.run_pages ENABLE TRIGGER pages_immutable")
    reason = (
        "replay_source"
        if invalid == "source"
        else "replay_limit"
        if invalid in {"page_limit", "object_limit", "total_limit", "record_limit"}
        else "replay_evidence"
        if invalid in {"length", "envelope"}
        else "replay_scope"
    )
    with reader(pg_dsn) as (dsn, _), pytest.raises(replay.ReplayError, match="^" + reason + "$"):
        replay.replay_run(dsn, run, root, tmp_path / "out", NORMALIZER_VERSION)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("suffix", ["", "nested"])
def test_output_cannot_write_inside_original_archive(
    suffix: str, pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    before = file_state(root)
    with pytest.raises(replay.ReplayError, match="^replay_input$"):
        replay.replay_run(pg_dsn, run, root, root / suffix, NORMALIZER_VERSION)
    assert file_state(root) == before


def test_closed_repeatable_read_snapshot_excludes_a_later_commit(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.graph.pilot_archive import ArchiveBinding, ArchiveRecovery, RawReference, recover
    from nima.storage.connection import connect
    from nima.storage.postgres import validate_schema

    root = tmp_path / "archive"
    migrate(pg_dsn)
    store = PageStore(pg_dsn, Archive(root))
    run = uuid4()
    store.start_run(run, QUERY)
    store.commit_page(run, body(), observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    connections = []

    def tracked(dsn: str) -> psycopg.Connection[tuple[object, ...]]:
        c = connect(dsn)
        connections.append(c)
        return c

    def schema(c: psycopg.Connection[tuple[object, ...]]) -> None:
        assert c.execute("SHOW transaction_read_only").fetchone() == ("on",)
        assert c.execute("SHOW transaction_isolation").fetchone() == ("repeatable read",)
        validate_schema(c)

    def later(
        refs: tuple[RawReference, ...], bindings: tuple[ArchiveBinding, ...]
    ) -> ArchiveRecovery:
        assert connections and all(c.closed for c in connections)
        store.commit_page(run, body(page=1), observed_at=datetime(2026, 1, 2, tzinfo=UTC))
        return recover(refs, bindings)

    monkeypatch.setattr(replay, "connect", tracked)
    monkeypatch.setattr(replay, "validate_schema", schema)
    monkeypatch.setattr(replay, "recover", later)
    with reader(pg_dsn) as (dsn, _):
        result = replay.replay_run(dsn, run, root, tmp_path / "out", NORMALIZER_VERSION)
    value = document(tmp_path / "out", result)
    assert result.page_count == 1 and value["source_run"]["next_page"] == 1
    assert (
        value["source_run"]["total_pages"] == 2 and value["source_run"]["query"] == QUERY.payload()
    )
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT next_page FROM nima.ingest_runs WHERE run_id=%s", (run,)
        ).fetchone() == (2,)


@pytest.mark.parametrize("unsafe", ["symlink", "readable", "conflict"])
def test_unsafe_output_or_conflict_cannot_overwrite_a_result(
    unsafe: str, pg_dsn: str, tmp_path: Path
) -> None:
    root, output = tmp_path / "archive", tmp_path / "out"
    run = seed(pg_dsn, root, project=False)
    with reader(pg_dsn) as (dsn, _):
        first = replay.replay_run(dsn, run, root, output, NORMALIZER_VERSION)
        path = output / (first.artifact_sha256 + ".json")
        if unsafe == "conflict":
            path.write_bytes(b"preserve conflicting output")
        elif unsafe == "readable":
            output.chmod(0o755)
        else:
            output.rename(tmp_path / "real")
            output.symlink_to(tmp_path / "real", target_is_directory=True)
        before = file_state(tmp_path / "real" if unsafe == "symlink" else output)
        with pytest.raises(replay.ReplayError, match="^replay_output$"):
            replay.replay_run(dsn, run, root, output, NORMALIZER_VERSION)
        after = file_state(tmp_path / "real" if unsafe == "symlink" else output)
        assert after.keys() == before.keys()
        assert {k: v for k, v in after.items() if k != "."} == {
            k: v for k, v in before.items() if k != "."
        }


def test_old_quarantine_is_reprocessed_from_raw_not_copied_from_sql(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from nima.sources.kimdis import RecordIssue, normalize_page
    from nima.storage import postgres

    root = tmp_path / "archive"
    migrate(pg_dsn)
    run = uuid4()

    def historic(raw: bytes, *, max_bytes: int) -> object:
        page = normalize_page(raw, max_bytes=max_bytes)
        return replace(
            page, contracts=(), issues=(RecordIssue("historic rule", page.contracts[0].evidence),)
        )

    with monkeypatch.context() as old:
        old.setattr(postgres, "NORMALIZER_VERSION", "historic-quarantine-test")
        old.setattr(postgres, "normalize_page", historic)
        store = PageStore(pg_dsn, Archive(root))
        store.start_run(run, QUERY)
        store.commit_page(run, body(total=1), observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        result = replay.replay_run(dsn, run, root, tmp_path / "out", NORMALIZER_VERSION)
    assert result.normalized_count == 1 and result.quarantined_count == 0
    assert document(tmp_path / "out", result)["pages"][0]["records"][0]["status"] == "normalized"
    assert state(pg_dsn) == before
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT reason FROM nima.quarantine").fetchall() == [("historic rule",)]
        assert c.execute("SELECT count(*) FROM nima.observations").fetchone() == (0,)


@pytest.mark.parametrize("invalid", ["unknown_run", "schema", "privilege"])
def test_database_failures_have_fixed_reasons(invalid: str, pg_dsn: str, tmp_path: Path) -> None:
    from psycopg import sql

    if invalid == "schema":
        with pytest.raises(replay.ReplayError, match="^replay_schema$"):
            replay.replay_run(
                pg_dsn, uuid4(), tmp_path / "raw", tmp_path / "out", NORMALIZER_VERSION
            )
    else:
        root = tmp_path / "raw"
        run = seed(pg_dsn, root, project=False)
        with reader(pg_dsn) as (dsn, role):
            if invalid == "privilege":
                with psycopg.connect(pg_dsn) as admin:
                    admin.execute(
                        sql.SQL("REVOKE SELECT ON nima.run_pages FROM {}").format(
                            sql.Identifier(role)
                        )
                    )
            with pytest.raises(
                replay.ReplayError,
                match="^replay_database$" if invalid == "privilege" else "^replay_scope$",
            ):
                replay.replay_run(
                    dsn,
                    run if invalid == "privilege" else uuid4(),
                    root,
                    tmp_path / "out",
                    NORMALIZER_VERSION,
                )
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("bad", ["dsn", "uuid", "relative", "parent", "git", "nul"])
def test_invalid_selection_is_rejected_before_io(
    bad: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid selection cannot open SQL")

    monkeypatch.setattr(replay, "connect", forbidden)
    paths = {
        "relative": Path("relative"),
        "parent": Path("/tmp/../x"),
        "git": Path("/tmp/.git/x"),
        "nul": Path("/tmp/\x00x"),
    }
    with pytest.raises(replay.ReplayError, match="^replay_input$"):
        replay.replay_run(
            "" if bad == "dsn" else "not-read",
            cast(Any, "bad") if bad == "uuid" else uuid4(),
            paths.get(bad, tmp_path / "raw"),
            tmp_path / "out",
            NORMALIZER_VERSION,
        )


def test_output_limit_fails_before_publisher(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nima.identity.artifacts as artifacts

    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    monkeypatch.setattr(artifacts, "MAX_REPORT_BYTES", 10)
    with reader(pg_dsn) as (dsn, _), pytest.raises(replay.ReplayError, match="^replay_limit$"):
        replay.replay_run(dsn, run, root, tmp_path / "out", NORMALIZER_VERSION)
    assert not (tmp_path / "out").exists()
