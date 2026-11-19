"""The collector ceiling is proven by running the real collect and resume under its grants."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql

from nima.dataops import access_audit as aa
from nima.dataops import access_audit_store as store
from nima.dataops import access_contract as ac
from nima.ingestion.archive import Archive
from nima.ingestion.collector import RunError, collect
from nima.ingestion.config import Limits, Summary
from nima.ingestion.resume import resume
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.test_access_audit_store import apply_printed_grants, new_role
from tests.test_access_projector import as_role
from tests.test_collection import QUERY, Clock, body

PROFILE = "collector"
EXPECTED_SELECT = {
    "nima.schema_migrations",
    "nima.ingest_runs",
    "nima.http_attempts",
    "nima.run_pages",
    "nima.observations",
}
EXPECTED_INSERT = {
    "nima.ingest_runs",
    "nima.http_attempts",
    "nima.run_pages",
    "nima.observations",
    "nima.raw_objects",
    "nima.source_records",
    "nima.record_versions",
    "nima.outbox",
    "nima.quarantine",
}
# Collection must not be able to rewrite what it has already archived or any other column.
FORBIDDEN = [
    "UPDATE nima.raw_objects SET byte_length = byte_length",
    "DELETE FROM nima.raw_objects",
    "UPDATE nima.run_pages SET page_number = page_number",
    "DELETE FROM nima.run_pages",
    "UPDATE nima.observations SET run_id = run_id",
    "DELETE FROM nima.observations",
    "UPDATE nima.record_versions SET source_id = source_id",
    "DELETE FROM nima.quarantine",
    "UPDATE nima.ingest_runs SET query = query",
    "UPDATE nima.ingest_runs SET run_id = run_id",
    "DELETE FROM nima.ingest_runs",
    "UPDATE nima.http_attempts SET run_id = run_id",
    "UPDATE nima.outbox SET delivered_at = clock_timestamp()",
    "DELETE FROM nima.outbox",
    "INSERT INTO nima.projection_receipts VALUES ('x', 1)",
    "UPDATE nima.workflow_requests SET status = status",
    "TRUNCATE nima.http_attempts",
]


def test_collector_ceiling_is_pinned_and_valid() -> None:
    profile = ac.get_profile(PROFILE)
    ac.validate_contract()
    privileges = dict(profile.table_privileges)
    assert {t for t, p in privileges.items() if ac.Priv.SELECT in p} == EXPECTED_SELECT
    assert {t for t, p in privileges.items() if ac.Priv.INSERT in p} == EXPECTED_INSERT
    assert all(p <= {ac.Priv.SELECT, ac.Priv.INSERT} for p in privileges.values())
    assert profile.schemas == frozenset({"nima"})
    assert profile.sequence_usage == frozenset()


@contextmanager
def collector_role(dsn: str, revoke: tuple[str, ...] = ()) -> Iterator[str]:
    with psycopg.connect(dsn, autocommit=True) as c:
        role = new_role(c)
        try:
            apply_printed_grants(c, PROFILE, role)
            for statement in revoke:
                c.execute(sql.SQL(statement).format(sql.Identifier(role)))
            yield role
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def handler(requests: list[int], pages: int = 2) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requests.append(page)
        return httpx.Response(200, content=body(page=page, total=pages))

    return httpx.MockTransport(handle)


def run_collect(dsn: str, root: Path, requests: list[int], pages: int = 2) -> Summary:
    with httpx.Client(transport=handler(requests, pages)) as client:
        return collect(
            QUERY, Limits(), Archive(root), client=client, clock=Clock(), database_dsn=dsn
        )


def stored(dsn: str) -> dict[str, object]:
    """Committed evidence, checked against values computed from the inputs themselves."""
    with psycopg.connect(dsn) as c:
        return {
            "raw": sorted(r[0] for r in c.execute("SELECT sha256 FROM nima.raw_objects")),
            "pages": c.execute("SELECT count(*) FROM nima.run_pages").fetchone(),
            "records": sorted(r[0] for r in c.execute("SELECT source_id FROM nima.source_records")),
            "versions": c.execute("SELECT count(*) FROM nima.record_versions").fetchone(),
            "observations": c.execute("SELECT count(*) FROM nima.observations").fetchone(),
            "outbox": c.execute("SELECT count(*) FROM nima.outbox").fetchone(),
            "attempts": c.execute(
                "SELECT count(*) FROM nima.http_attempts WHERE state='finished'"
            ).fetchone(),
        }


def expected(pages: int) -> dict[str, object]:
    digests = sorted(hashlib.sha256(body(page=n, total=pages)).hexdigest() for n in range(pages))
    ids = [f"kimdis:TEST-{n}" for n in range(pages)]
    return {
        "raw": digests,
        "pages": (pages,),
        "records": ids,
        "versions": (pages,),
        "observations": (pages,),
        "outbox": (pages,),
        "attempts": (pages,),
    }


def test_real_collect_completes_under_exactly_the_printed_grants(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    requests: list[int] = []
    with collector_role(pg_dsn) as role:
        assert aa.assess(store.read_snapshot(pg_dsn, role), PROFILE).passed
        summary = run_collect(as_role(pg_dsn, role), tmp_path / "raw", requests)
    assert summary.status == "complete" and summary.collection_complete
    assert summary.pages == 2 and summary.normalized == 2 and requests == [0, 1]
    assert stored(pg_dsn) == expected(2)


def test_real_resume_completes_under_the_same_grants(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    archive, run = Archive(tmp_path / "raw"), uuid4()
    first = RunStore(pg_dsn, archive, run, Limits())
    with first.lease():
        first.begin(QUERY)
        first.commit_page(run, body(), observed_at=datetime.now(UTC), owner=first.owner)
    requests: list[int] = []
    with collector_role(pg_dsn) as role, httpx.Client(transport=handler(requests)) as client:
        result = resume(as_role(pg_dsn, role), run, client=client, clock=Clock())
    assert result.status == "complete" and requests == [0, 1]
    assert stored(pg_dsn)["pages"] == (2,) and stored(pg_dsn)["observations"] == (2,)


def revocations() -> list[tuple[str, str]]:
    profile = ac.get_profile(PROFILE)
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
    profile = ac.get_profile(PROFILE)
    expected_count = 1 + len(EXPECTED_SELECT) + len(EXPECTED_INSERT)
    expected_count += len(profile.column_updates) + len(profile.sequence_usage)
    assert len(revocations()) == expected_count


def quarantine_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda _: httpx.Response(200, content=body(total=1, title=42)))


def succeeded(action: object) -> bool:
    """True only if the real operation finished with a complete or quarantined collection."""
    try:
        summary = action() if callable(action) else None
    except (RunError, psycopg.Error):
        return False
    return (
        isinstance(summary, Summary)
        and summary.status in {"complete", "quarantined"}
        and summary.collection_complete
    )


def scenarios(owner_dsn: str, role_dsn: str, root: Path) -> list[bool]:
    """Fresh clean run, fresh run with a quarantined record, and a resume of a prefix."""
    archive, run = Archive(root / "prefix"), uuid4()
    prefix = RunStore(owner_dsn, archive, run, Limits())
    with prefix.lease():  # prepared as the owner, so only the role's own work is judged
        prefix.begin(QUERY)
        prefix.commit_page(run, body(), observed_at=datetime.now(UTC), owner=prefix.owner)

    def fresh() -> Summary:
        return run_collect(role_dsn, root / "clean", [])

    def quarantined() -> Summary:
        with httpx.Client(transport=quarantine_transport()) as client:
            return collect(
                QUERY,
                Limits(),
                Archive(root / "quar"),
                client=client,
                clock=Clock(),
                database_dsn=role_dsn,
            )

    def resumed() -> Summary:
        with httpx.Client(transport=handler([])) as client:
            return resume(role_dsn, run, client=client, clock=Clock())

    return [succeeded(fresh), succeeded(quarantined), succeeded(resumed)]


def test_all_three_real_scenarios_succeed_with_the_full_ceiling(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    with collector_role(pg_dsn) as role:
        assert scenarios(pg_dsn, as_role(pg_dsn, role), tmp_path) == [True, True, True]
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima.quarantine").fetchone() == (1,)


@pytest.mark.parametrize(("label", "statement"), revocations(), ids=lambda v: v)
def test_every_privilege_is_necessary(
    pg_dsn: str, tmp_path: Path, label: str, statement: str
) -> None:
    """Removing any single privilege breaks at least one real collector scenario."""
    migrate(pg_dsn)
    with collector_role(pg_dsn, (statement,)) as role:
        results = scenarios(pg_dsn, as_role(pg_dsn, role), tmp_path)
    assert not all(results), f"{label} was not needed by any scenario"


def test_collector_cannot_rewrite_evidence_or_touch_other_state(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run_collect(pg_dsn, tmp_path / "raw", [])
    before = stored(pg_dsn)
    with collector_role(pg_dsn) as role, psycopg.connect(as_role(pg_dsn, role)) as c:
        for statement in FORBIDDEN:
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                c.execute(statement)
    assert stored(pg_dsn) == before
