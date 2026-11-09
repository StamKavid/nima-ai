"""Persistence guarantees are exercised against real PostgreSQL, not mocks."""

import psycopg
import pytest

from nima.storage.postgres import MigrationError, migrate


def test_migration_is_repeatable_and_checksum_verified(pg_dsn: str) -> None:
    migrate(pg_dsn)
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        assert connection.execute("SELECT count(*) FROM nima.schema_migrations").fetchone() == (1,)
        connection.execute("UPDATE nima.schema_migrations SET sha256 = repeat('0', 64)")
    with pytest.raises(MigrationError):
        migrate(pg_dsn)


def test_migration_rejects_a_newer_schema(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        connection.execute("INSERT INTO nima.schema_migrations VALUES (2, repeat('0', 64))")
    with pytest.raises(MigrationError):
        migrate(pg_dsn)


def test_failed_migration_leaves_no_partial_schema(pg_dsn: str) -> None:
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA nima; CREATE TABLE nima.raw_objects (unrelated int)")
    with pytest.raises(psycopg.errors.DuplicateTable):
        migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        assert connection.execute("SELECT to_regclass('nima.schema_migrations')").fetchone() == (
            None,
        )
