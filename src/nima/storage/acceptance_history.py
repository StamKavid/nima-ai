"""Append-only citation attestations, isolated from source and legacy journals."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from nima.contracts.acceptance_history import (
    HistoryError,
    Intent,
    Outcome,
    Record,
    assessed_outcome,
    decode_intent,
    decode_outcome,
)
from nima.storage.connection import Connection, connect
from nima.storage.postgres import MigrationError, validate_schema

# Effective privileges include PUBLIC, inherited and column grants. Keep this
# adapter below DataOps: the operator's access registry/audit must not be imported.
_ROLE = """SELECT
  EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user AND
    (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)),
  has_database_privilege(current_user,current_database(),'CREATE'),
  EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspname IN
    ('nima','nima_processing','nima_validation') AND
    (pg_has_role(current_user,n.nspowner,'MEMBER')
     OR has_schema_privilege(current_user,n.oid,'CREATE'))),
  EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid
    WHERE n.nspname IN ('nima','nima_processing','nima_validation') AND
    pg_has_role(current_user,p.proowner,'MEMBER')),
  EXISTS (SELECT 1 FROM pg_class r JOIN pg_namespace n ON r.relnamespace=n.oid
    WHERE n.nspname IN ('nima','nima_processing','nima_validation') AND
    (pg_has_role(current_user,r.relowner,'MEMBER')
     OR (r.relkind='S' AND has_sequence_privilege(current_user,r.oid,'USAGE,SELECT,UPDATE'))
     OR (r.relkind IN ('r','p','v','m','f') AND
       (has_table_privilege(current_user,r.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
        OR has_any_column_privilege(current_user,r.oid,'UPDATE,REFERENCES')
        OR ((n.nspname,r.relname) NOT IN
          (('nima','schema_migrations'),('nima_validation','acceptance_attempts'),
           ('nima_validation','acceptance_outcomes')) AND
          (has_table_privilege(current_user,r.oid,'SELECT')
           OR has_any_column_privilege(current_user,r.oid,'SELECT')))
        OR ((NOT %(write)s OR (n.nspname,r.relname) NOT IN
          (('nima_validation','acceptance_attempts'),('nima_validation','acceptance_outcomes')))
          AND (has_table_privilege(current_user,r.oid,'INSERT')
               OR has_any_column_privilege(current_user,r.oid,'INSERT'))))))),
  has_table_privilege(current_user,'nima.schema_migrations','SELECT') AND
  has_table_privilege(current_user,'nima_validation.acceptance_attempts','SELECT') AND
  has_table_privilege(current_user,'nima_validation.acceptance_outcomes','SELECT') AND
  (NOT %(write)s OR
   (has_table_privilege(current_user,'nima_validation.acceptance_attempts','INSERT') AND
    has_table_privilege(current_user,'nima_validation.acceptance_outcomes','INSERT')))"""


@contextmanager
def _database(dsn: str, *, write: bool) -> Iterator[Connection]:
    if not isinstance(dsn, str) or not dsn.strip():
        raise HistoryError("acceptance_history_configuration")
    try:
        with connect(dsn) as c:
            c.execute("SET TIME ZONE 'UTC'")
            c.execute("SET row_security=off")
            validate_schema(c)
            row = c.execute(_ROLE, {"write": write}).fetchone()
            if row is None or any(row[:5]) or not row[5]:
                raise HistoryError("acceptance_history_database")
            yield c
    except MigrationError:
        raise HistoryError("acceptance_history_schema") from None
    except psycopg.Error:
        raise HistoryError("acceptance_history_database") from None


def _lookup(c: Connection, attempt: UUID) -> Record | None:
    row = c.execute(
        """SELECT a.intent_sha256,a.document,a.started_at,
        o.outcome_sha256,o.document,o.recorded_at,o.acceptance_body
        FROM nima_validation.acceptance_attempts a
        LEFT JOIN nima_validation.acceptance_outcomes o USING (attempt_id,intent_sha256)
        WHERE a.attempt_id=%s""",
        (attempt,),
    ).fetchone()
    if row is None:
        return None
    intent = decode_intent(row[1])
    outcome = None if row[4] is None else decode_outcome(row[4])
    if intent.digest != row[0] or (outcome is not None and outcome.digest != row[3]):
        raise HistoryError("acceptance_history_integrity")
    return Record(
        attempt,
        intent,
        cast(datetime, row[2]),
        outcome,
        cast(datetime | None, row[5]),
        cast(bytes | None, row[6]),
    )


def show_acceptance(dsn: str, attempt: UUID) -> Record:
    if not isinstance(attempt, UUID):
        raise HistoryError("acceptance_history_configuration")
    with _database(dsn, write=False) as c, c.transaction():
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        c.execute("SET LOCAL statement_timeout=5000")
        c.execute("SET LOCAL lock_timeout=2000")
        result = _lookup(c, attempt)
        if result is None:
            raise HistoryError("acceptance_history_unknown")
        return result


class Journal:
    """One attempt lock; callers look up history before creating current intent."""

    def __init__(self, dsn: str, attempt: UUID) -> None:
        if not isinstance(attempt, UUID):
            raise HistoryError("acceptance_history_configuration")
        self.dsn, self.attempt = dsn, attempt

    @contextmanager
    def session(self) -> Iterator["JournalSession"]:
        with _database(self.dsn, write=True) as c:
            row = c.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0))",
                ("nima.acceptance:" + str(self.attempt),),
            ).fetchone()
            if row != (True,):
                raise HistoryError("acceptance_history_busy")
            yield JournalSession(c, self.attempt)


class JournalSession:
    def __init__(self, connection: Connection, attempt: UUID) -> None:
        self.connection, self.attempt = connection, attempt

    def lookup(self) -> Record | None:
        return _lookup(self.connection, self.attempt)

    def register(self, intent: Intent) -> Record:
        if not isinstance(intent, Intent):
            raise HistoryError("acceptance_history_configuration")
        self.connection.execute(
            """INSERT INTO nima_validation.acceptance_attempts
            (attempt_id,intent_sha256,document) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
            (self.attempt, intent.digest, Jsonb(intent.payload())),
        )
        result = self.lookup()
        if result is None or result.intent != intent:
            raise HistoryError("acceptance_history_conflict")
        return result

    def finish(self, outcome: Outcome, body: bytes | None = None) -> Record:
        current = self.lookup()
        if current is None or outcome.intent_sha256 != current.intent.digest:
            raise HistoryError("acceptance_history_conflict")
        if outcome.execution_state == "assessed":
            if body is None or assessed_outcome(current.intent, body) != outcome:
                raise HistoryError("acceptance_history_integrity")
        elif body is not None:
            raise HistoryError("acceptance_history_integrity")
        with self.connection.transaction():
            self.connection.execute(
                """INSERT INTO nima_validation.acceptance_outcomes
                (attempt_id,intent_sha256,outcome_sha256,document,acceptance_body)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (
                    self.attempt,
                    current.intent.digest,
                    outcome.digest,
                    Jsonb(outcome.payload()),
                    body,
                ),
            )
            result = self.lookup()
            if result is None or result.outcome != outcome or result.body != body:
                raise HistoryError("acceptance_history_conflict")
        return result
