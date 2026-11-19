"""The projector ceiling is proven by running the real drain under exactly its grants."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from nima.dataops import access_audit as aa
from nima.dataops import access_audit_store as store
from nima.dataops import access_contract as ac
from nima.projections.worker import ProjectionFailure, drain
from nima.storage.postgres import MigrationError, migrate
from tests.test_access_audit_store import apply_printed_grants, new_role
from tests.test_participation import counts, seed

EXPECTED_SELECT = {
    "nima.schema_migrations",
    "nima.outbox",
    "nima.observations",
    "nima.record_versions",
    "nima.projection_receipts",
    "nima.projection_contracts",
}
EXPECTED_INSERT = {
    "nima.projection_contracts",
    "nima.projection_mentions",
    "nima.projection_receipts",
}
EVIDENCE_TABLES = (
    "nima.raw_objects",
    "nima.run_pages",
    "nima.record_versions",
    "nima.observations",
    "nima.quarantine",
)


def test_projector_ceiling_is_pinned_and_valid() -> None:
    profile = ac.get_profile("projector")
    ac.validate_contract()
    privileges = dict(profile.table_privileges)
    assert {t for t, p in privileges.items() if ac.Priv.SELECT in p} == EXPECTED_SELECT
    assert {t for t, p in privileges.items() if ac.Priv.INSERT in p} == EXPECTED_INSERT
    assert all(p <= {ac.Priv.SELECT, ac.Priv.INSERT} for p in privileges.values())
    assert profile.column_updates == (("nima.outbox", "delivered_at"),)
    assert profile.sequence_usage == frozenset()
    assert profile.schemas == frozenset({"nima"})


def fingerprint(dsn: str) -> list[object]:
    """Source evidence plus the outbox rows ignoring the delivery stamp the projector owns."""
    queries = [
        f"SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {name} t"
        for name in EVIDENCE_TABLES
    ]
    queries.append(
        "SELECT md5(coalesce(string_agg(o.observation_id::text || o.event_type, '|' "
        "ORDER BY o.observation_id), '')) FROM nima.outbox o"
    )
    with psycopg.connect(dsn) as c:
        return [c.execute(q).fetchone() for q in queries]


@contextmanager
def projector_role(dsn: str, revoke: tuple[str, ...] = ()) -> Iterator[str]:
    with psycopg.connect(dsn, autocommit=True) as c:
        role = new_role(c)
        try:
            apply_printed_grants(c, "projector", role)
            for statement in revoke:
                c.execute(sql.SQL(statement).format(sql.Identifier(role)))
            yield role
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def as_role(dsn: str, role: str) -> str:
    return make_conninfo(dsn, options="-c role=" + role)


def test_real_drain_completes_under_exactly_the_printed_grants(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    seed(pg_dsn, tmp_path / "raw", "first", "second")
    before = fingerprint(pg_dsn)
    with projector_role(pg_dsn) as role:
        assert aa.assess(store.read_snapshot(pg_dsn, role), "projector").passed
        result = drain(as_role(pg_dsn, role))
    assert result["processed_events"] == 2 and result["status"] == "complete"
    contracts, mentions, receipts, delivered = counts(pg_dsn) or ()
    assert (contracts, receipts, delivered) == (2, 2, 2) and mentions == 6
    assert fingerprint(pg_dsn) == before


def revocations() -> list[tuple[str, str]]:
    """Every privilege in the candidate ceiling, as (label, revoke statement)."""
    profile = ac.get_profile("projector")
    out = [("schema usage", "REVOKE USAGE ON SCHEMA nima FROM {}")]
    for table, privs in profile.table_privileges:
        for priv in sorted(privs):
            out.append((f"{priv.value} {table}", f"REVOKE {priv.value} ON {table} FROM {{}}"))
    for table, column in profile.column_updates:
        out.append((f"UPDATE({column}) {table}", f"REVOKE UPDATE ({column}) ON {table} FROM {{}}"))
    for sequence in sorted(profile.sequence_usage):
        out.append((f"USAGE {sequence}", f"REVOKE USAGE ON SEQUENCE {sequence} FROM {{}}"))
    return out


def test_revocation_list_covers_the_whole_ceiling() -> None:
    profile = ac.get_profile("projector")
    expected = 1 + len(EXPECTED_SELECT) + len(EXPECTED_INSERT)
    expected += len(profile.column_updates) + len(profile.sequence_usage)
    assert len(revocations()) == expected


@pytest.mark.parametrize(("label", "statement"), revocations(), ids=lambda v: v)
def test_every_privilege_is_necessary(
    pg_dsn: str, tmp_path: Path, label: str, statement: str
) -> None:
    """Removing any single privilege makes the real drain fail and change nothing."""
    migrate(pg_dsn)
    seed(pg_dsn, tmp_path / "raw", "first")
    before, projected = fingerprint(pg_dsn), counts(pg_dsn)
    with (
        projector_role(pg_dsn, (statement,)) as role,
        pytest.raises((ProjectionFailure, MigrationError, psycopg.Error)),
    ):
        drain(as_role(pg_dsn, role))
    assert counts(pg_dsn) == projected and fingerprint(pg_dsn) == before


def test_projector_cannot_rewrite_evidence_or_other_control_state(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    seed(pg_dsn, tmp_path / "raw", "first")
    denied = [
        "UPDATE nima.observations SET run_id = run_id",
        "DELETE FROM nima.record_versions",
        "TRUNCATE nima.raw_objects",
        "UPDATE nima.outbox SET event_type = event_type",
        "DELETE FROM nima.outbox",
        "INSERT INTO nima.ingest_runs (run_id) VALUES (gen_random_uuid())",
        "UPDATE nima.projection_receipts SET observation_id = observation_id",
        "DELETE FROM nima.projection_contracts",
        "UPDATE nima.workflow_requests SET status = status",
    ]
    before = fingerprint(pg_dsn)
    with projector_role(pg_dsn) as role, psycopg.connect(as_role(pg_dsn, role)) as c:
        for statement in denied:
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                c.execute(statement)
    assert fingerprint(pg_dsn) == before
