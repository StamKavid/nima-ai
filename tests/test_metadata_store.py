"""Explicit canonical selection, restricted SQL roles and independent query parity."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from nima.metadata.export import prepare_metadata
from nima.metadata.store import promote_metadata, query_metadata
from nima.sources.metadata_extract import MetadataError
from tests.test_analytics_snapshot import reader, state
from tests.test_metadata_export import kimdis_run


@contextmanager
def principal(dsn: str, *, write: bool = False) -> Iterator[str]:
    with reader(dsn) as (limited, role), psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            sql.SQL("GRANT USAGE ON SCHEMA nima_processing TO {}").format(sql.Identifier(role))
        )
        c.execute(
            sql.SQL(
                "GRANT SELECT ON nima_processing.metadata_snapshots,"
                "nima_processing.reported_market_metadata TO {}"
            ).format(sql.Identifier(role))
        )
        if write:
            c.execute(
                sql.SQL("GRANT INSERT ON nima_processing.metadata_snapshots TO {}").format(
                    sql.Identifier(role)
                )
            )
            c.execute(
                sql.SQL("GRANT SELECT ON nima.gemi_imports TO {}").format(sql.Identifier(role))
            )
        yield limited


def test_selected_snapshot_and_sql_filters_preserve_c2_bytes_and_source_state(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    before = state(pg_dsn)
    with principal(pg_dsn, write=True) as dsn:
        first = promote_metadata(dsn, "kimdis", run, root, selected.artifact_sha256)
        assert first.reused is False and first.assertion_count == 4
        assert promote_metadata(dsn, "kimdis", run, root, selected.artifact_sha256).reused is True
    with principal(pg_dsn) as dsn:
        assert query_metadata(dsn, selected.artifact_sha256) == raw
        actual = query_metadata(dsn, selected.artifact_sha256, dimension="buyer_function", code="8")
        expected, _ = prepare_metadata(
            "kimdis", run, root, dsn=pg_dsn, dimension="buyer_function", code="8"
        )
        assert actual == expected
    with psycopg.connect(pg_dsn) as c:
        row = c.execute(
            "SELECT observed_at,processed_at,taxonomy_validation,json_pointer "
            "FROM nima_processing.reported_market_metadata WHERE dimension=%s",
            ("buyer_function",),
        ).fetchone()
        assert row is not None and row[1] > row[0] and row[2] == "not_checked"
        assert row[3] == "/content/0/contractingAuthorityActivity"
    assert state(pg_dsn) == before


def test_selection_mismatch_and_reader_write_are_refused(pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    with (
        principal(pg_dsn, write=True) as dsn,
        pytest.raises(MetadataError, match="^metadata_selection$"),
    ):
        promote_metadata(dsn, "kimdis", run, root, "0" * 64)
    with principal(pg_dsn) as dsn, pytest.raises(MetadataError, match="^metadata_database$"):
        promote_metadata(dsn, "kimdis", run, root, selected.artifact_sha256)
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima_processing.metadata_snapshots").fetchone() == (
            0,
        )


def test_gemi_requires_matching_prior_import_and_retains_404_rows(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.storage.gemi import import_run
    from nima.storage.postgres import migrate
    from tests.test_gemi_import_archive import archive_run

    migrate(pg_dsn)
    root = tmp_path / "gemi"
    run = archive_run(root)
    raw, selected = prepare_metadata("gemi", run, root)
    with (
        principal(pg_dsn, write=True) as dsn,
        pytest.raises(MetadataError, match="^metadata_scope$"),
    ):
        promote_metadata(dsn, "gemi", run, root, selected.artifact_sha256)
    import_run(pg_dsn, root, run)
    before = state(pg_dsn)
    with principal(pg_dsn, write=True) as dsn:
        promote_metadata(dsn, "gemi", run, root, selected.artifact_sha256)
    with principal(pg_dsn) as dsn:
        assert query_metadata(dsn, selected.artifact_sha256) == raw
        filtered = json.loads(
            query_metadata(dsn, selected.artifact_sha256, dimension="supplier_kad", code="missing")
        )
        assert filtered["records"] == [] and filtered["coverage"]["unavailable_record_count"] == 1
    assert state(pg_dsn) == before


@pytest.mark.parametrize(
    "dimension,code", [("procurement_cpv", "99999999-9"), ("buyer_type", None), (None, None)]
)
def test_sql_matches_shared_policy_for_unknowns_and_no_match(
    pg_dsn: str, tmp_path: Path, dimension: str | None, code: str | None
) -> None:
    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)
    actual = query_metadata(pg_dsn, selected.artifact_sha256, dimension=dimension, code=code)
    expected, _ = prepare_metadata("kimdis", run, root, dsn=pg_dsn, dimension=dimension, code=code)
    assert actual == expected


def test_unavailable_or_unsupported_selection_is_an_error(pg_dsn: str, tmp_path: Path) -> None:
    from nima.storage.postgres import migrate

    migrate(pg_dsn)
    with pytest.raises(MetadataError, match="^metadata_unavailable$"):
        query_metadata(pg_dsn, "0" * 64)
    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)
    with pytest.raises(MetadataError, match="^metadata_input$"):
        query_metadata(pg_dsn, selected.artifact_sha256, dimension="supplier_kad")


@pytest.mark.parametrize("default_isolation", ["read committed", "repeatable read"])
def test_concurrent_same_selection_is_idempotent(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, default_isolation: str
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from psycopg.conninfo import conninfo_to_dict

    from nima.metadata import store

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    barrier = Barrier(2)

    def together(*args: object, **kwargs: object) -> object:
        result = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(store, "prepare_metadata", together)
    with principal(pg_dsn, write=True) as dsn, ThreadPoolExecutor(max_workers=2) as pool:
        role = conninfo_to_dict(dsn)["user"]
        assert isinstance(role, str)
        with psycopg.connect(pg_dsn) as c:
            c.execute(
                sql.SQL("ALTER ROLE {} SET default_transaction_isolation TO {}").format(
                    sql.Identifier(role), sql.Literal(default_isolation)
                )
            )
        results = list(
            pool.map(
                lambda _: promote_metadata(dsn, "kimdis", run, root, selected.artifact_sha256),
                range(2),
            )
        )
    assert sorted(r.reused for r in results) == [False, True]


def test_zero_record_snapshot_has_explicit_empty_coverage(pg_dsn: str, tmp_path: Path) -> None:
    from tests.test_analytics_snapshot import seed

    root = tmp_path / "archive"
    run = seed(pg_dsn, root, empty=True, project=False)
    raw, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)
    assert query_metadata(pg_dsn, selected.artifact_sha256) == raw
    assert json.loads(raw)["coverage"]["record_count"] == 0


def test_partial_capture_cannot_be_promoted(pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    with psycopg.connect(pg_dsn) as c:
        c.execute("UPDATE nima.ingest_runs SET status='interrupted' WHERE run_id=%s", (run,))
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    with pytest.raises(MetadataError, match="^metadata_capture$"):
        promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)


def test_corrupt_stored_hash_is_not_served(pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, _ = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        from psycopg.types.json import Jsonb

        c.execute(
            "INSERT INTO nima_processing.metadata_snapshots "
            "(snapshot_sha256,source,kimdis_run_id,document) VALUES (%s,%s,%s,%s)",
            ("0" * 64, "kimdis", run, Jsonb(json.loads(raw))),
        )
    with pytest.raises(MetadataError, match="^metadata_evidence$"):
        query_metadata(pg_dsn, "0" * 64)


def test_existing_wrong_document_is_a_conflict_not_reuse(pg_dsn: str, tmp_path: Path) -> None:
    from psycopg.types.json import Jsonb

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    document = json.loads(raw)
    document["meaning"] = "synthetic corrupt stored row"
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "INSERT INTO nima_processing.metadata_snapshots "
            "(snapshot_sha256,source,kimdis_run_id,document) VALUES (%s,%s,%s,%s)",
            (selected.artifact_sha256, "kimdis", run, Jsonb(document)),
        )
    with pytest.raises(MetadataError, match="^metadata_conflict$"):
        promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)


def test_source_scope_is_rechecked_after_preparation(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.metadata import store

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    prepared = prepare_metadata("kimdis", run, root, dsn=pg_dsn)

    def changed(*args: object, **kwargs: object) -> object:
        with psycopg.connect(pg_dsn) as c:
            c.execute("UPDATE nima.ingest_runs SET status='interrupted' WHERE run_id=%s", (run,))
        return prepared

    monkeypatch.setattr(store, "prepare_metadata", changed)
    with pytest.raises(MetadataError, match="^metadata_scope$"):
        promote_metadata(pg_dsn, "kimdis", run, root, prepared[1].artifact_sha256)


def test_source_writer_lease_blocks_promotion(pg_dsn: str, tmp_path: Path) -> None:
    from nima.storage.runs import run_lock_key

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute("SELECT pg_advisory_lock(%s)", (run_lock_key(run),))
        try:
            with pytest.raises(MetadataError, match="^metadata_busy$"):
                promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)
        finally:
            c.execute("SELECT pg_advisory_unlock(%s)", (run_lock_key(run),))
    assert not promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256).reused


def test_sql_only_query_works_when_archive_is_offline(pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)
    root.rename(tmp_path / "offline-archive")
    with principal(pg_dsn) as dsn:
        assert query_metadata(dsn, selected.artifact_sha256) == raw


def test_sql_disagreement_is_refused_before_publication(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from importlib.resources import files

    from nima.metadata import store

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    _, selected = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    promote_metadata(pg_dsn, "kimdis", run, root, selected.artifact_sha256)
    altered = (
        files("nima.metadata")
        .joinpath("query.sql")
        .read_text()
        .replace("m.status='reported'", "false")
    )
    (tmp_path / "query.sql").write_text(altered)
    monkeypatch.setattr(store, "files", lambda _: tmp_path)
    with pytest.raises(MetadataError, match="^metadata_query$"):
        query_metadata(pg_dsn, selected.artifact_sha256, dimension="buyer_function", code="8")


def test_unknown_snapshot_format_does_not_look_like_no_match(pg_dsn: str, tmp_path: Path) -> None:
    import hashlib

    from psycopg.types.json import Jsonb

    from nima.identity.artifacts import encode

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, _ = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    document = json.loads(raw)
    document["artifact_version"] = "synthetic-unsupported-format"
    digest = hashlib.sha256(encode(document)).hexdigest()
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "INSERT INTO nima_processing.metadata_snapshots "
            "(snapshot_sha256,source,kimdis_run_id,document) VALUES (%s,%s,%s,%s)",
            (digest, "kimdis", run, Jsonb(document)),
        )
    with pytest.raises(MetadataError, match="^metadata_version$"):
        query_metadata(pg_dsn, digest)
