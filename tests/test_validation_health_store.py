"""Complete selected cohorts use real restricted repeatable-read SQL snapshots."""

from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.contracts.history import HistoryError, Outcome
from nima.storage.postgres import migrate
from nima.storage.validations import Journal, read_validation_history, show_validation
from tests.test_validation_history import intent
from tests.test_validation_store import journal_role


def test_complete_selection_and_existing_inspection_are_read_only(pg_dsn: str) -> None:
    migrate(pg_dsn)
    value = intent()
    attempt = uuid4()
    with journal_role(pg_dsn) as dsn:
        with Journal(dsn, attempt, value).session() as journal:
            saved = journal.finish(
                Outcome(value.digest, "passed", "byte_equivalence", "ok", "e" * 64, 7, 5)
            )
        with Journal(dsn, uuid4(), value).session():
            pass
        with Journal(dsn, uuid4(), replace(value, artifact_sha256="f" * 64)).session():
            pass
    with journal_role(pg_dsn, write=False) as dsn:
        sampled, records = read_validation_history(dsn, value.artifact_sha256)
        assert sampled.utcoffset() is not None and len(records) == 2
        assert {r.status for r in records} == {"passed", "pending"}
        assert next(r for r in records if r.attempt_id == attempt).payload() == saved
        assert show_validation(dsn, attempt) == saved
        assert read_validation_history(dsn, "0" * 64)[1] == ()


def test_limit_refuses_whole_cohort_without_truncation(pg_dsn: str) -> None:
    migrate(pg_dsn)
    value = intent()
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            """INSERT INTO nima_validation.attempts (attempt_id,intent_sha256,document)
            SELECT gen_random_uuid(),%s,%s FROM generate_series(1,1001)""",
            (value.digest, Jsonb(value.payload())),
        )
    with (
        journal_role(pg_dsn, write=False) as dsn,
        pytest.raises(HistoryError, match="^validation_limit$"),
    ):
        read_validation_history(dsn, value.artifact_sha256)


def test_old_corruption_is_not_hidden_by_latest_record(pg_dsn: str) -> None:
    migrate(pg_dsn)
    value = intent()
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            "INSERT INTO nima_validation.attempts (attempt_id,intent_sha256,document) "
            "VALUES (%s,%s,%s)",
            (uuid4(), "0" * 64, Jsonb(value.payload())),
        )
    with journal_role(pg_dsn) as dsn:
        with Journal(dsn, uuid4(), value).session() as journal:
            journal.finish(
                Outcome(value.digest, "passed", "byte_equivalence", "ok", "e" * 64, 7, 5)
            )
        with pytest.raises(HistoryError, match="^validation_integrity$"):
            read_validation_history(dsn, value.artifact_sha256)


def test_interleaved_commit_does_not_change_frozen_cohort(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import validations
    from nima.storage.connection import Connection

    migrate(pg_dsn)
    value = intent()
    with journal_role(pg_dsn) as dsn:
        with Journal(dsn, uuid4(), value).session():
            pass
        original = validations._history_size

        def interleave(c: Connection, artifact: str) -> int:
            count = original(c, artifact)
            with Journal(dsn, uuid4(), value).session():
                pass
            return count

        monkeypatch.setattr(validations, "_history_size", interleave)
        assert len(read_validation_history(dsn, value.artifact_sha256)[1]) == 1
        monkeypatch.setattr(validations, "_history_size", original)
        assert len(read_validation_history(dsn, value.artifact_sha256)[1]) == 2


def test_byte_budget_and_read_only_transaction_are_independent_guards(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import validations
    from nima.storage.connection import Connection

    migrate(pg_dsn)
    value = intent()
    with journal_role(pg_dsn) as dsn:
        with Journal(dsn, uuid4(), value).session():
            pass
        with monkeypatch.context() as patch:
            patch.setattr(validations, "MAX_HISTORY_BYTES", 1)
            with pytest.raises(HistoryError, match="^validation_limit$"):
                read_validation_history(dsn, value.artifact_sha256)
        blocked = []

        def write(c: Connection, artifact: str) -> int:
            try:
                c.execute(
                    "INSERT INTO nima_validation.attempts (attempt_id,intent_sha256,document) "
                    "VALUES (%s,%s,%s)",
                    (uuid4(), value.digest, Jsonb(value.payload())),
                )
            except psycopg.errors.ReadOnlySqlTransaction:
                blocked.append(True)
                raise
            pytest.fail("Health's transaction unexpectedly accepted a write")

        monkeypatch.setattr(validations, "_history_size", write)
        with pytest.raises(HistoryError, match="^validation_database$"):
            read_validation_history(dsn, value.artifact_sha256)
        assert blocked == [True]
