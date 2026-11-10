"""Offline registry imports exercise real PostgreSQL evidence and transactions."""

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from nima.ingestion.archive import Archive
from nima.projections.worker import drain
from nima.storage.gemi import import_run
from nima.storage.gemi_archive import ImportFailure
from nima.storage.postgres import PageStore, migrate
from tests.test_collection import QUERY, body
from tests.test_gemi_contracts import profile
from tests.test_gemi_import_archive import archive_run, edit, manifest_path, snapshot


def counts(dsn: str) -> tuple[object, ...] | None:
    with psycopg.connect(dsn) as connection:
        return connection.execute("""SELECT
            (SELECT count(*) FROM nima.gemi_imports),
            (SELECT count(*) FROM nima.gemi_responses),
            (SELECT count(*) FROM nima.gemi_profile_versions),
            (SELECT count(*) FROM nima.gemi_observations),
            (SELECT count(*) FROM nima.outbox)""").fetchone()


def test_atomic_mixed_import_and_verified_replay(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root, retry=True)
    before = snapshot(root)
    first = import_run(pg_dsn, root, run)
    assert not first.reused and (first.profiles, first.not_found) == (1, 1)
    assert counts(pg_dsn) == (1, 3, 1, 2, 0)
    assert import_run(pg_dsn, root, run).reused
    assert counts(pg_dsn) == (1, 3, 1, 2, 0) and snapshot(root) == before
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT manifest FROM nima.gemi_imports").fetchone() == (
            manifest_path(root, run).read_bytes(),
        )
        assert connection.execute("""SELECT
            normalized->'fields'->'reported_afm'->>'value'
            FROM nima.gemi_profile_versions""").fetchone() == ("001234567",)


def test_response_versions_keep_a_b_a_observations(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    for name in ("A", "B", "A"):
        run = archive_run(root, profile(coNameEl=name))
        assert not import_run(pg_dsn, root, run).reused
    assert counts(pg_dsn) == (3, 6, 2, 6, 0)
    with psycopg.connect(pg_dsn) as connection:
        rows = connection.execute("""SELECT
            v.normalized->'fields'->'name_el'->>'value' FROM nima.gemi_observations o
            JOIN nima.gemi_profile_versions v USING (source_id, normalizer_version, raw_sha256)
            ORDER BY o.observed_at""").fetchall()
        assert rows == [("A",), ("B",), ("A",)]


def test_concurrent_identical_imports_converge(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: import_run(pg_dsn, root, run), range(2)))
    assert sorted(r.reused for r in results) == [False, True]
    assert counts(pg_dsn) == (1, 2, 1, 2, 0)


def test_changed_run_manifest_conflicts_without_replacing_history(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root)
    import_run(pg_dsn, root, run)
    original = manifest_path(root, run).read_bytes()
    manifest_path(root, run).write_bytes(json.dumps(json.loads(original)).encode())
    with pytest.raises(ImportFailure, match="import_conflict"):
        import_run(pg_dsn, root, run)
    assert counts(pg_dsn) == (1, 2, 1, 2, 0)


def test_invalid_manifest_commits_no_registry_rows(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root)
    edit(root, run, "summary.found", 9)
    with pytest.raises(ImportFailure):
        import_run(pg_dsn, root, run)
    assert counts(pg_dsn) == (0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "table", ["gemi_imports", "gemi_responses", "gemi_profile_versions", "gemi_observations"]
)
def test_registry_evidence_is_immutable(pg_dsn: str, tmp_path: Path, table: str) -> None:
    from psycopg import sql

    migrate(pg_dsn)
    root = tmp_path / "raw"
    import_run(pg_dsn, root, archive_run(root))
    with (
        psycopg.connect(pg_dsn) as connection,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
    ):
        connection.execute(sql.SQL("DELETE FROM nima.{}").format(sql.Identifier(table)))


def test_stored_assertion_conflict_rejected_for_reuse_and_new_run(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root)
    import_run(pg_dsn, root, run)
    with psycopg.connect(pg_dsn) as connection:
        # Simulate out-of-band administrator corruption in this disposable database.
        connection.execute(
            "ALTER TABLE nima.gemi_profile_versions DISABLE TRIGGER gemi_versions_immutable"
        )
        connection.execute("""UPDATE nima.gemi_profile_versions SET normalized =
            jsonb_set(normalized, '{fields,reported_afm,value}', '"changed"')""")
    for selected in (run, archive_run(root)):
        with pytest.raises(ImportFailure, match="import_conflict"):
            import_run(pg_dsn, root, selected)
        assert counts(pg_dsn) == (1, 2, 1, 2, 0)


def test_replay_verifies_archive_again_and_rejects_relocation(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root)
    import_run(pg_dsn, root, run)
    copied = tmp_path / "copied"
    shutil.copytree(root, copied)
    with pytest.raises(ImportFailure, match="import_conflict"):
        import_run(pg_dsn, copied, run)
    next((root / "objects").glob("*/*.body")).unlink()
    with pytest.raises(ImportFailure, match="archive_invalid"):
        import_run(pg_dsn, root, run)
    assert counts(pg_dsn) == (1, 2, 1, 2, 0)


def test_sql_failure_rolls_back_entire_import(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = archive_run(root)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("""CREATE FUNCTION nima.test_fail() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic private error'; END; $$;
            CREATE TRIGGER test_fail BEFORE INSERT ON nima.gemi_observations
            FOR EACH ROW EXECUTE FUNCTION nima.test_fail();""")
    with pytest.raises(ImportFailure, match="^database$"):
        import_run(pg_dsn, root, run)
    assert counts(pg_dsn) == (0, 0, 0, 0, 0)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.raw_objects").fetchone() == (0,)


def test_schema_upgrade_is_explicit_and_keeps_populated_kimdis_history(
    pg_dsn: str, tmp_path: Path
) -> None:
    with psycopg.connect(pg_dsn) as connection:
        connection.execute(
            "CREATE SCHEMA nima; CREATE TABLE nima.schema_migrations "
            "(version integer PRIMARY KEY, sha256 text NOT NULL)"
        )
        for version in (1, 2, 3):
            original = files("nima.storage").joinpath(f"migrations/{version:04d}.sql").read_text()
            connection.execute(original)
            connection.execute(
                "INSERT INTO nima.schema_migrations VALUES (%s,%s)",
                (version, hashlib.sha256(original.encode()).hexdigest()),
            )
    store = PageStore(pg_dsn, Archive(tmp_path / "kimdis"))
    old = uuid4()
    store.start_run(old, QUERY)
    store.commit_page(old, body(total=1), observed_at=datetime.now(UTC))
    root = tmp_path / "gemi"
    run = archive_run(root)
    with pytest.raises(ImportFailure, match="database_schema"):
        import_run(pg_dsn, root, run)
    migrate(pg_dsn)
    assert import_run(pg_dsn, root, run).profiles == 1
    assert drain(pg_dsn)["processed_events"] == 1
    assert drain(pg_dsn)["processed_events"] == 0
    assert not store.commit_page(old, body(total=1), observed_at=datetime.now(UTC))
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.observations").fetchone() == (1,)
