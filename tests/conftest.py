"""Database tests create only their own disposable databases on local PostgreSQL."""

import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


@pytest.fixture
def pg_dsn() -> Iterator[str]:
    dsn = os.environ.get("NIMA_TEST_DSN", "")
    config = conninfo_to_dict(dsn)
    if (
        config.get("host") not in {"127.0.0.1", "localhost", "::1"}
        or config.get("dbname") != "nima_test"
    ):
        pytest.fail("Set NIMA_TEST_DSN to a disposable local database named nima_test")
    database = f"nima_test_{uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            yield make_conninfo(dsn, dbname=database)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
