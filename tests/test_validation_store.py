"""Actual SQL journal ownership, immutable history, retries and session fencing."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from nima.contracts.history import HistoryError, Outcome
from nima.storage.postgres import migrate
from nima.storage.validations import Journal, show_validation
from tests.test_analytics_snapshot import reader
from tests.test_validation_history import intent


@contextmanager
def journal_role(dsn: str, *, write: bool = True) -> Iterator[str]:
    with reader(dsn) as (limited, role), psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            sql.SQL("GRANT USAGE ON SCHEMA nima_validation TO {}").format(sql.Identifier(role))
        )
        grants = "SELECT,INSERT" if write else "SELECT"
        c.execute(
            sql.SQL("GRANT " + grants + " ON ALL TABLES IN SCHEMA nima_validation TO {}").format(
                sql.Identifier(role)
            )
        )
        yield limited


def test_pending_commit_replay_and_conflicting_intent(pg_dsn: str) -> None:
    migrate(pg_dsn)
    attempt = uuid4()
    value = intent()
    outcome = Outcome(value.digest, "passed", "byte_equivalence", "ok", "f" * 64, 7, 5)
    with journal_role(pg_dsn) as dsn:
        with Journal(dsn, attempt, value).session() as journal:
            assert journal.read()["status"] == "pending"
        assert show_validation(dsn, attempt)["status"] == "pending"
        with Journal(dsn, attempt, value).session() as journal:
            first = journal.finish(outcome)
        assert first["status"] == "passed"
        with Journal(dsn, attempt, value).session() as journal:
            assert journal.finish(outcome) == first
        with (
            pytest.raises(HistoryError, match="^validation_conflict$"),
            Journal(dsn, attempt, replace(value, artifact_sha256="d" * 64)).session(),
        ):
            pytest.fail("Conflicting intent acquired")
        with (
            Journal(dsn, attempt, value).session() as journal,
            pytest.raises(HistoryError, match="^validation_conflict$"),
        ):
            journal.finish(Outcome(value.digest, "blocked", "reconstruction", "inputs_unavailable"))
        fresh = uuid4()
        with Journal(dsn, fresh, value).session() as journal:
            second = journal.finish(outcome)
        assert first["outcome_sha256"] == second["outcome_sha256"]
        assert first["started_at"] != second["started_at"]
    with journal_role(pg_dsn, write=False) as dsn:
        assert show_validation(dsn, attempt) == first
        with (
            pytest.raises(HistoryError, match="^validation_database$"),
            Journal(dsn, uuid4(), value).session(),
        ):
            pytest.fail("Read role wrote")


def test_busy_and_immutable_rows(pg_dsn: str) -> None:
    migrate(pg_dsn)
    attempt, value = uuid4(), intent()
    with journal_role(pg_dsn) as dsn:
        with (
            Journal(dsn, attempt, value).session(),
            pytest.raises(HistoryError, match="^validation_busy$"),
            Journal(dsn, attempt, value).session(),
        ):
            pytest.fail("Concurrent writer acquired")
        with Journal(dsn, attempt, value).session() as journal:
            journal.finish(Outcome(value.digest, "failed", "artifact_integrity", "artifact_digest"))
    for table in ("attempts", "outcomes"):
        for verb in ("UPDATE", "DELETE", "TRUNCATE"):
            statement = {
                "UPDATE": "UPDATE {} SET attempt_id=attempt_id",
                "DELETE": "DELETE FROM {}",
                "TRUNCATE": "TRUNCATE {} CASCADE",
            }[verb]
            with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.Error):
                c.execute(sql.SQL(statement).format(sql.Identifier("nima_validation", table)))
    with journal_role(pg_dsn) as dsn:
        assert show_validation(dsn, attempt)["status"] == "failed"


def test_superuser_and_source_writers_are_not_journal_principals(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with (
        pytest.raises(HistoryError, match="^validation_database$"),
        Journal(pg_dsn, uuid4(), intent()).session(),
    ):
        pytest.fail("Superuser accepted")
    with journal_role(pg_dsn) as dsn:
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            role = psycopg.conninfo.conninfo_to_dict(dsn)["user"]
            assert isinstance(role, str)
            c.execute(
                sql.SQL("GRANT UPDATE ON nima.ingest_runs TO {}").format(sql.Identifier(role))
            )
        with (
            pytest.raises(HistoryError, match="^validation_database$"),
            Journal(dsn, uuid4(), intent()).session(),
        ):
            pytest.fail("Source writer accepted")


@pytest.mark.parametrize(
    "grant",
    [
        "GRANT CREATE ON SCHEMA nima_validation TO {}",
        "GRANT INSERT (status) ON nima.ingest_runs TO {}",
        "GRANT UPDATE (document) ON nima_validation.outcomes TO {}",
    ],
)
def test_column_or_schema_write_privileges_are_rejected(pg_dsn: str, grant: str) -> None:
    migrate(pg_dsn)
    with journal_role(pg_dsn) as dsn:
        role = psycopg.conninfo.conninfo_to_dict(dsn)["user"]
        assert isinstance(role, str)
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            c.execute(sql.SQL(grant).format(sql.Identifier(role)))
        with (
            pytest.raises(HistoryError, match="^validation_database$"),
            Journal(dsn, uuid4(), intent()).session(),
        ):
            pytest.fail("Unsafe privilege accepted")


def test_database_stamps_and_foreign_key_are_enforced(pg_dsn: str) -> None:
    migrate(pg_dsn)
    attempt, value = uuid4(), intent()
    with journal_role(pg_dsn) as dsn, psycopg.connect(dsn, autocommit=True) as c:
        c.execute(
            """INSERT INTO nima_validation.attempts
            (attempt_id,intent_sha256,document,started_at,database_principal)
            VALUES (%s,%s,%s,'2000-01-01Z','forged')""",
            (attempt, value.digest, Jsonb(value.payload())),
        )
        assert c.execute("""SELECT clock_timestamp()-started_at<interval '5 seconds',
            database_principal=current_user FROM nima_validation.attempts""").fetchone() == (
            True,
            True,
        )
        outcome = Outcome(value.digest, "blocked", "reconstruction", "inputs_unavailable")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute(
                """INSERT INTO nima_validation.outcomes
                (attempt_id,intent_sha256,outcome_sha256,document) VALUES (%s,%s,%s,%s)""",
                (uuid4(), value.digest, outcome.digest, Jsonb(outcome.payload())),
            )
        with pytest.raises(HistoryError, match="^validation_unknown$"):
            show_validation(dsn, uuid4())
