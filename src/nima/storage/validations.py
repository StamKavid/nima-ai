"""Append-only validation journal; source reads use a different connection/role."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from nima.contracts.history import HistoryError, Intent, Outcome, decode_intent, decode_outcome
from nima.storage.connection import Connection, connect
from nima.storage.postgres import MigrationError, validate_schema


def _role(c: Connection, *, write: bool) -> None:
    row = c.execute("""SELECT
        (SELECT rolsuper OR rolbypassrls OR rolcreaterole FROM pg_roles WHERE rolname=current_user),
        EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname IN
          ('nima','nima_processing','nima_validation')
          AND has_schema_privilege(current_user,n.oid,'CREATE')),
        EXISTS (SELECT 1 FROM pg_class r JOIN pg_namespace n ON r.relnamespace=n.oid
          WHERE n.nspname IN ('nima','nima_processing','nima_validation') AND
          ((r.relkind IN ('r','p','v','m','f') AND
            (has_table_privilege(current_user,r.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
             OR has_any_column_privilege(current_user,r.oid,'UPDATE,REFERENCES')
             OR (n.nspname<>'nima_validation' AND
                (has_table_privilege(current_user,r.oid,'INSERT')
                 OR has_any_column_privilege(current_user,r.oid,'INSERT')))))
           OR (r.relkind='S' AND has_sequence_privilege(current_user,r.oid,'USAGE,UPDATE')))),
        has_table_privilege(current_user,'nima_validation.attempts','SELECT') AND
        has_table_privilege(current_user,'nima_validation.outcomes','SELECT'),
        has_table_privilege(current_user,'nima_validation.attempts','INSERT') AND
        has_table_privilege(current_user,'nima_validation.outcomes','INSERT')""").fetchone()
    if row is None or any(row[:3]) or not row[3] or (write and not row[4]):
        raise HistoryError("validation_database")


@contextmanager
def _database(dsn: str, *, write: bool) -> Iterator[Connection]:
    if not isinstance(dsn, str) or not dsn.strip():
        raise HistoryError("validation_configuration")
    try:
        with connect(dsn) as c:
            validate_schema(c)
            _role(c, write=write)
            yield c
    except MigrationError:
        raise HistoryError("validation_schema") from None
    except psycopg.Error:
        raise HistoryError("validation_database") from None


def _read(c: Connection, attempt: UUID) -> dict[str, object]:
    row = c.execute(
        """SELECT a.intent_sha256,a.document,a.started_at,
        o.outcome_sha256,o.document,o.recorded_at FROM nima_validation.attempts a
        LEFT JOIN nima_validation.outcomes o USING (attempt_id,intent_sha256)
        WHERE a.attempt_id=%s""",
        (attempt,),
    ).fetchone()
    if row is None:
        raise HistoryError("validation_unknown")
    intent = decode_intent(row[1])
    if intent.digest != row[0]:
        raise HistoryError("validation_integrity")
    result = None if row[4] is None else decode_outcome(row[4])
    if result is not None and (result.intent_sha256 != intent.digest or result.digest != row[3]):
        raise HistoryError("validation_integrity")
    return {
        "version": "nima-validation-history-v1",
        "attempt_id": str(attempt),
        "intent_sha256": intent.digest,
        "intent": intent.payload(),
        "started_at": cast(datetime, row[2]).isoformat(),
        "recorded_at": None if row[5] is None else cast(datetime, row[5]).isoformat(),
        "outcome_sha256": row[3],
        "outcome": None if result is None else result.payload(),
        "status": "pending" if result is None else result.status,
    }


def show_validation(dsn: str, attempt: UUID) -> dict[str, object]:
    if not isinstance(attempt, UUID):
        raise HistoryError("validation_configuration")
    with _database(dsn, write=False) as c, c.transaction():
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return _read(c, attempt)


class Journal:
    """One session lock per attempt; no long SQL transaction spans file checking."""

    def __init__(self, dsn: str, attempt: UUID, intent: Intent) -> None:
        if not isinstance(attempt, UUID) or not isinstance(intent, Intent):
            raise HistoryError("validation_configuration")
        self._dsn, self.attempt, self.intent = dsn, attempt, intent

    @contextmanager
    def session(self) -> Iterator["JournalSession"]:
        with _database(self._dsn, write=True) as c:
            locked = c.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", (str(self.attempt),)
            ).fetchone()
            if locked != (True,):
                raise HistoryError("validation_busy")
            c.execute(
                """INSERT INTO nima_validation.attempts (attempt_id,intent_sha256,document)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                (self.attempt, self.intent.digest, Jsonb(self.intent.payload())),
            )
            current = _read(c, self.attempt)
            if (
                current["intent_sha256"] != self.intent.digest
                or current["intent"] != self.intent.payload()
            ):
                raise HistoryError("validation_conflict")
            yield JournalSession(c, self.attempt, self.intent)


class JournalSession:
    def __init__(self, connection: Connection, attempt: UUID, intent: Intent) -> None:
        self.connection, self.attempt, self.intent = connection, attempt, intent

    def read(self) -> dict[str, object]:
        return _read(self.connection, self.attempt)

    def finish(self, result: Outcome) -> dict[str, object]:
        if result.intent_sha256 != self.intent.digest:
            raise HistoryError("validation_conflict")
        self.connection.execute(
            """INSERT INTO nima_validation.outcomes
            (attempt_id,intent_sha256,outcome_sha256,document) VALUES (%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            (self.attempt, self.intent.digest, result.digest, Jsonb(result.payload())),
        )
        current = self.read()
        if current["outcome_sha256"] != result.digest or current["outcome"] != result.payload():
            raise HistoryError("validation_conflict")
        return current
