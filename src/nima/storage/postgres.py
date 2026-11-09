"""Explicit migrations and atomic page storage; no implicit HTTP resume.

Transaction/parameter patterns: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
and https://www.psycopg.org/psycopg3/docs/basic/params.html .
"""

import hashlib
from importlib.resources import files

import psycopg

type Connection = psycopg.Connection[tuple[object, ...]]


class MigrationError(ValueError):
    """Migration history or database major version is unsupported."""


def _connect(dsn: str) -> Connection:
    return psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=5,
        options="-c statement_timeout=30000 -c lock_timeout=5000",
    )


def migrate(dsn: str) -> None:
    """Apply the packaged additive migration once, with a verified checksum."""
    migration = files("nima.storage").joinpath("migrations/0001.sql").read_text()
    digest = hashlib.sha256(migration.encode()).hexdigest()
    with _connect(dsn) as connection, connection.transaction():
        if connection.info.server_version // 10000 != 17:
            raise MigrationError("This schema is tested on PostgreSQL 17")
        connection.execute("SELECT pg_advisory_xact_lock(812344001, 1)")
        connection.execute("CREATE SCHEMA IF NOT EXISTS nima")
        connection.execute("""CREATE TABLE IF NOT EXISTS nima.schema_migrations (
            version integer PRIMARY KEY, sha256 text NOT NULL)""")
        history = connection.execute(
            "SELECT version, sha256 FROM nima.schema_migrations ORDER BY version"
        ).fetchall()
        if history:
            if history != [(1, digest)]:
                raise MigrationError("Unknown migration version or changed checksum")
            return
        connection.execute(migration)
        connection.execute("INSERT INTO nima.schema_migrations VALUES (1, %s)", (digest,))
