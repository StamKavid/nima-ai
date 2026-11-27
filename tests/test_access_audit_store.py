"""Actual catalogue reads against disposable migrated databases with real roles."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from nima.dataops import access_audit as aa
from nima.dataops import access_audit_store as store
from nima.dataops import access_contract as ac
from nima.dataops import access_grants as ag
from nima.dataops.access_audit import ReasonCode as R
from nima.dataops.health import HealthError
from nima.storage.connection import Connection
from nima.storage.postgres import migrate
from tests.test_graph_support import database_snapshot


def new_role(c: psycopg.Connection, options: str = "") -> str:
    role = "nima_audit_" + uuid4().hex
    c.execute(sql.SQL("CREATE ROLE {} NOLOGIN " + options).format(sql.Identifier(role)))
    return role


def apply_printed_grants(c: psycopg.Connection, profile: str, role: str) -> None:
    text = ag.render_grants(profile, role)
    c.execute("\n".join(line for line in text.splitlines() if not line.startswith("--")))


@contextmanager
def roles(dsn: str, profile: str | None = None, options: str = "") -> Iterator[str]:
    with psycopg.connect(dsn, autocommit=True) as c:
        role = new_role(c, options)
        try:
            if profile:
                apply_printed_grants(c, profile, role)
            yield role
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def audit(dsn: str, role: str, profile: str) -> list[tuple[R, str, str]]:
    result = aa.assess(store.read_snapshot(dsn, role), profile)
    return [(r.code, r.subject, r.detail) for r in result.reasons]


@pytest.mark.parametrize("profile", sorted(ac.PROFILES))
def test_printed_grants_applied_to_a_real_role_audit_clean(pg_dsn: str, profile: str) -> None:
    migrate(pg_dsn)
    with roles(pg_dsn, profile) as role:
        snapshot = store.read_snapshot(pg_dsn, role)
        assert len(snapshot.tables) == 39 and len(snapshot.sequences) == 3
        assert aa.assess(snapshot, profile).passed


def test_contract_matches_the_migrated_catalogue_exactly(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with roles(pg_dsn) as role:
        snapshot = store.read_snapshot(pg_dsn, role)
    assert {t.name for t in snapshot.tables} == set(ac.table_rules())
    assert {s.name for s in snapshot.sequences} == set(ac.SEQUENCES)
    for table in snapshot.tables:
        rule = ac.table_rules()[table.name]
        if rule.kind is ac.TableKind.EVIDENCE:
            assert aa._has_guard(table, frozenset({"UPDATE", "DELETE"})) is True, table.name
            assert (aa._has_guard(table, frozenset({"TRUNCATE"})) is True) == rule.truncate_guarded


@pytest.mark.parametrize(
    ("grant", "expected"),
    [
        ("GRANT UPDATE ON nima.observations TO {}", (R.EVIDENCE_REWRITE_PRIVILEGE, "UPDATE")),
        ("GRANT DELETE ON nima.raw_objects TO {}", (R.EVIDENCE_REWRITE_PRIVILEGE, "DELETE")),
        ("GRANT TRUNCATE ON nima.run_pages TO {}", (R.EVIDENCE_REWRITE_PRIVILEGE, "TRUNCATE")),
        ("GRANT INSERT ON nima.ingest_runs TO {}", (R.PRIVILEGE_EXCESS, "INSERT")),
        (
            "GRANT UPDATE (next_page) ON nima.ingest_runs TO {}",
            (R.PRIVILEGE_EXCESS, "UPDATE(next_page)"),
        ),
    ],
)
def test_excess_grants_each_produce_their_exact_reason(
    pg_dsn: str, grant: str, expected: tuple[R, str]
) -> None:
    migrate(pg_dsn)
    with roles(pg_dsn, "analytics-reader") as role, psycopg.connect(pg_dsn) as c:
        c.execute(sql.SQL(grant).format(sql.Identifier(role)))
        c.commit()
        reasons = audit(pg_dsn, role, "analytics-reader")
    assert len(reasons) == 1 and (reasons[0][0], reasons[0][2]) == expected


def test_privilege_inherited_through_public_or_a_parent_role_is_counted(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with roles(pg_dsn, "analytics-reader") as role, roles(pg_dsn) as parent:
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            c.execute(
                sql.SQL("GRANT DELETE ON nima.quarantine TO {}").format(sql.Identifier(parent))
            )
            c.execute(
                sql.SQL("GRANT {} TO {}").format(sql.Identifier(parent), sql.Identifier(role))
            )
        assert audit(pg_dsn, role, "analytics-reader") == [
            (R.EVIDENCE_REWRITE_PRIVILEGE, "nima.quarantine", "DELETE")
        ]
    with roles(pg_dsn, "analytics-reader") as role, psycopg.connect(pg_dsn) as c:
        c.execute("GRANT TRUNCATE ON nima.observations TO PUBLIC")
        c.commit()
        try:
            assert (R.EVIDENCE_REWRITE_PRIVILEGE, "nima.observations", "TRUNCATE") in audit(
                pg_dsn, role, "analytics-reader"
            )
        finally:
            c.execute("REVOKE TRUNCATE ON nima.observations FROM PUBLIC")
            c.commit()


@pytest.mark.parametrize(
    ("ddl", "expected"),
    [
        (
            "ALTER TABLE nima.observations DISABLE TRIGGER observations_immutable",
            (R.EVIDENCE_TRIGGER_DISABLED, "nima.observations"),
        ),
        (
            "DROP TRIGGER observations_immutable ON nima.observations",
            (R.EVIDENCE_TRIGGER_MISSING, "nima.observations"),
        ),
        (
            "DROP TRIGGER validation_attempts_no_truncate ON nima_validation.attempts",
            (R.TRUNCATE_TRIGGER_MISSING, "nima_validation.attempts"),
        ),
        ("CREATE TABLE nima.brand_new (x integer)", (R.TABLE_UNCLASSIFIED, "nima.brand_new")),
    ],
)
def test_protection_drift_is_reported_with_its_exact_reason(
    pg_dsn: str, ddl: str, expected: tuple[R, str]
) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(ddl)
    with roles(pg_dsn, "analytics-reader") as role:
        reasons = audit(pg_dsn, role, "analytics-reader")
    assert [(code, subject) for code, subject, _ in reasons] == [expected]


def test_renamed_table_is_both_missing_and_unclassified(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute("ALTER TABLE nima.outbox RENAME TO outbox_moved")
    with roles(pg_dsn, "analytics-reader") as role:
        reasons = audit(pg_dsn, role, "analytics-reader")
    assert [(code, subject) for code, subject, _ in reasons] == [
        (R.TABLE_MISSING, "nima.outbox"),
        (R.TABLE_UNCLASSIFIED, "nima.outbox_moved"),
    ]


@pytest.mark.parametrize(
    ("options", "code"),
    [
        ("CREATEROLE", R.ROLE_CREATEROLE),
        ("CREATEDB", R.ROLE_CREATEDB),
        ("REPLICATION", R.ROLE_REPLICATION),
        ("BYPASSRLS", R.ROLE_BYPASSRLS),
    ],
)
def test_dangerous_role_attributes_are_reported(pg_dsn: str, options: str, code: R) -> None:
    migrate(pg_dsn)
    with roles(pg_dsn, "analytics-reader", options) as role:
        assert [c for c, _s, _d in audit(pg_dsn, role, "analytics-reader")] == [code]


def test_superuser_owner_membership_and_create_rights_are_reported(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        owner = c.execute("SELECT current_user").fetchone()
        database = c.execute("SELECT current_database()").fetchone()
    assert owner is not None and database is not None
    with roles(pg_dsn, "analytics-reader") as role, psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(owner[0]), sql.Identifier(role)))
        c.execute(sql.SQL("GRANT CREATE ON SCHEMA nima TO {}").format(sql.Identifier(role)))
        c.execute(
            sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                sql.Identifier(database[0]), sql.Identifier(role)
            )
        )
        found = {code for code, _s, _d in audit(pg_dsn, role, "analytics-reader")}
    # Membership in the owner (a superuser here) also inherits every privilege, which is
    # reported as well; these three reasons must be present.
    assert {R.ROLE_OWNER_MEMBER, R.ROLE_SCHEMA_CREATE, R.ROLE_DATABASE_CREATE} <= found
    with roles(pg_dsn, "analytics-reader") as role, psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(sql.SQL("ALTER TABLE nima.outbox OWNER TO {}").format(sql.Identifier(role)))
        try:
            assert R.ROLE_OWNS_OBJECTS in {
                c for c, _s, _d in audit(pg_dsn, role, "analytics-reader")
            }
        finally:
            c.execute(
                sql.SQL("ALTER TABLE nima.outbox OWNER TO {}").format(sql.Identifier(owner[0]))
            )
    # The test connection creates databases and BYPASSRLS roles, so it is a superuser.
    assert R.ROLE_SUPERUSER in {c for c, _s, _d in audit(pg_dsn, owner[0], "analytics-reader")}


def test_missing_role_and_unmigrated_database_cannot_pass(pg_dsn: str) -> None:
    with pytest.raises(HealthError, match="^access_audit_unavailable$"):
        store.read_snapshot(pg_dsn, "nima_audit_nobody")
    migrate(pg_dsn)
    with pytest.raises(HealthError, match="^access_audit_unavailable$"):
        store.read_snapshot(pg_dsn, "nima_audit_nobody")


@pytest.mark.parametrize("bad", ["", "x" * 64, "a\x00b"])
def test_invalid_role_argument_is_refused_before_connecting(bad: str) -> None:
    with pytest.raises(HealthError, match="^access_audit_configuration$"):
        store.read_snapshot("host=127.0.0.1 port=1", bad)
    with pytest.raises(HealthError, match="^access_audit_configuration$"):
        store.read_snapshot("  ", "role")


def test_more_than_the_bounded_number_of_tables_or_sequences_is_refused(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute("""DO $$ BEGIN FOR i IN 1..96 LOOP
            EXECUTE format('CREATE TABLE nima.extra_%s (x integer)', i); END LOOP; END $$""")
    with roles(pg_dsn) as role, pytest.raises(HealthError, match="^access_audit_limit$"):
        store.read_snapshot(pg_dsn, role)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute("""DO $$ BEGIN FOR i IN 1..96 LOOP
            EXECUTE format('DROP TABLE nima.extra_%s', i); END LOOP; END $$""")
        c.execute("""DO $$ BEGIN FOR i IN 1..62 LOOP
            EXECUTE format('CREATE SEQUENCE nima.extra_seq_%s', i); END LOOP; END $$""")
    with roles(pg_dsn) as role, pytest.raises(HealthError, match="^access_audit_limit$"):
        store.read_snapshot(pg_dsn, role)


def test_server_enforces_readonly_transaction_and_timeouts(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    original = store.collect

    def inspect(c: Connection, role: str) -> aa.AccessSnapshot:
        assert c.execute("""SELECT current_setting('transaction_read_only'),
            current_setting('transaction_isolation'),current_setting('statement_timeout'),
            current_setting('lock_timeout')""").fetchone() == ("on", "repeatable read", "5s", "2s")
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction), c.transaction():
            c.execute("GRANT SELECT ON nima.outbox TO PUBLIC")
        return original(c, role)

    monkeypatch.setattr(store, "collect", inspect)
    with roles(pg_dsn, "analytics-reader") as role:
        assert aa.assess(store.read_snapshot(pg_dsn, role), "analytics-reader").passed


def test_a_grant_committed_during_the_audit_is_seen_not_hidden(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Privilege functions read the newest committed grants even in a repeatable-read
    transaction, so a concurrent widening is reported rather than missed."""
    migrate(pg_dsn)
    original = store.collect
    with roles(pg_dsn, "analytics-reader") as role:

        def widen(c: Connection, name: str) -> aa.AccessSnapshot:
            with psycopg.connect(pg_dsn, autocommit=True) as other:
                other.execute(
                    sql.SQL("GRANT DELETE ON nima.observations TO {}").format(sql.Identifier(role))
                )
            return original(c, name)

        monkeypatch.setattr(store, "collect", widen)
        assert audit(pg_dsn, role, "analytics-reader") == [
            (R.EVIDENCE_REWRITE_PRIVILEGE, "nima.observations", "DELETE")
        ]


ACL_QUERY = (
    "SELECT relname, relacl::text FROM pg_class "
    "WHERE relnamespace IN ('nima'::regnamespace, 'nima_validation'::regnamespace) ORDER BY 1"
)


def test_the_audit_changes_nothing(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with roles(pg_dsn, "analytics-reader") as role:
        before = database_snapshot(pg_dsn)
        with psycopg.connect(pg_dsn) as c:
            acl = c.execute(ACL_QUERY).fetchall()
        store.read_snapshot(pg_dsn, role)
        with psycopg.connect(pg_dsn) as c:
            assert c.execute(ACL_QUERY).fetchall() == acl
        assert database_snapshot(pg_dsn) == before
