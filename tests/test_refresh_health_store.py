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
    # The wrapper keeps a real reader transaction open across a separate commit.
    from datetime import date
    from uuid import UUID

    from nima.storage.connection import Connection
    from nima.storage.refresh import missing_dates as original

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


def test_server_enforces_readonly_transaction_and_timeouts(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import date
    from uuid import UUID

    from nima.dataops import refresh_health_store as adapter
    from nima.storage.connection import Connection
    from nima.storage.refresh import missing_dates as original

    _, policy, _ = child(pg_dsn, tmp_path / "raw")

    def inspect(c: Connection, policy_id: UUID, start: date, end: date) -> tuple[date, ...]:
        assert c.execute("""SELECT current_setting('transaction_read_only'),
            current_setting('transaction_isolation'),current_setting('statement_timeout'),
            current_setting('lock_timeout'),current_setting('row_security')""").fetchone() == (
            "on",
            "repeatable read",
            "5s",
            "2s",
            "off",
        )
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction), c.transaction():
            c.execute("UPDATE nima.refresh_policies SET last_tick_at=clock_timestamp()")
        return original(c, policy_id, start, end)

    monkeypatch.setattr(adapter, "missing_dates", inspect)
    assert read_snapshot(pg_dsn, policy).policy_id == policy


@pytest.mark.parametrize("oversized", [False, True])
def test_configuration_is_bounded_before_decode_and_hash_checked(
    pg_dsn: str,
    tmp_path: Path,
    oversized: bool,
) -> None:
    from psycopg.types.json import Jsonb

    _, policy, _ = child(pg_dsn, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        c.execute("ALTER TABLE nima.refresh_policies DISABLE TRIGGER refresh_policy_identity")
        if oversized:
            c.execute(
                "UPDATE nima.refresh_policies SET configuration=configuration || %s",
                (Jsonb({"private_marker": "x" * 20000}),),
            )
        else:
            c.execute("UPDATE nima.refresh_policies SET configuration_sha256=repeat('0',64)")
    expected = "refresh_health_limit" if oversized else "refresh_health_evidence"
    with reader(pg_dsn) as dsn, pytest.raises(HealthError, match=f"^{expected}$"):
        read_snapshot(dsn, policy)


def test_open_cycle_cannot_be_hidden_by_a_later_completed_cycle(
    pg_dsn: str, tmp_path: Path
) -> None:
    _, policy, _ = child(pg_dsn, tmp_path / "raw")
    before = read_snapshot(pg_dsn, policy)
    assert before.cycle is not None
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            """INSERT INTO nima.refresh_cycles
            (cycle_id,policy_id,business_date,query_dates,completed_at)
            SELECT %s,policy_id,business_date+1,query_dates,clock_timestamp()
            FROM nima.refresh_cycles WHERE cycle_id=%s""",
            (uuid4(), before.cycle.cycle_id),
        )
    with reader(pg_dsn) as dsn:
        after = read_snapshot(dsn, policy)
    assert after.cycle == before.cycle


def test_fifteenth_child_refuses_instead_of_publishing_truncated_health(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    from datetime import timedelta

    from tests.test_refresh_store import DAY, new_policy

    store, policy = new_policy(pg_dsn, tmp_path / "raw", start=DAY - timedelta(days=30))
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None and len(session.children(cycle)) == 14
    with psycopg.connect(pg_dsn) as c:
        request = uuid4()
        c.execute(
            """INSERT INTO nima.workflow_requests(request_id,parameters,parameters_sha256)
            SELECT %s,parameters,parameters_sha256 FROM nima.workflow_requests LIMIT 1""",
            (request,),
        )
        c.execute(
            """INSERT INTO nima.refresh_windows(cycle_id,policy_id,query_date,request_id)
            VALUES(%s,%s,%s,%s)""",
            (cycle.cycle_id, policy, DAY - timedelta(days=31), request),
        )
    with reader(pg_dsn) as dsn, pytest.raises(HealthError, match="^refresh_health_evidence$"):
        read_snapshot(dsn, policy)


def test_row_security_cannot_silently_hide_the_open_cycle(pg_dsn: str, tmp_path: Path) -> None:
    _, policy, _ = child(pg_dsn, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        c.execute("ALTER TABLE nima.refresh_cycles ENABLE ROW LEVEL SECURITY")
        c.execute(
            "CREATE POLICY hide_refresh_cycles ON nima.refresh_cycles FOR SELECT USING(false)"
        )
    with reader(pg_dsn) as dsn, pytest.raises(HealthError, match="^refresh_health_database$"):
        read_snapshot(dsn, policy)
