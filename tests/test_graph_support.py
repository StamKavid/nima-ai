"""Authoritative relations, including retirement when installed; retain the source helper."""

import psycopg
from psycopg import sql

from tests.test_identity_review_support import source_snapshot


def database_snapshot(dsn: str) -> dict[str, list[object]]:
    source = source_snapshot(dsn)
    with psycopg.connect(dsn) as connection:
        tables: tuple[str, ...] = (
            "identity_entities",
            "identity_review_events",
            "identity_review_heads",
        )
        if connection.execute("SELECT to_regclass('nima.refresh_retirements')").fetchone() != (
            None,
        ):
            tables += ("refresh_retirements",)
        if connection.execute("SELECT to_regclass('nima.refresh_successions')").fetchone() != (
            None,
        ):
            tables += ("refresh_successions",)
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
                for table in tables
            },
        }
