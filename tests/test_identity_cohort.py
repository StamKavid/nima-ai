"""Connection-owned cohort reads preserve snapshot, limits and assessment output."""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import Cursor
from psycopg.abc import Params
from psycopg.pq import TransactionStatus
from psycopg.sql import SQL, Composed

from nima.identity import MAX_REPORT_BYTES, AssessmentError
from nima.identity.artifacts import encode
from nima.identity.cohort import read_cohort, read_cohort_in_transaction
from nima.identity.report import build_report
from nima.projections.worker import PROJECTION_VERSION, drain
from nima.storage.postgres import Connection, _connect
from tests.test_collection import QUERY, body
from tests.test_identity_report import seed
from tests.test_kimdis_pages import record
from tests.test_page_store import counts, store


def test_shared_reader_preserves_assessment_bytes_and_caller_transaction(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path, record("one"), record("two"))
    coverage, members = read_cohort(pg_dsn, run, PROJECTION_VERSION, 10000)
    expected = encode(build_report(run, PROJECTION_VERSION, coverage, members))
    before = counts(pg_dsn)
    with _connect(pg_dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        shared_coverage, shared_members = read_cohort_in_transaction(
            connection, run, PROJECTION_VERSION, 10000
        )
        assert (
            encode(build_report(run, PROJECTION_VERSION, shared_coverage, shared_members))
            == expected
        )
        assert (
            not connection.closed
            and connection.info.transaction_status == TransactionStatus.INTRANS
        )
        assert connection.execute("SELECT 1").fetchone() == (1,)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction), connection.transaction():
            connection.execute("UPDATE nima.ingest_runs SET next_page=next_page")
    assert counts(pg_dsn) == before


def test_repeated_shared_reads_exclude_commits_from_another_connection(
    pg_dsn: str, tmp_path: Path
) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, body(), observed_at=datetime.now(UTC))
    drain(pg_dsn)
    with _connect(pg_dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        first = read_cohort_in_transaction(connection, run, PROJECTION_VERSION, 10000)
        database.commit_page(run, body(page=1), observed_at=datetime.now(UTC))
        drain(pg_dsn)
        assert read_cohort_in_transaction(connection, run, PROJECTION_VERSION, 10000) == first
        assert first[0]["observation_count"] == len(first[1]) == 1
        assert connection.info.transaction_status == TransactionStatus.INTRANS
    assert read_cohort(pg_dsn, run, PROJECTION_VERSION, 10000)[0]["observation_count"] == 2


@pytest.mark.parametrize("context", ["idle", "read_committed", "read_write"])
def test_unconfigured_connection_is_rejected_without_reconfiguring_it(
    pg_dsn: str, context: str
) -> None:
    with _connect(pg_dsn) as connection:
        if context == "idle":
            with pytest.raises(ValueError, match="cohort_transaction"):
                read_cohort_in_transaction(connection, uuid4(), PROJECTION_VERSION, 10000)
            assert connection.info.transaction_status == TransactionStatus.IDLE
            return
        with connection.transaction():
            if context == "read_write":
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            else:
                connection.execute("SET TRANSACTION READ ONLY")
            setting = (
                "SELECT current_setting('transaction_isolation'), "
                "current_setting('transaction_read_only')"
            )
            before = connection.execute(setting).fetchone()
            with pytest.raises(ValueError, match="cohort_transaction"):
                read_cohort_in_transaction(connection, uuid4(), PROJECTION_VERSION, 10000)
            assert connection.execute(setting).fetchone() == before
            assert connection.info.transaction_status == TransactionStatus.INTRANS


def test_stricter_byte_budget_rejects_before_label_transfer_and_keeps_transaction(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    original = psycopg.Connection.execute

    def guarded_execute(
        self: Connection,
        query: str | bytes | SQL | Composed,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool = False,
    ) -> Cursor[tuple[object, ...]]:
        # Metadata really comes from PostgreSQL; crossing the label-transfer
        # boundary would be wrong even if a later check raised the same error.
        if isinstance(query, str) and "SELECT to_jsonb(m)" in query:
            raise AssertionError("label_transfer_before_budget")
        return original(self, query, params, prepare=prepare, binary=binary)

    with _connect(pg_dsn) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        monkeypatch.setattr(psycopg.Connection, "execute", guarded_execute)
        with pytest.raises(AssessmentError, match="assessment_limit"):
            read_cohort_in_transaction(
                connection, run, PROJECTION_VERSION, 10000, max_input_bytes=1
            )
        assert connection.info.transaction_status == TransactionStatus.INTRANS
        assert connection.execute("SELECT 1").fetchone() == (1,)


@pytest.mark.parametrize("budget", [0, -1, True, MAX_REPORT_BYTES + 1])
def test_invalid_helper_budget_fails_before_touching_a_connection(budget: int) -> None:
    with pytest.raises(ValueError, match="max_input_bytes"):
        read_cohort_in_transaction(
            cast(Connection, None), uuid4(), PROJECTION_VERSION, 10000, max_input_bytes=budget
        )
