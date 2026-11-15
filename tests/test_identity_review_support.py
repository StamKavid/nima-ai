"""Complete bounded-fixture state checks, excluding the intended review ledger writes."""

import psycopg
from psycopg import sql


def source_snapshot(dsn: str) -> dict[str, list[object]]:
    tables = (
        "schema_migrations",
        "raw_objects",
        "ingest_runs",
        "run_pages",
        "source_records",
        "record_versions",
        "observations",
        "quarantine",
        "outbox",
        "http_attempts",
        "projection_contracts",
        "projection_mentions",
        "projection_receipts",
        "gemi_imports",
        "gemi_responses",
        "gemi_profile_versions",
        "gemi_observations",
        "workflow_requests",
        "workflow_dispatches",
        "refresh_policies",
        "refresh_events",
        "refresh_cycles",
        "refresh_windows",
    )
    with psycopg.connect(dsn) as connection:
        return {
            table: [
                row[0]
                for row in connection.execute(
                    sql.SQL("SELECT to_jsonb(r) FROM nima.{} r ORDER BY to_jsonb(r)::text").format(
                        sql.Identifier(table)
                    )
                ).fetchall()
            ]
            for table in tables
        }
