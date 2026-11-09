"""Persistence guarantees are exercised against real PostgreSQL, not mocks."""

import hashlib
from importlib.resources import files

import psycopg
import pytest

from nima.storage.postgres import MigrationError, check_schema, migrate


def test_migration_is_repeatable_and_checksum_verified(pg_dsn: str) -> None:
    migrate(pg_dsn)
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        assert connection.execute("SELECT count(*) FROM nima.schema_migrations").fetchone() == (2,)
        connection.execute("UPDATE nima.schema_migrations SET sha256 = repeat('0', 64)")
    with pytest.raises(MigrationError):
        migrate(pg_dsn)


def test_migration_rejects_a_newer_schema(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        connection.execute("INSERT INTO nima.schema_migrations VALUES (3, repeat('0', 64))")
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


def test_populated_v1_upgrades_without_rewriting_old_evidence(pg_dsn: str) -> None:
    original = files("nima.storage").joinpath("migrations/0001.sql").read_text()
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        connection.execute(
            "CREATE SCHEMA nima; CREATE TABLE nima.schema_migrations "
            "(version integer PRIMARY KEY, sha256 text NOT NULL)"
        )
        connection.execute(original)
        connection.execute(
            "INSERT INTO nima.schema_migrations VALUES (1, %s)",
            (hashlib.sha256(original.encode()).hexdigest(),),
        )
        connection.execute("INSERT INTO nima.raw_objects VALUES (repeat('a',64), 123)")
    with pytest.raises(MigrationError):
        check_schema(pg_dsn)
    migrate(pg_dsn)
    check_schema(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT byte_length FROM nima.raw_objects").fetchone() == (123,)
