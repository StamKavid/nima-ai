"""Real SQL/roles and filesystem samples never mutate source data."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from nima.dataops.health import HealthError
from nima.dataops.health_store import read_snapshot, sample_capacity
from nima.projections.worker import PROJECTION_VERSION, drain
from tests.test_analytics_snapshot import state
from tests.test_metadata_export import kimdis_run


@contextmanager
def health_reader(dsn: str) -> Iterator[str]:
    role = "nima_health_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT").format(
                sql.Identifier(role)
            )
        )
        try:
            c.execute(sql.SQL("GRANT USAGE ON SCHEMA nima TO {}").format(sql.Identifier(role)))
            c.execute(
                sql.SQL(
                    "GRANT SELECT ON nima.schema_migrations,nima.ingest_runs,nima.run_pages,"
                    "nima.observations,nima.projection_receipts,nima.workflow_requests TO {}"
                ).format(sql.Identifier(role))
            )
            yield make_conninfo(dsn, options="-c role=" + role)
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_limited_readonly_snapshot_reports_projection_backlog_without_mutation(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = kimdis_run(pg_dsn, tmp_path / "archive")
    before = state(pg_dsn)
    with health_reader(pg_dsn) as dsn:
        sample = read_snapshot(dsn, run)
        assert sample.run_id == run and sample.status == "complete"
        assert sample.page_count == sample.record_count == sample.observation_count == 1
        assert (
            sample.pending_projection_count == 1 and sample.projection_version == PROJECTION_VERSION
        )
        assert sample.workflow_status is None and sample.workflow_id is None
        assert (
            sample.oldest_observed_at
            == sample.newest_observed_at
            == datetime(2026, 1, 1, tzinfo=UTC)
        )
        assert sample.newest_observed_at is not None
        assert sample.sampled_at > sample.newest_observed_at
        with psycopg.connect(dsn) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM nima.workflow_requests")
    assert state(pg_dsn) == before
    drain(pg_dsn, run_id=run)
    with health_reader(pg_dsn) as dsn:
        assert read_snapshot(dsn, run).pending_projection_count == 0


def test_absent_selected_run_is_not_a_zero_count_success(pg_dsn: str) -> None:
    from nima.storage.postgres import migrate

    migrate(pg_dsn)
    with health_reader(pg_dsn) as dsn, pytest.raises(HealthError, match="^health_unavailable$"):
        read_snapshot(dsn, uuid4())


def test_capacity_uses_available_not_reserved_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "capacity"
    target.mkdir(mode=0o700)
    fake = os.statvfs_result((4096, 1024, 100, 90, 2, 100, 90, 3, 0, 255))
    monkeypatch.setattr(os, "fstatvfs", lambda fd: fake)
    sample = sample_capacity(target)
    assert sample.available_bytes == 2048 and sample.available_inodes == 3
    assert sample.directory == str(target) and sample.sampled_at.utcoffset() is not None
    assert list(target.iterdir()) == []
    monkeypatch.setattr(
        os, "fstatvfs", lambda fd: os.statvfs_result((4096, 1024, 100, 90, 2, 0, 0, 0, 0, 255))
    )
    assert sample_capacity(target).available_inodes is None


@pytest.mark.parametrize("kind", ["missing", "symlink", "public", "invalid_stats"])
def test_capacity_failure_is_not_zero_or_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    target = tmp_path / "capacity"
    if kind != "missing":
        target.mkdir(mode=0o700)
    if kind == "symlink":
        original = target.with_name("original")
        target.rename(original)
        target.symlink_to(original, target_is_directory=True)
    elif kind == "public":
        target.chmod(0o755)
    elif kind == "invalid_stats":
        monkeypatch.setattr(
            os, "fstatvfs", lambda fd: os.statvfs_result((4096, 0, 100, 90, 2, 100, 90, 3, 0, 255))
        )
    with pytest.raises(HealthError, match="^health_capacity$"):
        sample_capacity(target)


def test_server_policy_proves_actual_readonly_repeatable_read_and_timeout(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    run = kimdis_run(pg_dsn, tmp_path / "archive")
    with psycopg.connect(pg_dsn) as c:
        c.execute("ALTER TABLE nima.ingest_runs ENABLE ROW LEVEL SECURITY")
        c.execute("""CREATE POLICY health_transaction_test ON nima.ingest_runs FOR SELECT USING (
            current_setting('transaction_read_only') = 'on'
            AND current_setting('transaction_isolation') = 'repeatable read'
            AND current_setting('statement_timeout') = '5s'
        )""")
    with health_reader(pg_dsn) as dsn:
        assert read_snapshot(dsn, run).status == "complete"
        with psycopg.connect(dsn) as c:
            assert c.execute("SELECT count(*) FROM nima.ingest_runs").fetchone() == (0,)


def test_linked_failed_workflow_is_reported_without_reading_parameters(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    from psycopg.types.json import Jsonb

    run = kimdis_run(pg_dsn, tmp_path / "archive")
    request = uuid4()
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "INSERT INTO nima.workflow_requests "
            "(request_id,parameters,parameters_sha256,run_id,status) "
            "VALUES (%s,%s,%s,%s,%s)",
            (request, Jsonb({"private_marker": "never_log"}), "0" * 64, run, "failed"),
        )
    before = state(pg_dsn)
    with health_reader(pg_dsn) as dsn:
        sample = read_snapshot(dsn, run)
        assert sample.workflow_id == request and sample.workflow_status == "failed"
        assert sample.workflow_updated_at is not None
    assert state(pg_dsn) == before


def test_health_does_not_implicitly_migrate_a_database(pg_dsn: str) -> None:
    with pytest.raises(HealthError, match="^health_schema$"):
        read_snapshot(pg_dsn, uuid4())
