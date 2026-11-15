"""Graph facts and reviewed state share one bounded, read-only SQL snapshot."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Never
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from nima.graph import GraphError, snapshot
from nima.identity import review_snapshot, review_store
from nima.identity.registry_cohort import read_comparison_cohort
from nima.identity.review_inputs import decode_report
from nima.identity.review_types import ReviewReport
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import Connection, _connect
from tests.test_collection import QUERY
from tests.test_identity_report import seed
from tests.test_identity_review_accept import request
from tests.test_identity_review_evidence import report as comparison_report
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import report_body
from tests.test_identity_review_reversal import revoke
from tests.test_identity_review_support import source_snapshot
from tests.test_kimdis_pages import page_body, record
from tests.test_page_store import store
from tests.test_registry_cohort import registry_import


@pytest.mark.parametrize("limit", [0, -1, 10001, True])
def test_graph_configuration_is_rejected_before_sql(
    limit: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid configuration must not open SQL")

    monkeypatch.setattr(snapshot, "check_schema", forbidden)
    with pytest.raises(ValueError, match="^graph_configuration$"):
        snapshot.read_snapshot("private-sentinel", decode_report(report_body()), max_events=limit)


def test_changed_typed_report_fails_before_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid report must not open SQL")

    monkeypatch.setattr(snapshot, "check_schema", forbidden)
    parsed = replace(decode_report(report_body()), sha256="0" * 64)
    with pytest.raises(GraphError, match="^graph_evidence$"):
        snapshot.read_snapshot("private-sentinel", parsed)


def test_more_than_100_selected_occurrences_fail_before_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = decode_report(report_body()).cohort
    oversized = comparison_report(
        replace(
            cohort,
            parties=tuple(
                replace(cohort.parties[0], observation_id=index + 1) for index in range(101)
            ),
        )
    )

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Oversized selected graph must fail before opening SQL")

    monkeypatch.setattr(snapshot, "check_schema", forbidden)
    with pytest.raises(GraphError, match="^graph_limit$"):
        snapshot.read_snapshot("private-sentinel", oversized)


def test_complete_graph_snapshot_keeps_exact_facts_and_review_state_without_writes(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    expected = review_snapshot.read_snapshot(pg_dsn, parsed)
    before = source_snapshot(pg_dsn)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Offline graph read must not make HTTP requests")

    monkeypatch.setattr("httpx.Client", forbidden)
    actual = snapshot.read_snapshot(pg_dsn, parsed)
    assert actual.review.heads == expected.heads
    assert actual.review.events == expected.events and actual.review.entities == expected.entities
    assert actual.review.report == parsed
    assert actual.input_bytes > expected.input_bytes
    assert len(actual.contracts) == 1 and len(actual.review.heads) == 2
    fact = actual.contracts[0]
    assert fact.key.source_id == "kimdis:26SYMV000000001"
    assert fact.key.projection_version == PROJECTION_VERSION
    assert fact.title == "ΔΟΚΙΜΑΣΤΙΚΗ" and fact.net_amount == Decimal("0.10")
    assert fact.gross_amount is None and fact.currency is None
    assert fact.bidder_count is None and fact.cancelled is None
    assert fact.source_submitted_at is fact.source_updated_at is None
    assert fact.supplier_count == 1 and len(fact.projection_sha256) == 64
    assert actual == snapshot.read_snapshot(pg_dsn, parsed)
    assert source_snapshot(pg_dsn) == before


def test_normalized_decimal_exponent_is_exact_despite_postgres_numeric_text_format(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path, {**record(), "totalCostWithoutVAT": "1e6"})
    imported = registry_import(pg_dsn, tmp_path)
    parsed = comparison_report(read_comparison_cohort(pg_dsn, run, (imported,), PROJECTION_VERSION))
    actual = snapshot.read_snapshot(pg_dsn, parsed)
    assert actual.contracts[0].net_amount == Decimal("1000000")


def test_selected_subjects_do_not_expose_unselected_supplier_labels(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(
        pg_dsn,
        tmp_path,
        {
            **record(),
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": "Άλφα", "vatNumber": "001234567", "country": {"key": "GR"}},
                    {"name": "private-unselected-sentinel", "vatNumber": "001234567"},
                ]
            },
        },
    )
    imported = registry_import(pg_dsn, tmp_path)
    full = read_comparison_cohort(pg_dsn, run, (imported,), PROJECTION_VERSION)
    parsed = comparison_report(
        replace(
            full, parties=tuple(p for p in full.parties if p.role == "supplier" and p.ordinal == 0)
        )
    )
    actual = snapshot.read_snapshot(pg_dsn, parsed)
    assert len(actual.review.heads) == 1 and actual.contracts[0].supplier_count == 2
    assert "private-unselected-sentinel" not in repr(actual)


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "private-corrupt-sentinel"),
        ("net_amount", Decimal("0.11")),
        ("gross_amount", Decimal("1.23")),
        ("currency", "EUR"),
        ("bidder_count", 3),
        ("cancelled", True),
        ("supplier_count", 2),
        ("projection_sha256", "a" * 64),
    ],
)
def test_stored_contract_columns_are_checked_even_when_normalized_record_is_unchanged(
    pg_dsn: str, tmp_path: Path, field: str, value: object
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("ALTER TABLE nima.projection_contracts DISABLE TRIGGER USER")
        connection.execute(
            sql.SQL("UPDATE nima.projection_contracts SET {}=%s").format(sql.Identifier(field)),
            (value,),
        )
    with pytest.raises(GraphError, match="^graph_evidence$") as failure:
        snapshot.read_snapshot(pg_dsn, parsed)
    assert "private-corrupt-sentinel" not in str(failure.value)


@pytest.mark.parametrize("replacement", ['"private-corrupt-sentinel"', "42"])
def test_normalized_record_codec_and_digest_are_revalidated(
    pg_dsn: str, tmp_path: Path, replacement: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("ALTER TABLE nima.record_versions DISABLE TRIGGER USER")
        connection.execute(
            "UPDATE nima.record_versions SET normalized=jsonb_set(normalized,'{title}',%s::jsonb)",
            (replacement,),
        )
    with pytest.raises(GraphError, match="^graph_evidence$"):
        snapshot.read_snapshot(pg_dsn, parsed)


def test_full_contract_bytes_are_reserved_before_any_private_rows_are_materialized(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path, {**record(), "title": "x" * (5 * 1024 * 1024)})
    imported = registry_import(pg_dsn, tmp_path)
    parsed = comparison_report(read_comparison_cohort(pg_dsn, run, (imported,), PROJECTION_VERSION))

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Over-budget graph must not transfer private review or contract rows")

    monkeypatch.setattr(review_snapshot, "read_snapshot_in_transaction", forbidden)
    monkeypatch.setattr(snapshot, "_fact", forbidden)
    with pytest.raises(GraphError, match="^graph_limit$"):
        snapshot.read_snapshot(pg_dsn, parsed)


def test_combined_contract_and_review_budget_has_an_exact_boundary(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    actual = snapshot.read_snapshot(pg_dsn, parsed)
    monkeypatch.setattr("nima.identity.review_evidence.MAX_INPUT_BYTES", actual.input_bytes)
    assert snapshot.read_snapshot(pg_dsn, parsed) == actual
    monkeypatch.setattr("nima.identity.review_evidence.MAX_INPUT_BYTES", actual.input_bytes - 1)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Combined preflight must precede private labels")

    monkeypatch.setattr("nima.identity.review_evidence._party", forbidden)
    monkeypatch.setattr(snapshot, "_fact", forbidden)
    with pytest.raises(GraphError, match="^graph_limit$"):
        snapshot.read_snapshot(pg_dsn, parsed)


def test_contract_budget_pins_the_same_snapshot_as_a_concurrent_reversal(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    original = review_snapshot.read_snapshot_in_transaction
    reversed_once = False

    def concurrent(
        connection: Connection,
        report: ReviewReport,
        *,
        max_events: int = 10000,
        reserve_bytes: int = 0,
    ) -> review_snapshot.ResolutionSnapshot:
        nonlocal reversed_once
        if not reversed_once:
            reversed_once = True
            review_store.review(pg_dsn, revoke(chosen, 1))
        return original(connection, report, max_events=max_events, reserve_bytes=reserve_bytes)

    with monkeypatch.context() as patch:
        patch.setattr(review_snapshot, "read_snapshot_in_transaction", concurrent)
        earlier = snapshot.read_snapshot(pg_dsn, parsed)
    later = snapshot.read_snapshot(pg_dsn, parsed)
    assert earlier.review.heads[1].accepted_entity_id == chosen.entity_id
    assert earlier.review.heads[1].revision == 1
    assert later.review.heads[1].accepted_entity_id is None
    assert later.review.heads[1].revision == 2
    assert earlier.contracts == later.contracts


def test_later_collection_does_not_replace_a_historical_reports_contract_version(
    pg_dsn: str, tmp_path: Path
) -> None:
    parsed = seed_report(pg_dsn, tmp_path / "old")
    run = seed(pg_dsn, tmp_path / "later", {**record(), "title": "Νέα έκδοση"})
    later = comparison_report(
        read_comparison_cohort(
            pg_dsn, run, (parsed.cohort.imports[0].import_id,), PROJECTION_VERSION
        )
    )
    old_graph = snapshot.read_snapshot(pg_dsn, parsed)
    new_graph = snapshot.read_snapshot(pg_dsn, later)
    assert old_graph.contracts[0].title == "ΔΟΚΙΜΑΣΤΙΚΗ"
    assert new_graph.contracts[0].title == "Νέα έκδοση"
    assert old_graph.contracts[0].key != new_graph.contracts[0].key


@pytest.mark.parametrize("suppliers", [None, []])
def test_missing_and_explicitly_empty_supplier_lists_remain_distinct(
    pg_dsn: str, tmp_path: Path, suppliers: object
) -> None:
    run = seed(
        pg_dsn,
        tmp_path,
        {
            **record(),
            "totalCostWithoutVAT": None,
            "contractingDataDetails": {"contractingMembersDataList": suppliers},
        },
    )
    imported = registry_import(pg_dsn, tmp_path)
    parsed = comparison_report(read_comparison_cohort(pg_dsn, run, (imported,), PROJECTION_VERSION))
    actual = snapshot.read_snapshot(pg_dsn, parsed)
    assert actual.contracts[0].supplier_count == (None if suppliers is None else 0)
    assert actual.contracts[0].net_amount is None
    assert len(actual.review.heads) == 1 and actual.review.heads[0].subject.role == "buyer"


def test_empty_selection_retains_catalog_without_contracts(pg_dsn: str, tmp_path: Path) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, page_body(), observed_at=datetime.now(UTC))
    imported = registry_import(pg_dsn, tmp_path)
    parsed = comparison_report(read_comparison_cohort(pg_dsn, run, (imported,), PROJECTION_VERSION))
    actual = snapshot.read_snapshot(pg_dsn, parsed)
    assert actual.contracts == () and actual.review.heads == ()
    assert actual.review.report.cohort.registry == parsed.cohort.registry


@pytest.mark.parametrize("table", ["projection_contracts", "record_versions"])
def test_missing_exact_contract_or_normalized_version_fails_before_materialization(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, table: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    # Deliberate administrator corruption in the disposable database; normal writes
    # are protected by immutable triggers and foreign keys.
    with psycopg.connect(pg_dsn) as connection:
        connection.execute(
            sql.SQL("ALTER TABLE nima.{} DISABLE TRIGGER ALL").format(sql.Identifier(table))
        )
        connection.execute(sql.SQL("DELETE FROM nima.{}").format(sql.Identifier(table)))

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Missing version must fail before private review reads")

    monkeypatch.setattr(review_snapshot, "read_snapshot_in_transaction", forbidden)
    with pytest.raises(GraphError, match="^graph_evidence$"):
        snapshot.read_snapshot(pg_dsn, parsed)


def test_rehashed_forged_report_labels_still_fail_against_sql(pg_dsn: str, tmp_path: Path) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    cohort = parsed.cohort
    forged = comparison_report(
        replace(
            cohort,
            parties=(
                replace(cohort.parties[0], name="private-forged-sentinel"),
                *cohort.parties[1:],
            ),
        )
    )
    with pytest.raises(GraphError, match="^graph_evidence$"):
        snapshot.read_snapshot(pg_dsn, forged)


def test_missing_schema_and_invalid_dsn_have_fixed_failures(pg_dsn: str) -> None:
    parsed = decode_report(report_body())
    with pytest.raises(GraphError, match="^graph_schema$"):
        snapshot.read_snapshot(pg_dsn, parsed)
    with pytest.raises(GraphError, match="^graph_database$"):
        snapshot.read_snapshot("private-invalid-dsn-sentinel", parsed)


def test_inconsistent_review_head_is_a_graph_state_failure(pg_dsn: str, tmp_path: Path) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("ALTER TABLE nima.identity_review_heads DISABLE TRIGGER ALL")
        connection.execute("UPDATE nima.identity_review_heads SET revision=revision+1")
    with pytest.raises(GraphError, match="^graph_state$"):
        snapshot.read_snapshot(pg_dsn, parsed)


def test_selected_event_limit_is_shared_with_review_reader(pg_dsn: str, tmp_path: Path) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    review_store.review(pg_dsn, revoke(chosen, 1))
    with pytest.raises(GraphError, match="^graph_limit$"):
        snapshot.read_snapshot(pg_dsn, parsed, max_events=1)
    assert len(snapshot.read_snapshot(pg_dsn, parsed, max_events=2).review.events) == 2


def test_missing_contract_read_permission_is_redacted_and_closes_connection(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    role = sql.Identifier("nima_graph_" + uuid4().hex)
    connections: list[Connection] = []
    original = _connect

    @contextmanager
    def restricted(dsn: str) -> Iterator[Connection]:
        with original(dsn) as connection:
            connections.append(connection)
            connection.execute(sql.SQL("SET ROLE {}").format(role))
            yield connection

    with psycopg.connect(pg_dsn) as connection:
        connection.execute(sql.SQL("CREATE ROLE {}").format(role))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA nima TO {}").format(role))
        connection.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA nima TO {}").format(role))
        connection.execute(
            sql.SQL("REVOKE SELECT ON nima.projection_contracts FROM {}").format(role)
        )
    try:
        monkeypatch.setattr(snapshot, "_connect", restricted)
        with pytest.raises(GraphError, match="^graph_permission$"):
            snapshot.read_snapshot(pg_dsn, parsed)
        assert len(connections) == 1 and connections[0].closed
    finally:
        with psycopg.connect(pg_dsn) as connection:
            connection.execute(sql.SQL("DROP OWNED BY {}").format(role))
            connection.execute(sql.SQL("DROP ROLE {}").format(role))


@pytest.mark.parametrize("outcome", ["success", "evidence", "driver", "interrupted"])
def test_owned_connection_closes_after_success_failure_and_interruption(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    connections: list[Connection] = []
    original = _connect

    @contextmanager
    def tracked(dsn: str) -> Iterator[Connection]:
        with original(dsn) as connection:
            connections.append(connection)
            yield connection

    monkeypatch.setattr(snapshot, "_connect", tracked)
    if outcome == "success":
        snapshot.read_snapshot(pg_dsn, parsed)
    else:

        def failing_fact(*args: object, **kwargs: object) -> Never:
            if outcome == "interrupted":
                raise KeyboardInterrupt
            if outcome == "driver":
                raise psycopg.OperationalError("private-driver-sentinel")
            raise GraphError("graph_evidence")

        monkeypatch.setattr(snapshot, "_fact", failing_fact)
        if outcome == "interrupted":
            with pytest.raises(KeyboardInterrupt):
                snapshot.read_snapshot(pg_dsn, parsed)
        else:
            expected = "graph_database" if outcome == "driver" else "graph_evidence"
            with pytest.raises(GraphError, match=f"^{expected}$"):
                snapshot.read_snapshot(pg_dsn, parsed)
    assert len(connections) == 1 and connections[0].closed
