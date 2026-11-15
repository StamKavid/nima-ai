"""One bounded read-only SQL snapshot binds review heads, history and anchors."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Never, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from nima.identity import review_evidence, review_snapshot, review_store
from nima.identity.artifacts import encode
from nima.identity.registry_cohort import read_comparison_cohort
from nima.identity.review_export import build_resolution
from nima.identity.review_inputs import decode_report
from nima.identity.review_types import ReviewError, ReviewEvidence, ReviewReport, ReviewSubject
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import Connection, _connect
from tests.test_collection import QUERY
from tests.test_identity_review_accept import request
from tests.test_identity_review_evidence import report as comparison_report
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import report_body
from tests.test_identity_review_reversal import revoke
from tests.test_identity_review_schema import head
from tests.test_identity_review_support import source_snapshot
from tests.test_kimdis_pages import page_body
from tests.test_page_store import store
from tests.test_registry_cohort import registry_import


@pytest.mark.parametrize(
    "status",
    [
        TransactionStatus.IDLE,
        TransactionStatus.INERROR,
        TransactionStatus.UNKNOWN,
        TransactionStatus.ACTIVE,
    ],
)
def test_inactive_caller_connection_is_rejected_before_any_sql(
    status: TransactionStatus,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Caller must supply an active transaction before SQL")

    connection = cast(
        Connection,
        SimpleNamespace(info=SimpleNamespace(transaction_status=status), execute=forbidden),
    )
    with pytest.raises(ReviewError, match="^review_state$"):
        review_snapshot.read_snapshot_in_transaction(connection, decode_report(report_body()))


@pytest.mark.parametrize("limit", [0, -1, 10001, True])
def test_caller_owned_read_validates_limits_before_connection_access(limit: int) -> None:
    with pytest.raises(ValueError, match="^review_configuration$"):
        review_snapshot.read_snapshot_in_transaction(
            cast(Connection, None), decode_report(report_body()), max_events=limit
        )


def test_both_reader_paths_reject_changed_report_before_connection_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = replace(decode_report(report_body()), sha256="0" * 64)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Changed report must fail before any database access")

    monkeypatch.setattr(review_snapshot, "check_schema", forbidden)
    with pytest.raises(ReviewError, match="^review_evidence$"):
        review_snapshot.read_snapshot("private-sentinel", parsed)
    with pytest.raises(ReviewError, match="^review_evidence$"):
        review_snapshot.read_snapshot_in_transaction(cast(Connection, None), parsed)


def test_caller_owned_reader_preserves_transaction_and_canonical_resolution(
    pg_dsn: str, tmp_path: Path
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    review_store.review(pg_dsn, request(parsed), report=parsed)
    expected = review_snapshot.read_snapshot(pg_dsn, parsed)
    before = source_snapshot(pg_dsn)
    with _connect(pg_dsn) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            connection.execute("SET LOCAL application_name='nima_snapshot_owner'")
            identity = connection.execute(
                "SELECT pg_backend_pid(), pg_current_snapshot()::text"
            ).fetchone()
            actual = review_snapshot.read_snapshot_in_transaction(connection, parsed)
            assert actual == expected
            assert encode(build_resolution(actual)) == encode(build_resolution(expected))
            assert not connection.closed
            assert connection.info.transaction_status == TransactionStatus.INTRANS
            assert (
                connection.execute(
                    "SELECT pg_backend_pid(), pg_current_snapshot()::text"
                ).fetchone()
                == identity
            )
            assert connection.execute("SHOW application_name").fetchone() == (
                "nima_snapshot_owner",
            )
            assert review_snapshot.read_snapshot_in_transaction(connection, parsed) == actual
        assert connection.info.transaction_status.name == "IDLE"
        assert connection.execute("SELECT 42").fetchone() == (42,)
    assert source_snapshot(pg_dsn) == before


@pytest.mark.parametrize(
    ("isolation", "read_only", "zone"),
    [
        (psycopg.IsolationLevel.READ_COMMITTED, True, "UTC"),
        (psycopg.IsolationLevel.REPEATABLE_READ, False, "UTC"),
        (psycopg.IsolationLevel.REPEATABLE_READ, True, "Europe/Athens"),
        (psycopg.IsolationLevel.SERIALIZABLE, True, "UTC"),
    ],
)
def test_caller_owned_read_rejects_unsafe_context_without_ending_transaction(
    pg_dsn: str,
    tmp_path: Path,
    isolation: psycopg.IsolationLevel,
    read_only: bool,
    zone: str,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    with _connect(pg_dsn) as connection:
        connection.isolation_level = isolation
        connection.read_only = read_only
        with connection.transaction():
            connection.execute("SELECT set_config('TimeZone',%s,true)", (zone,))
            with pytest.raises(ReviewError, match="^review_state$"):
                review_snapshot.read_snapshot_in_transaction(connection, parsed)
            assert not connection.closed
            assert connection.info.transaction_status == TransactionStatus.INTRANS
            assert connection.execute("SELECT 1").fetchone() == (1,)


def test_caller_owned_read_does_not_begin_an_idle_connection(pg_dsn: str, tmp_path: Path) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    with _connect(pg_dsn) as connection:
        assert connection.info.transaction_status == TransactionStatus.IDLE
        with pytest.raises(ReviewError, match="^review_state$"):
            review_snapshot.read_snapshot_in_transaction(connection, parsed)
        assert connection.info.transaction_status == TransactionStatus.IDLE


@pytest.mark.parametrize("limit", [0, -1, 10001, True])
def test_invalid_snapshot_limit_fails_before_database(
    limit: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid configuration must not reach SQL")

    monkeypatch.setattr(review_snapshot, "check_schema", forbidden)
    with pytest.raises(ValueError, match="^review_configuration$"):
        review_snapshot.read_snapshot(
            "private-sentinel", decode_report(report_body()), max_events=limit
        )


@pytest.mark.parametrize("reserved", [-1, True, 8 * 1024 * 1024 + 1])
def test_invalid_additional_byte_reservation_fails_before_sql(reserved: int) -> None:
    with pytest.raises(ReviewError, match="^review_limit$"):
        review_evidence.validate_evidence(
            cast(Connection, None), decode_report(report_body()), reserve_bytes=reserved
        )


@pytest.mark.parametrize("reserved", [-1, True, 8 * 1024 * 1024 + 1])
def test_shared_snapshot_rejects_invalid_reservation_before_sql(reserved: int) -> None:
    with pytest.raises(ReviewError, match="^review_limit$"):
        review_snapshot.read_snapshot_in_transaction(
            cast(Connection, None), decode_report(report_body()), reserve_bytes=reserved
        )


def test_shared_snapshot_reservation_reduces_the_same_combined_budget(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    review_store.review(pg_dsn, request(parsed), report=parsed)
    expected = review_snapshot.read_snapshot(pg_dsn, parsed)
    with _connect(pg_dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        reserved = review_snapshot.read_snapshot_in_transaction(
            connection, parsed, reserve_bytes=1234
        )
        assert reserved == replace(expected, input_bytes=expected.input_bytes + 1234)
        monkeypatch.setattr(review_evidence, "MAX_INPUT_BYTES", reserved.input_bytes)
        assert (
            review_snapshot.read_snapshot_in_transaction(connection, parsed, reserve_bytes=1234)
            == reserved
        )
        monkeypatch.setattr(review_evidence, "MAX_INPUT_BYTES", reserved.input_bytes - 1)

        def forbidden(*args: object, **kwargs: object) -> Never:
            pytest.fail("Reserved budget must be checked before private labels")

        monkeypatch.setattr(review_evidence, "_party", forbidden)
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_snapshot.read_snapshot_in_transaction(connection, parsed, reserve_bytes=1234)
        assert not connection.closed
        assert connection.info.transaction_status == TransactionStatus.INTRANS


def test_unreviewed_members_need_no_head_writes(pg_dsn: str, tmp_path: Path) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    before = source_snapshot(pg_dsn)
    snapshot = review_snapshot.read_snapshot(pg_dsn, parsed)
    assert snapshot.report == parsed and len(snapshot.heads) == len(parsed.cohort.parties) == 2
    assert all(head.revision == 0 and not head.pairs for head in snapshot.heads)
    assert not snapshot.events and not snapshot.entities
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.identity_review_heads").fetchone() == (
            0,
        )
    assert source_snapshot(pg_dsn) == before


def test_committed_history_must_reconcile_with_the_selected_head(
    pg_dsn: str, tmp_path: Path
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    # Seed coherent immutable history with an accidentally unadvanced head.
    # This is possible for a trusted administrator using raw SQL, not via review().
    with psycopg.connect(pg_dsn) as connection:
        head(connection, chosen.subject.run_id, role="supplier")
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) VALUES (%s,%s,'1',%s)",
            (chosen.entity_id, chosen.candidate.import_id, chosen.request_id),
        )
        connection.execute(
            """INSERT INTO nima.identity_review_events
            (event_id,observation_id,projection_version,role,ordinal,subject_revision,
             candidate_import_id,registry_number,operation,entity_id,request_sha256,
             request_payload,report_sha256,rationale,issues,policy_version)
            VALUES (%s,%s,%s,'supplier',0,1,%s,'1','accept',%s,%s,%s,%s,%s,
                    ARRAY[]::text[],'reviewed-identity-v1')""",
            (
                chosen.request_id,
                chosen.subject.observation_id,
                chosen.subject.projection_version,
                chosen.candidate.import_id,
                chosen.entity_id,
                chosen.digest,
                Jsonb(chosen.payload()),
                chosen.report_sha256,
                chosen.rationale,
            ),
        )
    with pytest.raises(ReviewError, match="^review_state$"):
        review_snapshot.read_snapshot(pg_dsn, parsed)


def test_empty_selected_run_produces_a_complete_empty_resolution(
    pg_dsn: str, tmp_path: Path
) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, page_body(), observed_at=datetime.now(UTC))
    selected = registry_import(pg_dsn, tmp_path)
    parsed = comparison_report(read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION))
    snapshot = review_snapshot.read_snapshot(pg_dsn, parsed)
    assert not snapshot.heads and not snapshot.events and not snapshot.entities


def test_history_candidate_outside_current_catalog_retains_immutable_terminal_provenance(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    outside = registry_import(pg_dsn, tmp_path / "outside")
    expanded = comparison_report(
        read_comparison_cohort(
            pg_dsn,
            parsed.cohort.run_id,
            (parsed.cohort.imports[0].import_id, outside),
            PROJECTION_VERSION,
        )
    )
    chosen = replace(
        request(expanded),
        operation="reject",
        entity_id=None,
        candidate=replace(request(expanded).candidate, import_id=outside),
    )
    review_store.review(pg_dsn, chosen, report=expanded)
    snapshot = review_snapshot.read_snapshot(pg_dsn, parsed)
    assert len(snapshot.events) == 1 and snapshot.events[0].candidate_provenance["run_id"] == str(
        outside
    )
    assert snapshot.events[0].event.request.report_sha256 == expanded.sha256
    assert snapshot.report == parsed and not snapshot.entities


def test_snapshot_retains_rejected_revoked_and_accepted_history_and_sql_attribution(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    rejection = replace(chosen, operation="reject", entity_id=None)
    review_store.review(pg_dsn, rejection, report=parsed)
    reversal = revoke(rejection, 1)
    review_store.review(pg_dsn, reversal)
    accepted = replace(chosen, request_id=uuid4(), expected_revision=2)
    review_store.review(pg_dsn, accepted, report=parsed)
    before = source_snapshot(pg_dsn)
    snapshot = review_snapshot.read_snapshot(pg_dsn, parsed, max_events=3)
    assert [row.event.request.operation for row in snapshot.events] == [
        "reject",
        "revoke",
        "accept",
    ]
    assert all(row.principal and row.recorded_at.endswith("+00:00") for row in snapshot.events)
    assert all(row.candidate_provenance["outcome"] == "found" for row in snapshot.events)
    assert [head.revision for head in snapshot.heads] == [0, 3]
    assert snapshot.entities[0].entity_id == chosen.entity_id
    assert snapshot.entities[0].creating_event_id == accepted.request_id
    assert snapshot.report.cohort.coverage == parsed.cohort.coverage
    assert snapshot == review_snapshot.read_snapshot(pg_dsn, parsed, max_events=3)
    assert source_snapshot(pg_dsn) == before


def test_repeatable_read_survives_concurrent_committed_review(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    original = review_evidence.validate_evidence
    inserted = False

    def concurrent(
        connection: Connection,
        report: ReviewReport,
        *,
        subjects: Sequence[ReviewSubject] | None = None,
        entity_ids: Sequence[UUID] = (),
        reserve_bytes: int = 0,
    ) -> ReviewEvidence:
        nonlocal inserted
        if not inserted:
            inserted = True
            assert connection.execute(
                "SELECT current_setting('transaction_isolation'),"
                "current_setting('transaction_read_only')"
            ).fetchone() == ("repeatable read", "on")
            review_store.review(pg_dsn, chosen, report=parsed)
        return original(
            connection,
            report,
            subjects=subjects,
            entity_ids=entity_ids,
            reserve_bytes=reserve_bytes,
        )

    with monkeypatch.context() as patch:
        patch.setattr(review_evidence, "validate_evidence", concurrent)
        earlier = review_snapshot.read_snapshot(pg_dsn, parsed)
    assert earlier.events == () and all(head.revision == 0 for head in earlier.heads)
    later = review_snapshot.read_snapshot(pg_dsn, parsed)
    assert len(later.events) == 1 and later.heads[1].revision == 1


def test_history_limit_and_combined_bytes_fail_before_materializing_private_rows(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    review_store.review(pg_dsn, revoke(chosen, 1))

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("A rejected budget must precede private source text")

    with monkeypatch.context() as patch:
        patch.setattr(review_evidence, "validate_evidence", forbidden)
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_snapshot.read_snapshot(pg_dsn, parsed, max_events=1)
    snapshot = review_snapshot.read_snapshot(pg_dsn, parsed, max_events=2)
    with monkeypatch.context() as patch:
        patch.setattr(review_evidence, "MAX_INPUT_BYTES", snapshot.input_bytes - 1)
        patch.setattr(review_evidence, "_party", forbidden)
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_snapshot.read_snapshot(pg_dsn, parsed, max_events=2)


def test_all_selected_history_handles_revalidate_outside_anchor_and_observation_budget(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path / "selected")
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    other = seed_report(pg_dsn, tmp_path / "outside")
    another = request(other)
    review_store.review(pg_dsn, another, report=other)
    review_store.review(pg_dsn, revoke(chosen, 1))
    attached = replace(chosen, request_id=uuid4(), entity_id=another.entity_id, expected_revision=2)
    review_store.review(pg_dsn, attached, report=parsed)
    snapshot = review_snapshot.read_snapshot(pg_dsn, parsed)
    assert {entity.entity_id for entity in snapshot.entities} == {
        chosen.entity_id,
        another.entity_id,
    }
    assert {entity.evidence.claim.import_id for entity in snapshot.entities} == {
        chosen.candidate.import_id,
        another.candidate.import_id,
    }
    monkeypatch.setattr(review_evidence, "MAX_REGISTRY_OBSERVATIONS", 2)
    with pytest.raises(ReviewError, match="^review_limit$"):
        review_snapshot.read_snapshot(pg_dsn, parsed)
