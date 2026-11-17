"""Public database connection settings shared by new adapters and legacy callers."""

import psycopg

type Connection = psycopg.Connection[tuple[object, ...]]


def connect(dsn: str) -> Connection:
    return psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=5,
        options="-c statement_timeout=30000 -c lock_timeout=5000",
    )
