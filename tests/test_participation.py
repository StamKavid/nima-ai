"""Reported occurrences are not resolved companies or allocated contract spend."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import pytest

from nima.projections.contracts import InvalidProjection, project_contract
from nima.projections.worker import PROJECTION_VERSION, ProjectionFailure, drain
from nima.sources.kimdis import normalize_page
from nima.storage.postgres import _connect
from tests.test_collection import QUERY
from tests.test_kimdis_pages import page_body, record
from tests.test_page_store import store


def joint_record() -> dict[str, object]:
    return {
        **record(),
        "totalCostWithoutVAT": "123456789012345678.90",
        "organization": {"key": "001", "value": "Δήμος δοκιμής"},
        "contractingDataDetails": {
            "contractingMembersDataList": [
                {"name": "ΑΛΦΑ", "vatNumber": "001234567", "country": {"key": "GR"}},
                {"name": "ΒΗΤΑ", "vatNumber": "001234567"},
            ]
        },
    }


def normalized() -> dict[str, object]:
    value = asdict(normalize_page(page_body(joint_record())).contracts[0])
    del value["evidence"]
    value["net_amount"] = str(value["net_amount"])
    return cast(dict[str, object], json.loads(json.dumps(value)))


def seed(dsn: str, path: Path, *titles: str) -> None:
    database = store(dsn, path)
    for title in titles:
        run = uuid4()
        database.start_run(run, QUERY)
        database.commit_page(
            run, page_body({**joint_record(), "title": title}), observed_at=datetime.now(UTC)
        )


def counts(dsn: str) -> tuple[object, ...] | None:
    with psycopg.connect(dsn) as connection:
        return connection.execute("""SELECT
            (SELECT count(*) FROM nima.projection_contracts),
            (SELECT count(*) FROM nima.projection_mentions),
            (SELECT count(*) FROM nima.projection_receipts),
            (SELECT count(*) FROM nima.outbox WHERE delivered_at IS NOT NULL)""").fetchone()


def test_mapping_preserves_occurrences_exact_money_and_unknowns() -> None:
    value = normalized()
    projection = project_contract(value)
    assert projection.net_amount == Decimal("123456789012345678.90")
    assert projection.gross_amount is None and projection.bidder_count is None
    assert projection.supplier_count == 2
    assert [m.name for m in projection.mentions] == ["Δήμος δοκιμής", "ΑΛΦΑ", "ΒΗΤΑ"]
    assert [m.tax_id for m in projection.mentions] == [None, "001234567", "001234567"]
    assert [m.ordinal for m in projection.mentions] == [0, 0, 1]
    assert project_contract({**value, "suppliers": None}).supplier_count is None
    assert project_contract({**value, "suppliers": []}).supplier_count == 0
    assert project_contract({**value, "suppliers": [value["buyer"]] * 1000}).supplier_count == 1000
    assert (
        project_contract(
            {**value, "net_amount": "0", "cancelled": False, "bidder_count": 0}
        ).net_amount
        == 0
    )


@pytest.mark.parametrize(
    "change",
    [
        {"net_amount": 0.1},
        {"net_amount": "NaN"},
        {"net_amount": "Infinity"},
        {"net_amount": "bad"},
        {"title": " "},
        {"title": None},
        {"bidder_count": True},
        {"bidder_count": -1},
        {"cancelled": 1},
        {"buyer": {}},
        {"buyer": []},
        {"suppliers": {}},
        {"suppliers": [None]},
        {"currency": 3},
        {"references": None},
        {"suppliers": [normalized()["buyer"]] * 1001},
    ],
)
def test_mapping_rejects_invalid_persisted_data(change: dict[str, object]) -> None:
    with pytest.raises(InvalidProjection):
        project_contract({**normalized(), **change})


def test_mapping_requires_explicit_fields() -> None:
    value = normalized()
    del value["suppliers"]
    with pytest.raises(InvalidProjection):
        project_contract(value)


def test_unknown_and_empty_suppliers_do_not_create_synthetic_edges(
    pg_dsn: str, tmp_path: Path
) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(
        run,
        page_body(
            record("unknown"),
            {**record("empty"), "contractingDataDetails": {"contractingMembersDataList": []}},
        ),
        observed_at=datetime.now(UTC),
    )
    assert drain(pg_dsn)["processed_events"] == 2
    assert counts(pg_dsn) == (2, 2, 2, 2)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("""SELECT supplier_count FROM nima.projection_contracts
            ORDER BY supplier_count NULLS FIRST""").fetchall() == [(None,), (0,)]
        assert connection.execute(
            "SELECT count(*) FROM nima.reported_procurement_edges"
        ).fetchone() == (0,)
        assert (
            connection.execute("""SELECT name, tax_id, source_key, country_code
            FROM nima.projection_mentions""").fetchall()
            == [(None, None, None, None)] * 2
        )


def test_joint_awards_replay_and_revisions_retain_observation_evidence(
    pg_dsn: str, tmp_path: Path
) -> None:
    seed(pg_dsn, tmp_path, "A", "B", "A", "A")
    assert drain(pg_dsn, max_events=2) == {
        "projection_version": PROJECTION_VERSION,
        "processed_events": 2,
        "remaining_events": 2,
        "status": "pending",
    }
    assert drain(pg_dsn)["processed_events"] == 2
    assert drain(pg_dsn)["processed_events"] == 0
    assert counts(pg_dsn) == (2, 6, 4, 4)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT DISTINCT net_amount FROM nima.projection_contracts"
        ).fetchall() == [(Decimal("123456789012345678.90"),)]
        edges = connection.execute("""SELECT buyer_name, supplier_name,
            supplier_tax_id, json_pointer, raw_sha256 FROM nima.reported_procurement_edges
            ORDER BY observation_id, supplier_ordinal""").fetchall()
        assert len(edges) == 8
        assert edges[0][:4] == ("Δήμος δοκιμής", "ΑΛΦΑ", "001234567", "/content/0")
        assert len(str(edges[0][4])) == 64
        assert (
            connection.execute("""SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'nima' AND table_name = 'reported_procurement_edges'
            AND column_name LIKE '%%amount%%'""").fetchall()
            == []
        )


def test_locked_older_events_remain_eligible_on_next_invocation(
    pg_dsn: str, tmp_path: Path
) -> None:
    seed(pg_dsn, tmp_path, "A", "B")
    with psycopg.connect(pg_dsn) as locker:
        locker.execute("SELECT 1 FROM nima.outbox ORDER BY observation_id LIMIT 1 FOR UPDATE")
        assert drain(pg_dsn)["processed_events"] == 1
        assert counts(pg_dsn) == (1, 3, 1, 1)
    assert drain(pg_dsn)["processed_events"] == 1
    assert counts(pg_dsn) == (2, 6, 2, 2)


def test_projection_hash_conflict_rolls_back_receipt_and_ack(pg_dsn: str, tmp_path: Path) -> None:
    seed(pg_dsn, tmp_path, "A", "A")
    drain(pg_dsn, max_events=1)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("ALTER TABLE nima.projection_contracts DISABLE TRIGGER USER")
        connection.execute("UPDATE nima.projection_contracts SET projection_sha256=repeat('0',64)")
        connection.execute("ALTER TABLE nima.projection_contracts ENABLE TRIGGER USER")
    with pytest.raises(ProjectionFailure) as failure:
        drain(pg_dsn)
    assert failure.value.reason == "invalid_projection"
    assert counts(pg_dsn) == (1, 3, 1, 1)


@pytest.mark.parametrize("limit", [0, 1001, True])
def test_batch_bounds(limit: int) -> None:
    with pytest.raises(ValueError):
        drain("", max_events=limit)


def test_new_projection_version_replays_acknowledged_events_without_clearing_history(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(pg_dsn, tmp_path, "A", "A")
    drain(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        original = connection.execute("SELECT delivered_at FROM nima.outbox ORDER BY 1").fetchall()
    monkeypatch.setattr("nima.projections.worker.PROJECTION_VERSION", "test-participation-v2")
    assert drain(pg_dsn)["processed_events"] == 2
    assert counts(pg_dsn) == (2, 6, 4, 2)
    with psycopg.connect(pg_dsn) as connection:
        assert (
            connection.execute("SELECT delivered_at FROM nima.outbox ORDER BY 1").fetchall()
            == original
        )
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            connection.execute("UPDATE nima.projection_mentions SET tax_id='changed'")


@pytest.mark.parametrize("kind", ["normalizer", "missing_field", "identity"])
def test_poison_event_stops_visibly_without_acknowledgement(
    pg_dsn: str, tmp_path: Path, kind: str
) -> None:
    seed(pg_dsn, tmp_path, "A", "B")
    with psycopg.connect(pg_dsn) as connection:
        invalid = normalized()
        if kind == "missing_field":
            del invalid["suppliers"]
        elif kind == "identity":
            invalid["source_id"] = "unexpected-source"
        version = "unsupported" if kind == "normalizer" else "kimdis-normalized-v1"
        connection.execute(
            """INSERT INTO nima.record_versions
            SELECT source_id, %s, repeat('f',64), %s FROM nima.source_records""",
            (version, psycopg.types.json.Jsonb(invalid)),
        )
        # Fixture-only corruption: move the last observation to a poison source version.
        connection.execute("ALTER TABLE nima.observations DISABLE TRIGGER USER")
        connection.execute(
            """UPDATE nima.observations SET normalizer_version=%s,
            content_sha256=repeat('f',64) WHERE observation_id=(SELECT max(observation_id)
            FROM nima.observations)""",
            (version,),
        )
        connection.execute("ALTER TABLE nima.observations ENABLE TRIGGER USER")
    with pytest.raises(ProjectionFailure) as failure:
        drain(pg_dsn)
    assert failure.value.reason == "invalid_projection"
    assert failure.value.processed == 1 and failure.value.event_id == 2
    assert counts(pg_dsn) == (1, 3, 1, 1)


def test_concurrent_consumers_commit_each_observation_once(pg_dsn: str, tmp_path: Path) -> None:
    seed(pg_dsn, tmp_path, *("A" for _ in range(12)))
    with ThreadPoolExecutor(max_workers=2) as workers:
        summaries = list(workers.map(lambda _: drain(pg_dsn), range(2)))
    assert sum(int(str(summary["processed_events"])) for summary in summaries) == 12
    assert counts(pg_dsn) == (1, 3, 12, 12)


def test_claim_with_stale_receipt_snapshot_is_rechecked_under_lock(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.projections.worker import _project

    seed(pg_dsn, tmp_path, "A")
    # Model a candidate read before another worker commits; the lock holder must
    # recheck receipts using a fresh statement snapshot before inserting anything.
    with _connect(pg_dsn) as connection:
        candidate = connection.execute("""SELECT q.observation_id, q.event_type,
            v.source_id, v.normalizer_version, v.content_sha256, v.normalized
            FROM nima.outbox q JOIN nima.observations o USING (observation_id)
            JOIN nima.record_versions v USING (source_id, normalizer_version, content_sha256)
            """).fetchone()
        assert candidate is not None
        assert drain(pg_dsn)["processed_events"] == 1
        with connection.transaction():
            connection.execute("SELECT 1 FROM nima.outbox FOR UPDATE")
            assert not _project(connection, candidate)
    assert counts(pg_dsn) == (1, 3, 1, 1)


def test_cli_batch_limits_and_sql_failure_are_redacted(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.__main__ import main

    seed(pg_dsn, tmp_path, "A", "B")
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    assert main(["outbox", "project", "--max-events", "0"]) == 2
    capsys.readouterr()
    assert main(["outbox", "project", "--max-events", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["remaining_events"] == 1
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("""CREATE FUNCTION nima.fail_projection() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'private database details'; END; $$;
            CREATE TRIGGER fail_projection BEFORE INSERT ON nima.projection_mentions
            FOR EACH ROW EXECUTE FUNCTION nima.fail_projection();""")
    assert main(["outbox", "project"]) == 1
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["failure"] == "database" and summary["event_id"] == 2
    assert summary["processed_events"] == 0 and "private" not in output.out + output.err
    assert counts(pg_dsn) == (1, 3, 1, 1)
