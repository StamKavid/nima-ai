"""All 26 authoritative relations; retain the existing 23-table source helper."""

import psycopg
from psycopg import sql

from tests.test_identity_review_support import source_snapshot


def database_snapshot(dsn: str) -> dict[str, list[object]]:
    source = source_snapshot(dsn)
    with psycopg.connect(dsn) as connection:
        return {
            **source,
            **{
                table: [
                    row[0]
                    for row in connection.execute(
                        sql.SQL(
                            "SELECT to_jsonb(r) FROM nima.{} r ORDER BY to_jsonb(r)::text"
                        ).format(sql.Identifier(table))
                    ).fetchall()
                ]
                for table in (
                    "identity_entities",
                    "identity_review_events",
                    "identity_review_heads",
                )
            },
        }
