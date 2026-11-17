"""Public database connection settings shared by new adapters and legacy callers."""

import psycopg

type Connection = psycopg.Connection[tuple[object, ...]]


def connect(dsn: str) -> Connection:
    # A keyword `options` replaces libpq startup roles from DSNs/services/environment.
    # Session SET preserves role options: https://www.postgresql.org/docs/17/sql-set.html
    connection = psycopg.connect(dsn, autocommit=True, connect_timeout=5)
    try:
        connection.execute("SET statement_timeout = 30000")
        connection.execute("SET lock_timeout = 5000")
    except BaseException:
        connection.close()
        raise
    return connection
