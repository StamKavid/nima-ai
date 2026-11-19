"""Retirement is an immutable operator decision, never completed coverage."""

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from nima.storage import postgres
from nima.storage.refresh_lifecycle import retire
from nima.storage.workflows import RequestStore, WorkflowError
from tests.test_collection import QUERY
from tests.test_connection import migration_owner
from tests.test_graph_support import database_snapshot
from tests.test_refresh_store import DAY, new_policy


def test_retire_preserves_gaps_requests_and_original_budget(pg_dsn: str, tmp_path: Path) -> None:
    store, policy = new_policy(pg_dsn, tmp_path / "raw")
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(DAY)
        assert cycle is not None
        session.children(cycle)
    before = database_snapshot(pg_dsn)
    result = retire(pg_dsn, policy, "budget_exhausted")
    assert result["retired"] is True and result["reused"] is False
    assert result["schedule_reconciliation"] == "required"
    assert "database_principal" not in result and str(tmp_path) not in str(result)
    after = database_snapshot(pg_dsn)
    for table in before.keys() - {"refresh_policies", "refresh_events", "refresh_retirements"}:
        assert after[table] == before[table]
    repeated = retire(pg_dsn, policy, "budget_exhausted")
    assert repeated == {**result, "reused": True}
    assert database_snapshot(pg_dsn) == after
    with pytest.raises(WorkflowError, match="^retirement_conflict$"):
        retire(pg_dsn, policy, "operator_stop")
    assert database_snapshot(pg_dsn) == after


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE", "CASCADE"])
def test_owner_cannot_rewrite_or_truncate_retirement(
    pg_dsn: str, tmp_path: Path, operation: str
) -> None:
    _, policy = new_policy(pg_dsn, tmp_path / "raw")
    retire(pg_dsn, policy, "operator_stop")
    statements = {
        "UPDATE": "UPDATE nima.refresh_retirements SET reason=reason",
        "DELETE": "DELETE FROM nima.refresh_retirements",
        # The successor FK requires CASCADE before PostgreSQL reaches the triggers.
        "TRUNCATE": "TRUNCATE nima.refresh_retirements CASCADE",
        "CASCADE": "TRUNCATE nima.refresh_policies CASCADE",
    }
    with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        c.execute(statements[operation])


def test_effective_actor_and_time_are_stamped_even_when_caller_supplies_values(
    pg_dsn: str, tmp_path: Path
) -> None:
    with migration_owner(pg_dsn) as owner:
        dsn = make_conninfo(pg_dsn, options="-c role=" + owner)
        _, policy = new_policy(dsn, tmp_path / "raw")
        with psycopg.connect(dsn) as c:
            before = c.execute("SELECT clock_timestamp()").fetchone()
            c.execute(
                "INSERT INTO nima.refresh_retirements "
                "(policy_id,reason,recorded_at,database_principal) "
                "VALUES (%s,'operator_stop','2000-01-01','forged')",
                (policy,),
            )
            result = c.execute(
                "SELECT recorded_at,database_principal,clock_timestamp(),session_user "
                "FROM nima.refresh_retirements"
            ).fetchone()
        assert before is not None and result is not None
        assert before[0] <= result[0] <= result[2]
        assert result[1] == owner and result[1] != result[3]


def test_paused_retirement_needs_no_new_engine_ack_and_rollback_is_atomic(
    pg_dsn: str, tmp_path: Path
) -> None:
    _, policy = new_policy(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "INSERT INTO nima.refresh_retirements(policy_id,reason) VALUES (%s,'operator_stop')",
            (policy,),
        )
        c.rollback()
    assert database_snapshot(pg_dsn) == before
    assert retire(pg_dsn, policy, "operator_stop")["schedule_reconciliation"] == "last_acknowledged"


def test_policy_lock_and_fixed_invalid_input_never_leave_a_decision(
    pg_dsn: str, tmp_path: Path
) -> None:
    store, policy = new_policy(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    with store.lease(policy), pytest.raises(WorkflowError, match="^policy_busy$"):
        retire(pg_dsn, policy, "operator_stop")
    with pytest.raises(WorkflowError, match="^retirement_reason$"):
        retire(pg_dsn, policy, "private-sentinel")
    with pytest.raises(WorkflowError, match="^policy_unavailable$"):
        retire(pg_dsn, uuid4(), "operator_stop")
    assert database_snapshot(pg_dsn) == before


def test_narrow_nonowner_operator_needs_no_source_write_privilege(
    pg_dsn: str, tmp_path: Path
) -> None:
    _, policy = new_policy(pg_dsn, tmp_path / "raw")
    role = "nima_retire_test_" + uuid4().hex
    with psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        try:
            admin.execute(
                sql.SQL("""
                GRANT USAGE ON SCHEMA nima TO {role};
                GRANT SELECT ON nima.schema_migrations,nima.refresh_policies,
                    nima.refresh_retirements TO {role};
                GRANT UPDATE(state) ON nima.refresh_policies TO {role};
                GRANT INSERT ON nima.refresh_retirements,nima.refresh_events TO {role};
                GRANT USAGE ON SEQUENCE nima.refresh_events_event_id_seq TO {role}
                """).format(role=sql.Identifier(role))
            )
            limited = make_conninfo(pg_dsn, user=role)
            assert retire(limited, policy, "operator_stop")["retired"] is True
            assert admin.execute(
                "SELECT database_principal FROM nima.refresh_retirements"
            ).fetchone() == (role,)
            with psycopg.connect(limited) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("INSERT INTO nima.raw_objects VALUES (repeat('a',64),1)")
        finally:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_upgrade_ten_preserves_every_existing_table_and_checksum(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations = postgres._migrations()
    assert [item[0] for item in migrations] == list(range(1, 13))
    with monkeypatch.context() as patch:
        patch.setattr(postgres, "_migrations", lambda: migrations[:10])
        _, policy = new_policy(pg_dsn, tmp_path / "raw")
        RequestStore(pg_dsn).submit(uuid4(), QUERY, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    assert len(before) == 26
    postgres.migrate(pg_dsn)
    postgres.migrate(pg_dsn)
    after = database_snapshot(pg_dsn)
    assert len(after) == 28 and after["refresh_retirements"] == []
    for table in before.keys() - {"schema_migrations"}:
        assert after[table] == before[table]
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT version,sha256 FROM nima.schema_migrations WHERE version<=10 ORDER BY version"
        ).fetchall() == [(v, digest) for v, _, digest in migrations[:10]]
        assert c.execute(
            "SELECT has_table_privilege('public','nima.refresh_retirements','INSERT')"
        ).fetchone() == (False,)
        assert (
            c.execute(
                "SELECT policy_id FROM nima.refresh_policies WHERE policy_id=%s", (policy,)
            ).fetchone()
            is not None
        )
