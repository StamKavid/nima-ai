"""Migration 0013: statement-level TRUNCATE guards on the fifteen older evidence tables."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from nima.dataops import access_audit as aa
from nima.dataops import access_audit_store as store
from nima.dataops import access_contract as ac
from nima.storage import postgres
from nima.storage.postgres import migrate
from tests.test_access_audit_store import apply_printed_grants, new_role
from tests.test_graph_support import database_snapshot
from tests.test_participation import seed
from tests.test_refresh_succession_store import retired

OLDER_EVIDENCE = (
    "raw_objects",
    "run_pages",
    "record_versions",
    "observations",
    "quarantine",
    "projection_contracts",
    "projection_mentions",
    "projection_receipts",
    "gemi_imports",
    "gemi_responses",
    "gemi_profile_versions",
    "gemi_observations",
    "refresh_events",
    "identity_entities",
    "identity_review_events",
)
IMMUTABLE = "Evidence rows are immutable"


def test_every_evidence_table_is_classified_as_truncate_guarded() -> None:
    evidence = {n for n, r in ac.table_rules().items() if r.kind is ac.TableKind.EVIDENCE}
    guarded = {n for n, r in ac.table_rules().items() if r.truncate_guarded}
    assert len(evidence) == 28 and guarded == evidence
    assert {f"nima.{t}" for t in OLDER_EVIDENCE} <= guarded


def test_migration_list_and_new_file_are_additive_triggers_only() -> None:
    migrations = postgres._migrations()
    assert [v for v, _, _ in migrations] == list(range(1, 16))
    body = files("nima.storage").joinpath("migrations/0013.sql").read_text()
    statements = [s.strip() for s in re.sub(r"--[^\n]*", "", body).split(";") if s.strip()]
    pattern = re.compile(
        r"^CREATE TRIGGER (\w+)_no_truncate BEFORE TRUNCATE ON nima\.(\w+)\s+"
        r"FOR EACH STATEMENT EXECUTE FUNCTION nima\.reject_mutation\(\)$"
    )
    matched = [pattern.match(" ".join(s.split())) for s in statements]
    assert all(matched), "0013 may contain only the TRUNCATE guard triggers"
    assert {m.group(2) for m in matched if m} == set(OLDER_EVIDENCE)
    assert all(m.group(1) == m.group(2) for m in matched if m)
    assert len(statements) == 15


@contextmanager
def overprivileged_role(dsn: str) -> Iterator[str]:
    """A runtime role wrongly holding TRUNCATE on every Nima table."""
    with psycopg.connect(dsn, autocommit=True) as c:
        role = new_role(c)
        try:
            for schema in ("nima", "nima_processing", "nima_validation"):
                c.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(role)
                    )
                )
                c.execute(
                    sql.SQL("GRANT TRUNCATE, SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                        sql.Identifier(schema), sql.Identifier(role)
                    )
                )
            yield role
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.parametrize("table", OLDER_EVIDENCE)
def test_cascade_truncate_is_rejected_for_the_owner_and_an_overprivileged_role(
    pg_dsn: str, tmp_path: Path, table: str
) -> None:
    """TRUNCATE ... CASCADE is the form that wiped evidence before 0013 (the guard fires
    because the evidence table itself is truncated, whatever the foreign keys say)."""
    migrate(pg_dsn)
    seed(pg_dsn, tmp_path / "raw", "first")
    before = database_snapshot(pg_dsn)
    statement = sql.SQL("TRUNCATE nima.{} CASCADE").format(sql.Identifier(table))
    with (
        psycopg.connect(pg_dsn) as c,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match=IMMUTABLE),
    ):
        c.execute(statement)
    with overprivileged_role(pg_dsn) as role, psycopg.connect(pg_dsn) as c:
        c.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match=IMMUTABLE):
            c.execute(statement)
    assert database_snapshot(pg_dsn) == before


@pytest.mark.parametrize("table", OLDER_EVIDENCE)
def test_plain_truncate_never_succeeds(pg_dsn: str, tmp_path: Path, table: str) -> None:
    """PostgreSQL refuses a plain TRUNCATE of a referenced table before any trigger runs;
    unreferenced tables reach the new guard. Either way nothing is removed."""
    migrate(pg_dsn)
    seed(pg_dsn, tmp_path / "raw", "first")
    before = database_snapshot(pg_dsn)
    with (
        psycopg.connect(pg_dsn) as c,
        pytest.raises(
            (psycopg.errors.FeatureNotSupported, psycopg.errors.ObjectNotInPrerequisiteState)
        ),
    ):
        c.execute(sql.SQL("TRUNCATE nima.{}").format(sql.Identifier(table)))
    assert database_snapshot(pg_dsn) == before


def test_cascade_from_an_unguarded_parent_cannot_wipe_a_guarded_child(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    seed(pg_dsn, tmp_path / "raw", "first")
    before = database_snapshot(pg_dsn)
    with (
        psycopg.connect(pg_dsn) as c,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match=IMMUTABLE),
    ):
        c.execute("TRUNCATE nima.ingest_runs CASCADE")
    assert database_snapshot(pg_dsn) == before


def test_update_and_delete_are_still_rejected(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    seed(pg_dsn, tmp_path / "raw", "first")
    for statement in ("DELETE FROM nima.raw_objects", "UPDATE nima.observations SET run_id=run_id"):
        with (
            psycopg.connect(pg_dsn) as c,
            pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match=IMMUTABLE),
        ):
            c.execute(statement)


def acl(dsn: str) -> list[tuple[object, ...]]:
    with psycopg.connect(dsn) as c:
        return c.execute(
            "SELECT c.relname, c.relowner::regrole::text, c.relacl::text FROM pg_class c "
            "WHERE c.relnamespace IN ('nima'::regnamespace, 'nima_processing'::regnamespace, "
            "'nima_validation'::regnamespace) AND c.relkind='r' ORDER BY 1"
        ).fetchall()


def test_upgrade_from_twelve_preserves_every_row_owner_and_grant(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrations = postgres._migrations()
    assert len(migrations) == 15
    with monkeypatch.context() as patch:
        patch.setattr(postgres, "_migrations", lambda: migrations[:12])
        retired(pg_dsn, tmp_path / "raw")
        seed(pg_dsn, tmp_path / "raw2", "first", "second")
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            role = new_role(c)
            apply_printed_grants(c, "analytics-reader", role)
    before, before_acl = database_snapshot(pg_dsn), acl(pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT max(version) FROM nima.schema_migrations").fetchone() == (12,)
    migrate(pg_dsn)
    migrate(pg_dsn)  # idempotent: a second application changes nothing
    after = database_snapshot(pg_dsn)
    assert all(after[t] == before[t] for t in before.keys() - {"schema_migrations"})
    after_acl = acl(pg_dsn)
    added = [
        row
        for row in after_acl
        if str(row[0]).startswith("gemi_search_")
        or row[0] in {"acceptance_attempts", "acceptance_outcomes"}
    ]
    assert [row for row in after_acl if row not in added] == before_acl
    # 0014 adds four tables; 0015 adds two with explicit PUBLIC revocation.
    # Existing ACLs stay exact and no new table grants rights beyond its owner.
    assert len(added) == 6
    assert all(row[2] is None for row in added if str(row[0]).startswith("gemi_search_"))
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a "
            "WHERE c.relnamespace='nima_validation'::regnamespace "
            "AND c.relname IN ('acceptance_attempts','acceptance_outcomes') "
            "AND (a.grantee<>c.relowner OR a.grantor<>c.relowner)"
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT version,sha256 FROM nima.schema_migrations ORDER BY version"
        ).fetchall() == [(v, h) for v, _, h in migrations]
        triggers = c.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname LIKE '%\\_no\\_truncate' "
            "AND NOT tgisinternal"
        ).fetchone()
    assert triggers == (28,)  # seven existing, fifteen from 0013, four from 0014, two from 0015
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
        c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def audit(dsn: str, role: str) -> aa.AuditResult:
    return aa.assess(store.read_snapshot(dsn, role), "analytics-reader")


def test_audit_passes_with_an_empty_limitation_list(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        role = new_role(c)
        apply_printed_grants(c, "analytics-reader", role)
        try:
            result = audit(pg_dsn, role)
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
    assert result.passed and result.limitations == ()


@pytest.mark.parametrize("table", OLDER_EVIDENCE)
@pytest.mark.parametrize(
    "change",
    [
        "DROP TRIGGER {t}_no_truncate ON nima.{t}",
        "ALTER TABLE nima.{t} DISABLE TRIGGER {t}_no_truncate",
    ],
)
def test_losing_or_disabling_a_new_guard_is_reported_exactly(
    pg_dsn: str, table: str, change: str
) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        role = new_role(c)
        apply_printed_grants(c, "analytics-reader", role)
        c.execute(change.format(t=table))
        try:
            reasons = [(r.code, r.subject) for r in audit(pg_dsn, role).reasons]
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
    assert reasons == [(aa.ReasonCode.TRUNCATE_TRIGGER_MISSING, f"nima.{table}")]


def test_audit_refuses_a_database_that_has_not_applied_0013(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unmigrated database cannot be audited at all; it is never a partial pass."""
    from nima.dataops.health import HealthError

    migrations = postgres._migrations()
    with monkeypatch.context() as patch:
        patch.setattr(postgres, "_migrations", lambda: migrations[:12])
        migrate(pg_dsn)
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            role = new_role(c)
    with pytest.raises(HealthError, match="^access_audit_unavailable$"):
        store.read_snapshot(pg_dsn, role)
    migrate(pg_dsn)  # once migrated the same role can be audited
    assert store.read_snapshot(pg_dsn, role).role.name == role
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
