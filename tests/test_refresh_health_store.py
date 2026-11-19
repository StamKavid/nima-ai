"""Actual selected-policy SQL snapshots with a SELECT-only operator role."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from nima.dataops.health import HealthError
from nima.dataops.refresh_health_store import read_snapshot
from nima.storage.postgres import migrate
from tests.test_graph_support import database_snapshot
from tests.test_refresh_recovery_control import child


@contextmanager
def reader(dsn: str) -> Iterator[str]:
    role = "nima_refresh_health_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOINHERIT").format(sql.Identifier(role))
        )
        try:
            c.execute(sql.SQL("GRANT USAGE ON SCHEMA nima TO {}").format(sql.Identifier(role)))
            c.execute(
                sql.SQL(
                    "GRANT SELECT ON nima.schema_migrations,nima.refresh_policies,"
                    "nima.refresh_cycles,nima.refresh_windows,nima.refresh_retirements,"
                    "nima.workflow_requests,nima.workflow_dispatches TO {}"
                ).format(sql.Identifier(role))
            )
            yield make_conninfo(dsn, options="-c role=" + role)
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_reader_reports_open_children_and_gaps_without_mutation(
    pg_dsn: str, tmp_path: Path
) -> None:
    _, policy, request = child(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    with reader(pg_dsn) as dsn:
        sample = read_snapshot(dsn, policy)
        assert sample.policy_id == policy and sample.cycle is not None
        assert sample.missing_days > 0 and len(sample.oldest_missing) == min(7, sample.missing_days)
        assert len(sample.cycle.children) == 2
        selected = next(c for c in sample.cycle.children if c.request_id == request)
        assert selected.dispatch_state == "sending" and selected.budget.dispatches == 1
        with psycopg.connect(dsn) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE nima.refresh_policies SET last_tick_at=clock_timestamp()")
    assert database_snapshot(pg_dsn) == before


def test_absent_policy_and_missing_schema_cannot_become_healthy(pg_dsn: str) -> None:
    with pytest.raises(HealthError, match="^refresh_health_schema$"):
        read_snapshot(pg_dsn, uuid4())
    migrate(pg_dsn)
    with pytest.raises(HealthError, match="^refresh_health_unavailable$"):
        read_snapshot(pg_dsn, uuid4())


def test_missing_cycle_child_is_refused_instead_of_silently_omitted(
    pg_dsn: str, tmp_path: Path
) -> None:
    _, policy, _ = child(pg_dsn, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        c.execute("ALTER TABLE nima.refresh_windows DISABLE TRIGGER refresh_windows_no_delete")
        c.execute(
            "DELETE FROM nima.refresh_windows WHERE query_date="
            "(SELECT min(query_date) FROM nima.refresh_windows)"
        )
    with pytest.raises(HealthError, match="^refresh_health_evidence$"):
        read_snapshot(pg_dsn, policy)


def test_interleaved_commit_cannot_change_child_snapshot(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.dataops import refresh_health_store as adapter

    _, policy, request = child(pg_dsn, tmp_path / "raw")
    original = adapter.missing_dates
    # The wrapper keeps a real reader transaction open across a separate commit.
    from datetime import date
    from uuid import UUID

    from nima.storage.connection import Connection

    def commit(c: Connection, policy_id: UUID, start: date, end: date) -> tuple[date, ...]:
        result = original(c, policy_id, start, end)
        with psycopg.connect(pg_dsn) as other:
            other.execute(
                "UPDATE nima.workflow_requests SET status='failed' WHERE request_id=%s", (request,)
            )
        return result

    monkeypatch.setattr(adapter, "missing_dates", commit)
    with reader(pg_dsn) as dsn:
        result = read_snapshot(dsn, policy)
    assert result.cycle is not None
    assert (
        next(c for c in result.cycle.children if c.request_id == request).budget.status == "queued"
    )
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT status FROM nima.workflow_requests WHERE request_id=%s", (request,)
        ).fetchone() == ("failed",)
