"""An explicit approval creates one paused generation, retaining original evidence."""

from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from nima.storage.connection import Connection
from nima.storage.refresh_lifecycle import retire
from nima.storage.refresh_succession import supersede
from nima.storage.workflows import WorkflowError
from tests.test_graph_support import database_snapshot
from tests.test_refresh_store import new_policy


def insert_link(c: Connection, old: UUID, new: UUID, *, authorized: bool = True) -> None:
    c.execute(
        "INSERT INTO nima.refresh_successions "
        "(predecessor_id,successor_id,new_budgets_authorized,budget_profile,"
        "successor_configuration_sha256,authorized_at,database_principal) "
        "VALUES (%s,%s,%s,'nima-refresh-budgets-v1',repeat('0',64),'2000-01-01','forged')",
        (old, new, authorized),
    )


def retired(dsn: str, root: Path) -> tuple[UUID, UUID]:
    _, old = new_policy(dsn, root)
    retire(dsn, old, "operator_stop")
    return old, uuid4()


def test_atomic_fresh_successor_retains_scope_and_original_generation(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.storage.refresh import RefreshStore

    old, new = retired(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    result = supersede(pg_dsn, old, new, authorize_new_budgets=True)
    assert result["successor_state"] == "paused" and result["reused"] is False
    assert result["budget_profile"] == "nima-refresh-budgets-v1"
    assert result["new_budgets_authorized"] is True
    assert result["predecessor_id"] == str(old) and result["successor_id"] == str(new)
    assert "database_principal" not in result and str(tmp_path) not in str(result)
    store = RefreshStore(pg_dsn)
    assert store.options(old) == store.options(new)
    after = database_snapshot(pg_dsn)
    for table in before.keys() - {"refresh_policies", "refresh_events", "refresh_successions"}:
        assert after[table] == before[table]
    assert all(row in after["refresh_policies"] for row in before["refresh_policies"])
    assert len(after["refresh_policies"]) == 2 and len(after["refresh_successions"]) == 1
    assert not (tmp_path / "raw").exists()


def test_reuse_preserves_approval_after_activation_and_runtime_change(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import refresh_succession
    from nima.storage.refresh import RefreshStore

    old, new = retired(pg_dsn, tmp_path / "raw")
    first = supersede(pg_dsn, old, new, authorize_new_budgets=True)
    with RefreshStore(pg_dsn).lease(new) as session:
        session.state("enabled")
    before = database_snapshot(pg_dsn)

    def forbidden(*args: object) -> None:
        pytest.fail("A reused approval was reinterpreted as new work")

    monkeypatch.setattr(refresh_succession, "policy_parameters", forbidden)
    again = supersede(pg_dsn, old, new, authorize_new_budgets=True)
    assert again == {**first, "reused": True, "successor_state": "enabled"}
    assert database_snapshot(pg_dsn) == before


@pytest.mark.parametrize(
    "fault", ["authorization", "same", "existing", "not_retired", "other_target"]
)
def test_invalid_authority_or_identity_leaves_no_partial_successor(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    store, old = new_policy(pg_dsn, tmp_path / "raw")
    new = uuid4()
    expected = "succession_conflict"
    if fault != "not_retired":
        retire(pg_dsn, old, "operator_stop")
    else:
        expected = "succession_not_retired"
    if fault == "same":
        new = old
    elif fault == "existing":
        store.create(new, store.options(old))
    elif fault == "other_target":
        supersede(pg_dsn, old, uuid4(), authorize_new_budgets=True)
    elif fault == "authorization":
        expected = "succession_authorization"
    before = database_snapshot(pg_dsn)
    with pytest.raises(WorkflowError, match="^" + expected + "$"):
        supersede(pg_dsn, old, new, authorize_new_budgets=fault != "authorization")
    assert database_snapshot(pg_dsn) == before


@pytest.mark.parametrize("operation", ["update", "delete", "truncate", "cascade"])
def test_authorization_is_immutable_even_for_owner(
    pg_dsn: str, tmp_path: Path, operation: str
) -> None:
    old, new = retired(pg_dsn, tmp_path / "raw")
    supersede(pg_dsn, old, new, authorize_new_budgets=True)
    statements = {
        "update": "UPDATE nima.refresh_successions SET budget_profile=budget_profile",
        "delete": "DELETE FROM nima.refresh_successions",
        "truncate": "TRUNCATE nima.refresh_successions",
        "cascade": "TRUNCATE nima.refresh_policies CASCADE",
    }
    with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        c.execute(statements[operation])


@pytest.mark.parametrize("authorized", [1, "yes"])
def test_truthy_values_are_not_explicit_boolean_authorization(authorized: bool) -> None:
    with pytest.raises(WorkflowError, match="^succession_authorization$"):
        supersede("invalid-private-config", uuid4(), uuid4(), authorize_new_budgets=authorized)


@pytest.mark.parametrize(
    "fault", ["authorization", "buyers", "enabled", "prior_enabled", "tick", "cycle", "retired"]
)
def test_database_rejects_unapproved_or_used_or_different_scope_target(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    from nima.orchestration.refresh import Policy
    from nima.storage.refresh import RefreshStore
    from tests.test_refresh_store import DAY

    old, new = retired(pg_dsn, tmp_path / "raw")
    store = RefreshStore(pg_dsn)
    policy = store.options(old)
    store.create(new, Policy(policy.start, ("22",), policy.root) if fault == "buyers" else policy)
    if fault in {"enabled", "prior_enabled"}:
        with store.lease(new) as session:
            session.state("enabled")
            if fault == "prior_enabled":
                session.state("paused")
    elif fault == "retired":
        retire(pg_dsn, new, "operator_stop")
    elif fault in {"tick", "cycle"}:
        with psycopg.connect(pg_dsn) as c:
            if fault == "tick":
                c.execute(
                    "UPDATE nima.refresh_policies SET last_tick_at=clock_timestamp() "
                    "WHERE policy_id=%s",
                    (new,),
                )
            else:
                c.execute(
                    "INSERT INTO nima.refresh_cycles "
                    "(cycle_id,policy_id,business_date,query_dates) VALUES (%s,%s,%s,%s)",
                    (uuid4(), new, DAY, [DAY]),
                )
    expected = (
        psycopg.errors.CheckViolation
        if fault == "authorization"
        else psycopg.errors.ObjectNotInPrerequisiteState
    )
    before = database_snapshot(pg_dsn)
    with psycopg.connect(pg_dsn) as c, pytest.raises(expected):
        insert_link(c, old, new, authorized=fault != "authorization")
    assert database_snapshot(pg_dsn) == before


def test_database_overwrites_forged_actor_time_and_configuration_hash(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.storage.refresh import RefreshStore

    old, new = retired(pg_dsn, tmp_path / "raw")
    store = RefreshStore(pg_dsn)
    store.create(new, store.options(old))
    with psycopg.connect(pg_dsn) as c:
        before = c.execute("SELECT clock_timestamp()").fetchone()
        insert_link(c, old, new)
        row = c.execute(
            "SELECT s.database_principal,current_user,s.authorized_at,clock_timestamp(),"
            "s.successor_configuration_sha256,p.configuration_sha256 "
            "FROM nima.refresh_successions s "
            "JOIN nima.refresh_policies p ON p.policy_id=s.successor_id"
        ).fetchone()
    assert row is not None and before is not None
    assert row[0] == row[1] and before[0] <= row[2] <= row[3] and row[4] == row[5]


def test_upgrade_eleven_keeps_all_original_rows_and_checksums(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import postgres

    migrations = postgres._migrations()
    assert [v for v, _, _ in migrations] == list(range(1, 13))
    with monkeypatch.context() as patch:
        patch.setattr(postgres, "_migrations", lambda: migrations[:11])
        retired(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    assert len(before) == 27
    postgres.migrate(pg_dsn)
    postgres.migrate(pg_dsn)
    after = database_snapshot(pg_dsn)
    assert len(after) == 28 and after["refresh_successions"] == []
    assert all(after[t] == before[t] for t in before.keys() - {"schema_migrations"})
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT version,sha256 FROM nima.schema_migrations WHERE version<=11 ORDER BY version"
        ).fetchall() == [(v, h) for v, _, h in migrations[:11]]


def test_narrow_nonowner_can_authorize_without_source_write_privilege(
    pg_dsn: str, tmp_path: Path
) -> None:
    old, new = retired(pg_dsn, tmp_path / "raw")
    role = "nima_succession_test_" + uuid4().hex
    with psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        try:
            admin.execute(
                sql.SQL("""
                GRANT USAGE ON SCHEMA nima TO {role};
                GRANT SELECT ON nima.schema_migrations,nima.refresh_policies,
                    nima.refresh_retirements,
                    nima.refresh_successions,nima.refresh_events,nima.refresh_cycles TO {role};
                GRANT UPDATE(state) ON nima.refresh_policies TO {role};
                GRANT INSERT ON nima.refresh_policies,nima.refresh_events,
                    nima.refresh_successions TO {role};
                GRANT USAGE ON SEQUENCE nima.refresh_events_event_id_seq TO {role}
                """).format(role=sql.Identifier(role))
            )
            assert (
                supersede(make_conninfo(pg_dsn, user=role), old, new, authorize_new_budgets=True)[
                    "successor_state"
                ]
                == "paused"
            )
            assert admin.execute(
                "SELECT database_principal FROM nima.refresh_successions"
            ).fetchone() == (role,)
            with (
                psycopg.connect(make_conninfo(pg_dsn, user=role)) as c,
                pytest.raises(psycopg.errors.InsufficientPrivilege),
            ):
                c.execute("INSERT INTO nima.raw_objects VALUES (repeat('a',64),1)")
        finally:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
