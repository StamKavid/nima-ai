"""Additive metadata storage never becomes another source ledger."""

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.metadata.export import prepare_metadata
from nima.storage.postgres import migrate
from tests.test_metadata_export import kimdis_run


def test_metadata_schema_is_separate_and_previous_migrations_preserved(pg_dsn: str) -> None:
    from nima.storage.postgres import _migrations

    assert len(_migrations()) == 11
    migrate(pg_dsn)
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='nima'").fetchone() == (
            27,
        )
        assert c.execute(
            "SELECT to_regclass('nima_processing.reported_market_metadata')"
        ).fetchone() == ("nima_processing.reported_market_metadata",)
        assert c.execute(
            "SELECT sha256 FROM nima.schema_migrations WHERE version=8"
        ).fetchone() == (_migrations()[7][2],)


@pytest.mark.parametrize(
    "operation",
    [
        "UPDATE nima_processing.metadata_snapshots SET source=source",
        "DELETE FROM nima_processing.metadata_snapshots",
        "TRUNCATE nima_processing.metadata_snapshots",
    ],
)
def test_snapshot_immutable_even_for_owner(pg_dsn: str, tmp_path: Path, operation: str) -> None:
    import json

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, prepared = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "INSERT INTO nima_processing.metadata_snapshots "
            "(snapshot_sha256,source,kimdis_run_id,document) VALUES (%s,%s,%s,%s)",
            (prepared.artifact_sha256, "kimdis", run, Jsonb(json.loads(raw))),
        )
    with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        c.execute(operation)


def test_foreign_keys_and_document_scope_are_enforced(pg_dsn: str, tmp_path: Path) -> None:
    import json

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, prepared = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    document = json.loads(raw)
    for key, value in [("kimdis_run_id", uuid4()), ("source", "gemi")]:
        row = {
            "snapshot_sha256": prepared.artifact_sha256,
            "source": "kimdis",
            "kimdis_run_id": run,
            "document": Jsonb(document),
        }
        row[key] = value
        with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.IntegrityError):
            c.execute(
                "INSERT INTO nima_processing.metadata_snapshots "
                "(snapshot_sha256,source,kimdis_run_id,document) VALUES "
                "(%(snapshot_sha256)s,%(source)s,%(kimdis_run_id)s,%(document)s)",
                row,
            )


def test_declared_counts_cannot_disagree_with_actual_assertions(
    pg_dsn: str, tmp_path: Path
) -> None:
    import json

    root = tmp_path / "archive"
    run = kimdis_run(pg_dsn, root)
    raw, prepared = prepare_metadata("kimdis", run, root, dsn=pg_dsn)
    document = json.loads(raw)
    document["coverage"]["assertion_count"] = 0
    with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.IntegrityError):
        c.execute(
            "INSERT INTO nima_processing.metadata_snapshots "
            "(snapshot_sha256,source,kimdis_run_id,document) VALUES (%s,%s,%s,%s)",
            (prepared.artifact_sha256, "kimdis", run, Jsonb(document)),
        )


def test_upgrade_from_eight_keeps_existing_derived_rows(pg_dsn: str) -> None:
    from nima.storage.postgres import _migrations

    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(
            "CREATE SCHEMA nima; CREATE TABLE nima.schema_migrations "
            "(version int PRIMARY KEY,sha256 text NOT NULL)"
        )
        for version, body, digest in _migrations()[:8]:
            c.execute(body)
            c.execute("INSERT INTO nima.schema_migrations VALUES (%s,%s)", (version, digest))
        run = uuid4()
        c.execute(
            "INSERT INTO nima.ingest_runs "
            "(run_id,query,connector_version,normalizer_version,archive_root) "
            "VALUES (%s,%s,%s,%s,%s)",
            (run, Jsonb({}), "synthetic", "synthetic", "/synthetic"),
        )
        c.execute(
            "INSERT INTO nima_processing.replay_batches "
            "(replay_sha256,source_run_id,normalizer_version,manifest,page_count,"
            "normalized_count,quarantined_count) VALUES (%s,%s,%s,%s,1,0,0)",
            ("a" * 64, run, "synthetic", Jsonb({})),
        )
        history = c.execute(
            "SELECT version,sha256 FROM nima.schema_migrations ORDER BY version"
        ).fetchall()
        before = c.execute("SELECT to_jsonb(b) FROM nima_processing.replay_batches b").fetchall()
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        assert (
            c.execute(
                "SELECT version,sha256 FROM nima.schema_migrations "
                "WHERE version<=8 ORDER BY version"
            ).fetchall()
            == history
        )
        assert (
            c.execute("SELECT to_jsonb(b) FROM nima_processing.replay_batches b").fetchall()
            == before
        )
