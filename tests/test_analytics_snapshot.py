"""Real limited SQL principals, frozen inputs and unchanged application tables."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

from nima.analytics.snapshot import REQUIRED_TABLES, SnapshotError, read_snapshot
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.projections.worker import drain
from nima.semantics.participation import MetricResult, Observation, evaluate, reference_sql
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.test_collection import QUERY, body
from tests.test_semantics import CUTOFF, TAX


def seed(dsn: str, root: Path, *, empty: bool = False, project: bool = True) -> UUID:
    migrate(dsn)
    run = uuid4()
    store = RunStore(dsn, Archive(root), run, Limits())
    with store.lease():
        store.begin(QUERY)
        raw = body(
            total=0 if empty else 1,
            organization={"key": "B1", "value": "Συνθετικός αγοραστής"},
            totalCostWithoutVAT="1E+2",
            contractingDataDetails={
                "contractingMembersDataList": [
                    {"name": "Synthetic", "vatNumber": TAX, "country": {"key": "EL"}}
                ]
            },
        )
        store.commit_page(run, raw, observed_at=datetime(2026, 1, 1, tzinfo=UTC), owner=store.owner)
        store.finish(Summary(status="complete"))
    if project:
        drain(dsn, run_id=run)
    return run


@contextmanager
def reader(dsn: str) -> Iterator[tuple[str, str]]:
    config = conninfo_to_dict(dsn)
    assert config.get("host") in {"127.0.0.1", "localhost", "::1"}
    database = config.get("dbname")
    assert isinstance(database, str) and database.startswith("nima_test_")
    role = "nima_analytics_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        try:
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA nima TO {}").format(sql.Identifier(role)))
            admin.execute(
                sql.SQL("GRANT SELECT ON {} TO {}").format(
                    sql.SQL(",").join(sql.Identifier("nima", name) for name in REQUIRED_TABLES),
                    sql.Identifier(role),
                )
            )
            yield make_conninfo(dsn, user=role), role
        finally:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def state(dsn: str) -> str:
    digest = hashlib.sha256()
    with psycopg.connect(dsn) as connection:
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='nima' ORDER BY tablename"
        ).fetchall()
        assert len(tables) == 28
        for (name,) in tables:
            row = connection.execute(
                sql.SQL(
                    "SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '[]')::text"
                    " FROM {} t"
                ).format(sql.Identifier("nima", name))
            ).fetchone()
            assert row is not None
            digest.update((name + row[0]).encode())
    return digest.hexdigest()


def test_snapshot_uses_one_closed_readonly_connection_and_preserves_all_tables(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.analytics import snapshot
    from nima.storage.connection import connect

    run = seed(pg_dsn, tmp_path / "archive")
    before = state(pg_dsn)
    connections: list[psycopg.Connection[tuple[object, ...]]] = []

    from nima.semantics import participation

    packaged_sql = participation.reference_sql

    def before_transaction() -> str:
        assert all(connection.closed for connection in connections)
        return packaged_sql()

    monkeypatch.setattr(participation, "reference_sql", before_transaction)

    def tracked(dsn: str) -> psycopg.Connection[tuple[object, ...]]:
        connection = connect(dsn)
        connections.append(connection)
        return connection

    monkeypatch.setattr(snapshot, "connect", tracked)
    with reader(pg_dsn) as (dsn, _):
        result = read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
        assert result.metric.total == 1
        assert result.metric.buyers[0].buyer_key == "kimdis.buyer-key:B1"
        assert len(result.observations) == 1
        assert len(result.input_sha256) == 64
        document = json.loads(result.document_json)
        assert len(document["pages"]) == 1
        assert "archive_root" not in document["runs"][0]
        assert read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF) == result
    assert len(connections) == 2 and all(connection.closed for connection in connections)
    assert state(pg_dsn) == before


def test_owner_is_refused_even_for_an_empty_capture(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive", empty=True)
    with pytest.raises(SnapshotError, match="^analytics_role$"):
        read_snapshot(pg_dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
    with reader(pg_dsn) as (dsn, _):
        result = read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
        assert result.metric.status == "empty_capture"
        assert len(json.loads(result.document_json)["pages"]) == 1


def test_projection_lag_blocks_a_plausible_zero(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive", project=False)
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match="^analytics_projection$"):
        read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
    assert state(pg_dsn) == before


@pytest.mark.parametrize(
    "grant",
    [
        "GRANT UPDATE(normalized) ON nima.record_versions TO {}",
        "GRANT CREATE ON SCHEMA nima TO {}",
        "GRANT TRUNCATE ON nima.observations TO {}",
    ],
)
def test_write_grants_are_refused(pg_dsn: str, tmp_path: Path, grant: str) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, role):
        with psycopg.connect(pg_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL(grant).format(sql.Identifier(role)))
        with pytest.raises(SnapshotError, match="^analytics_role$"):
            read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"status": "failed"}, "analytics_coverage"),
        ({"normalizer_version": "future"}, "analytics_version"),
        ({"next_page": 2}, "analytics_coverage"),
        ({"query": {"dateFrom": "bad", "dateTo": "2026-11-06"}}, "analytics_coverage"),
        ({"query": {}}, "analytics_coverage"),
        ({"query": {"dateFrom": "2026-11-07", "dateTo": "2026-11-06"}}, "analytics_coverage"),
        (
            {"query": {"dateFrom": "2026-11-06", "dateTo": "2026-11-06", "organizations": ["0"]}},
            "analytics_coverage",
        ),
        ({"total_pages": 2}, "analytics_coverage"),
    ],
)
def test_invalid_cohort_metadata_blocks_readout(
    pg_dsn: str,
    tmp_path: Path,
    changes: dict[str, object],
    reason: str,
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    field, value = next(iter(changes.items()))
    with psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("UPDATE nima.ingest_runs SET {}=%s WHERE run_id=%s").format(
                sql.Identifier(field)
            ),
            (Jsonb(value) if field == "query" else value, run),
        )
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match=f"^{reason}$"):
        read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


def test_declared_payload_bound_is_checked_before_transfer(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.analytics import snapshot

    run = seed(pg_dsn, tmp_path / "archive")
    monkeypatch.setattr(snapshot, "MAX_INPUT_BYTES", 1)
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match="^analytics_limit$"):
        read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


@pytest.mark.parametrize("amount", ["101", "NaN"])
def test_corrupt_stored_projection_is_not_hidden_by_a_receipt(
    pg_dsn: str, tmp_path: Path, amount: str
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    # Privileged setup simulates existing corruption; the read principal cannot do this.
    with psycopg.connect(pg_dsn) as admin:
        admin.execute("ALTER TABLE nima.projection_contracts DISABLE TRIGGER USER")
        admin.execute("UPDATE nima.projection_contracts SET net_amount=%s", (amount,))
        admin.execute("ALTER TABLE nima.projection_contracts ENABLE TRIGGER USER")
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match="^analytics_projection$"):
        read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
    assert state(pg_dsn) == before


def test_inherited_write_grant_is_refused(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    group = sql.Identifier("nima_analytics_group_" + uuid4().hex)
    with reader(pg_dsn) as (dsn, role), psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {}").format(group))
        try:
            admin.execute(
                sql.SQL("GRANT UPDATE(normalized) ON nima.record_versions TO {}").format(group)
            )
            admin.execute(sql.SQL("GRANT {} TO {}").format(group, sql.Identifier(role)))
            with pytest.raises(SnapshotError, match="^analytics_role$"):
                read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
        finally:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(group))
            admin.execute(sql.SQL("DROP ROLE {}").format(group))


def test_missing_run_and_missing_read_grant_are_explicit(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, role):
        with pytest.raises(SnapshotError, match="^analytics_coverage$"):
            read_snapshot(dsn, (uuid4(),), tax_id=TAX, cutoff=CUTOFF)
        with psycopg.connect(pg_dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("REVOKE SELECT ON nima.quarantine FROM {}").format(sql.Identifier(role))
            )
        with pytest.raises(SnapshotError, match="^analytics_role$"):
            read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


def test_public_write_and_sequence_grants_are_refused(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, role), psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute("GRANT UPDATE ON nima.ingest_runs TO PUBLIC")
        try:
            with pytest.raises(SnapshotError, match="^analytics_role$"):
                read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
        finally:
            admin.execute("REVOKE UPDATE ON nima.ingest_runs FROM PUBLIC")
        admin.execute(
            sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA nima TO {}").format(
                sql.Identifier(role)
            )
        )
        with pytest.raises(SnapshotError, match="^analytics_role$"):
            read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


def test_empty_capture_page_limit_is_checked_before_payload(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive", empty=True)
    with psycopg.connect(pg_dsn) as admin:
        admin.execute(
            """INSERT INTO nima.run_pages
            SELECT run_id,n,raw_sha256,observed_at,0,0,source_ids
            FROM nima.run_pages CROSS JOIN generate_series(1,32) n WHERE run_id=%s""",
            (run,),
        )
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match="^analytics_limit$"):
        read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


def test_snapshot_remains_consistent_across_concurrent_metadata_change(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.analytics import snapshot
    from nima.storage.connection import Connection

    run = seed(pg_dsn, tmp_path / "archive")
    original = snapshot._preflight

    def concurrent(connection: Connection, parameters: dict[str, object]) -> None:
        original(connection, parameters)
        with psycopg.connect(pg_dsn) as admin:
            admin.execute("UPDATE nima.ingest_runs SET status='failed' WHERE run_id=%s", (run,))

    monkeypatch.setattr(snapshot, "_preflight", concurrent)
    with reader(pg_dsn) as (dsn, _):
        result = read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
        assert json.loads(result.document_json)["runs"][0]["status"] == "complete"
        assert result.metric.total == 1
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT status FROM nima.ingest_runs WHERE run_id=%s", (run,)
        ).fetchone() == ("failed",)


@pytest.mark.parametrize("runs,tax", [((), TAX), ((uuid4(),) * 2, TAX), ((uuid4(),), "bad")])
def test_bad_selections_are_refused_before_connect(runs: tuple[UUID, ...], tax: str) -> None:
    with pytest.raises(SnapshotError, match="^analytics_input$"):
        read_snapshot("not a connection string", runs, tax_id=tax, cutoff=CUTOFF)


def test_unknown_schema_has_a_fixed_error(pg_dsn: str) -> None:
    with pytest.raises(SnapshotError, match="^analytics_schema$"):
        read_snapshot(pg_dsn, (uuid4(),), tax_id=TAX, cutoff=CUTOFF)


def test_driver_errors_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    from nima.analytics import snapshot

    def failed(dsn: str) -> psycopg.Connection[tuple[object, ...]]:
        raise psycopg.OperationalError("private driver details")

    monkeypatch.setattr(snapshot, "connect", failed)
    with pytest.raises(SnapshotError, match="^analytics_database$"):
        read_snapshot("private configuration", (uuid4(),), tax_id=TAX, cutoff=CUTOFF)


def test_disagreement_with_sql_cannot_be_returned_as_a_result(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.analytics import snapshot

    run = seed(pg_dsn, tmp_path / "archive")
    original = reference_sql()
    changed = original.replace("'total', (SELECT count(*) FROM matched)", "'total', 0")
    assert changed != original
    monkeypatch.setattr(snapshot, "reference_sql", lambda: changed)
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match="^analytics_metric$"):
        read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


def test_corrupt_normalized_fields_and_false_empty_metadata_are_refused(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _), psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute("ALTER TABLE nima.record_versions DISABLE TRIGGER USER")
        admin.execute("UPDATE nima.record_versions SET normalized=normalized-'title'")
        admin.execute("ALTER TABLE nima.record_versions ENABLE TRIGGER USER")
        with pytest.raises(SnapshotError, match="^analytics_projection$"):
            read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
        admin.execute(
            "UPDATE nima.ingest_runs SET total_records=0,total_pages=0 WHERE run_id=%s", (run,)
        )
        with pytest.raises(SnapshotError, match="^analytics_coverage$"):
            read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


def test_historical_read_does_not_use_current_storage_version_defaults(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.storage import postgres

    run = seed(pg_dsn, tmp_path / "archive")
    monkeypatch.setattr(postgres, "NORMALIZER_VERSION", "future-default")
    with reader(pg_dsn) as (dsn, _):
        assert read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF).metric.total == 1


def test_disagreement_with_pure_policy_is_also_blocked(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.analytics import snapshot

    run = seed(pg_dsn, tmp_path / "archive")

    def biased(
        observations: tuple[Observation, ...], *, tax_id: str, cutoff: datetime
    ) -> MetricResult:
        result = evaluate(observations, tax_id=tax_id, cutoff=cutoff)
        return replace(result, total=result.total + 1) if observations else result

    monkeypatch.setattr(snapshot, "evaluate", biased)
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match="^analytics_metric$"):
        read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)


@pytest.mark.parametrize("field", ["input_sha256", "metric", "observations", "document_json"])
def test_frozen_snapshot_revalidation_rejects_changed_values(
    pg_dsn: str,
    tmp_path: Path,
    field: str,
) -> None:
    from nima.analytics.snapshot import validate_snapshot

    run = seed(pg_dsn, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _):
        original = read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
    assert validate_snapshot(original, (run,), tax_id=TAX, cutoff=CUTOFF) == json.loads(
        original.document_json
    )
    changes: dict[str, Any] = {
        "input_sha256": "0" * 64,
        "metric": replace(original.metric, total=0),
        "observations": (),
        "document_json": original.document_json + " ",
    }
    with pytest.raises(SnapshotError, match="^analytics_evidence$"):
        validate_snapshot(
            replace(original, **{field: changes[field]}), (run,), tax_id=TAX, cutoff=CUTOFF
        )


def test_snapshot_revalidation_checks_the_expected_definition(pg_dsn: str, tmp_path: Path) -> None:
    from nima.analytics.snapshot import validate_snapshot

    run = seed(pg_dsn, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _):
        snapshot = read_snapshot(dsn, (run,), tax_id=TAX, cutoff=CUTOFF)
    with pytest.raises(SnapshotError, match="^analytics_metric$"):
        validate_snapshot(
            snapshot, (run,), tax_id=TAX, cutoff=CUTOFF, expected_definition_sha256="f" * 64
        )


@pytest.mark.parametrize(
    "document",
    [
        "not json",
        "[]",
        "{}",
        '{"runs":null,"pages":[],"records":[]}',
        '{"runs":[],"pages":[],"records":[1]}',
        json.dumps({"runs": [], "pages": [], "records": [{}] * 501}),
    ],
)
def test_offline_validator_rejects_invalid_snapshot_documents(document: str) -> None:
    from nima.analytics.snapshot import ReadoutSnapshot, validate_snapshot

    empty = evaluate((), tax_id=TAX, cutoff=CUTOFF)
    snapshot = ReadoutSnapshot(document, (), empty, "0" * 64)
    with pytest.raises(SnapshotError, match="^analytics_evidence$"):
        validate_snapshot(snapshot, (uuid4(),), tax_id=TAX, cutoff=CUTOFF)


def test_offline_validator_enforces_its_byte_budget() -> None:
    from nima.analytics.snapshot import MAX_INPUT_BYTES, ReadoutSnapshot, validate_snapshot

    snapshot = ReadoutSnapshot(
        " " * (MAX_INPUT_BYTES + 1), (), evaluate((), tax_id=TAX, cutoff=CUTOFF), "0" * 64
    )
    with pytest.raises(SnapshotError, match="^analytics_limit$"):
        validate_snapshot(snapshot, (uuid4(),), tax_id=TAX, cutoff=CUTOFF)
