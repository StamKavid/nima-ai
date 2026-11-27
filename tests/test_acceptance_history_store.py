"""Native PostgreSQL constraints, dedicated roles and append-only attempt lifecycle."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from importlib.resources import files
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from nima.contracts.acceptance_history import Intent, Outcome
from nima.dataops.access_grants import render_grants
from nima.storage.postgres import migrate


@contextmanager
def journal_role(dsn: str, *, write: bool = True) -> Iterator[str]:
    role = "nima_acceptance_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        try:
            c.execute(render_grants("acceptance-writer" if write else "acceptance-reader", role))
            yield make_conninfo(dsn, user=role)
        finally:
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_additive_tables_and_unchanged_legacy_checksums(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        assert c.execute(
            """SELECT to_regclass('nima_validation.acceptance_attempts'),
            to_regclass('nima_validation.acceptance_outcomes')"""
        ).fetchone() == (
            "nima_validation.acceptance_attempts",
            "nima_validation.acceptance_outcomes",
        )
        rows = c.execute(
            "SELECT version,sha256 FROM nima.schema_migrations ORDER BY version"
        ).fetchall()
        assert len(rows) == 15
        assert rows[:14] == [
            (
                i,
                hashlib.sha256(
                    files("nima.storage").joinpath(f"migrations/{i:04d}.sql").read_bytes()
                ).hexdigest(),
            )
            for i in range(1, 15)
        ]
        assert c.execute("SELECT count(*) FROM nima_validation.attempts").fetchone() == (0,)


def test_database_stamps_and_immutable_rows(pg_dsn: str) -> None:
    migrate(pg_dsn)
    attempt = uuid4()
    intent = Intent("a" * 64, "b" * 64)
    outcome = Outcome(intent.digest, "refused", None, None, "acceptance_evidence")
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(
            """INSERT INTO nima_validation.acceptance_attempts
            (attempt_id,intent_sha256,document,started_at,database_principal) VALUES
            (%s,%s,%s,'2000-01-01','forged')
            """,
            (attempt, intent.digest, Jsonb(intent.payload())),
        )
        c.execute(
            """INSERT INTO nima_validation.acceptance_outcomes
            (attempt_id,intent_sha256,outcome_sha256,document,recorded_at,database_principal)
            VALUES (%s,%s,%s,%s,'2000-01-01','forged')
            """,
            (attempt, intent.digest, outcome.digest, Jsonb(outcome.payload())),
        )
        assert c.execute(
            """SELECT started_at>'2000-01-02'::timestamptz,database_principal=current_user
            FROM nima_validation.acceptance_attempts"""
        ).fetchone() == (True, True)
        assert c.execute(
            """SELECT recorded_at>'2000-01-02'::timestamptz,database_principal=current_user
            FROM nima_validation.acceptance_outcomes"""
        ).fetchone() == (True, True)
    for table in ("acceptance_attempts", "acceptance_outcomes"):
        for verb in ("UPDATE", "DELETE", "TRUNCATE"):
            statement = {
                "UPDATE": "UPDATE {} SET attempt_id=attempt_id",
                "DELETE": "DELETE FROM {}",
                "TRUNCATE": "TRUNCATE {} CASCADE",
            }[verb]
            with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.Error):
                c.execute(sql.SQL(statement).format(sql.Identifier("nima_validation", table)))


@pytest.mark.parametrize(
    "fault",
    [
        "missing_attempt",
        "intent",
        "extra",
        "body",
        "null_fitness",
        "fake_fitness",
        "interrupted",
        "limit",
        "empty",
        "hash",
    ],
)
def test_sql_refuses_contradictory_terminal_rows(pg_dsn: str, fault: str) -> None:
    migrate(pg_dsn)
    attempt = uuid4()
    intent = Intent("a" * 64, "b" * 64)
    document = Outcome(intent.digest, "refused", None, None, "acceptance_evidence").payload()
    body = None
    with psycopg.connect(pg_dsn) as c:
        if fault != "missing_attempt":
            c.execute(
                """INSERT INTO nima_validation.acceptance_attempts
                (attempt_id,intent_sha256,document) VALUES (%s,%s,%s)
                """,
                (attempt, intent.digest, Jsonb(intent.payload())),
            )
        if fault == "intent":
            document["intent_sha256"] = "f" * 64
        elif fault == "extra":
            document["extra"] = "PRIVATE"
        elif fault == "body":
            body = b"not allowed on refusal"
        elif fault == "fake_fitness":
            document["data_fitness"] = "blocked"
        elif fault == "interrupted":
            document["refusal_code"] = "acceptance_interrupted"
        elif fault != "missing_attempt":
            document.update(
                execution_state="assessed",
                data_fitness="ready",
                refusal_code=None,
                acceptance_sha256="f" * 64,
            )
            if fault == "null_fitness":
                document["data_fitness"] = None
            elif fault == "limit":
                body = b"x" * 65537
            elif fault == "empty":
                body = b""
            elif fault == "hash":
                body = b"wrong hash"
            if fault in {"limit", "empty"}:
                assert body is not None
                document["acceptance_sha256"] = hashlib.sha256(body).hexdigest()
        with pytest.raises(psycopg.Error) as refused:
            c.execute(
                """INSERT INTO nima_validation.acceptance_outcomes
                (attempt_id,intent_sha256,outcome_sha256,document,acceptance_body)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (attempt, intent.digest, "e" * 64, Jsonb(document), body),
            )
        assert refused.value.sqlstate == ("23503" if fault == "missing_attempt" else "23514")


def test_journal_commits_pending_and_reuses_only_identical_terminal(pg_dsn: str) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage.acceptance_history import Journal, show_acceptance

    migrate(pg_dsn)
    attempt, intent = uuid4(), Intent("a" * 64, "b" * 64)
    with journal_role(pg_dsn) as writer, journal_role(pg_dsn, write=False) as reader:
        with Journal(writer, attempt).session() as session:
            assert session.lookup() is None
            pending = session.register(intent)
            assert pending.execution_state == "pending"
            assert show_acceptance(reader, attempt) == pending
            assert session.register(intent) == pending
            with (
                pytest.raises(HistoryError, match="acceptance_history_busy"),
                Journal(writer, attempt).session(),
            ):
                pytest.fail("Concurrent lock admitted")
            outcome = Outcome(intent.digest, "refused", None, None, "acceptance_evidence")
            completed = session.finish(outcome)
            assert completed.started_at == pending.started_at
            assert session.finish(outcome) == completed
            with pytest.raises(HistoryError, match="acceptance_history_conflict"):
                session.finish(Outcome(intent.digest, "refused", None, None, "acceptance_input"))
        assert show_acceptance(reader, attempt) == completed
        with Journal(writer, attempt).session() as session:
            assert session.lookup() == completed
            with pytest.raises(HistoryError, match="acceptance_history_conflict"):
                session.register(Intent("c" * 64, "b" * 64))
        with (
            pytest.raises(HistoryError, match="acceptance_history_database"),
            Journal(reader, uuid4()).session(),
        ):
            pytest.fail("Reader became writer")
    with pytest.raises(HistoryError, match="acceptance_history_database"):
        show_acceptance(pg_dsn, attempt)


def test_sql_body_boundary_uses_sha256_without_an_extension(pg_dsn: str) -> None:
    migrate(pg_dsn)
    attempt = uuid4()
    intent = Intent("a" * 64, "b" * 64)
    body = b"x" * 65536
    outcome = Outcome(intent.digest, "assessed", "ready", hashlib.sha256(body).hexdigest(), None)
    with psycopg.connect(pg_dsn) as c:
        c.execute(
            """INSERT INTO nima_validation.acceptance_attempts
            (attempt_id,intent_sha256,document) VALUES (%s,%s,%s)
            """,
            (attempt, intent.digest, Jsonb(intent.payload())),
        )
        c.execute(
            """INSERT INTO nima_validation.acceptance_outcomes
            (attempt_id,intent_sha256,outcome_sha256,document,acceptance_body) VALUES
            (%s,%s,%s,%s,%s)
            """,
            (attempt, intent.digest, outcome.digest, Jsonb(outcome.payload()), body),
        )
        assert c.execute(
            "SELECT octet_length(acceptance_body) FROM nima_validation.acceptance_outcomes"
        ).fetchone() == (65536,)
        assert c.execute(
            "SELECT count(*) FROM pg_extension WHERE extname='pgcrypto'"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "grant",
    [
        "GRANT SELECT ON nima.observations TO {}",
        "GRANT SELECT(source_id) ON nima.observations TO {}",
        "GRANT INSERT(source_id) ON nima.observations TO {}",
        "GRANT UPDATE(document) ON nima_validation.acceptance_attempts TO {}",
        "GRANT REFERENCES(document) ON nima_validation.acceptance_attempts TO {}",
        "GRANT TRUNCATE ON nima_validation.acceptance_attempts TO {}",
        "GRANT SELECT ON nima_validation.attempts TO {}",
        "GRANT INSERT ON nima_validation.outcomes TO {}",
        "GRANT CREATE ON SCHEMA nima_processing TO {}",
        "GRANT SELECT ON SEQUENCE nima.observations_observation_id_seq TO {}",
        "ALTER ROLE {} CREATEDB",
        "ALTER ROLE {} CREATEROLE",
        "ALTER ROLE {} REPLICATION",
        "ALTER ROLE {} BYPASSRLS",
    ],
)
def test_effective_privilege_excess_is_rejected(pg_dsn: str, grant: str) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage.acceptance_history import Journal

    migrate(pg_dsn)
    with journal_role(pg_dsn) as writer, psycopg.connect(pg_dsn, autocommit=True) as c:
        role = str(psycopg.conninfo.conninfo_to_dict(writer)["user"])
        c.execute(sql.SQL(grant).format(sql.Identifier(role)))
        with (
            pytest.raises(HistoryError, match="^acceptance_history_database$"),
            Journal(writer, uuid4()).session(),
        ):
            pytest.fail("Excess role admitted")


@pytest.mark.parametrize("source", ["public", "inherited", "owner_member", "function_owner"])
def test_indirect_privilege_and_ownership_excess(pg_dsn: str, source: str) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage.acceptance_history import Journal

    migrate(pg_dsn)
    with journal_role(pg_dsn) as writer, psycopg.connect(pg_dsn, autocommit=True) as c:
        role = str(psycopg.conninfo.conninfo_to_dict(writer)["user"])
        parent = "nima_parent_" + uuid4().hex
        c.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(parent)))
        try:
            if source == "public":
                c.execute("GRANT SELECT(source_id) ON nima.observations TO PUBLIC")
            elif source == "inherited":
                c.execute(
                    sql.SQL("GRANT SELECT(source_id) ON nima.observations TO {}").format(
                        sql.Identifier(parent)
                    )
                )
                c.execute(
                    sql.SQL("GRANT {} TO {}").format(sql.Identifier(parent), sql.Identifier(role))
                )
            elif source == "owner_member":
                c.execute(
                    sql.SQL("ALTER TABLE nima.observations OWNER TO {}").format(
                        sql.Identifier(parent)
                    )
                )
                c.execute(
                    sql.SQL("GRANT {} TO {}").format(sql.Identifier(parent), sql.Identifier(role))
                )
            else:
                c.execute(
                    "CREATE FUNCTION nima_validation.excess() RETURNS int "
                    "LANGUAGE sql AS 'SELECT 1'"
                )
                c.execute(
                    sql.SQL("ALTER FUNCTION nima_validation.excess() OWNER TO {}").format(
                        sql.Identifier(role)
                    )
                )
            with (
                pytest.raises(HistoryError, match="^acceptance_history_database$"),
                Journal(writer, uuid4()).session(),
            ):
                pytest.fail("Indirect excess role admitted")
        finally:
            c.execute("REVOKE SELECT(source_id) ON nima.observations FROM PUBLIC")
            c.execute(
                sql.SQL("REASSIGN OWNED BY {} TO CURRENT_USER").format(sql.Identifier(parent))
            )
            c.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(parent)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(parent)))


@pytest.mark.parametrize("fault", ["intent_hash", "outcome_hash", "composite_fk"])
def test_record_integrity_and_composite_fk(pg_dsn: str, fault: str) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage.acceptance_history import show_acceptance

    migrate(pg_dsn)
    attempt, intent = uuid4(), Intent("a" * 64, "b" * 64)
    key = "f" * 64 if fault == "intent_hash" else intent.digest
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(
            "INSERT INTO nima_validation.acceptance_attempts "
            "(attempt_id,intent_sha256,document) VALUES (%s,%s,%s)",
            (attempt, key, Jsonb(intent.payload())),
        )
        if fault != "intent_hash":
            outcome = Outcome(
                "f" * 64 if fault == "composite_fk" else key,
                "refused",
                None,
                None,
                "acceptance_evidence",
            )

            def insert() -> None:
                c.execute(
                    "INSERT INTO nima_validation.acceptance_outcomes "
                    "(attempt_id,intent_sha256,outcome_sha256,document) VALUES (%s,%s,%s,%s)",
                    (attempt, outcome.intent_sha256, "e" * 64, Jsonb(outcome.payload())),
                )

            if fault == "composite_fk":
                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    insert()
                return
            insert()
    with (
        journal_role(pg_dsn, write=False) as reader,
        pytest.raises(HistoryError, match="acceptance_history_integrity"),
    ):
        show_acceptance(reader, attempt)


def test_adapter_failure_paths_and_refused_body(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage import acceptance_history as store

    for dsn in ("", "host=127.0.0.1 port=1 connect_timeout=1"):
        with pytest.raises(HistoryError):
            store.show_acceptance(dsn, uuid4())
    with pytest.raises(HistoryError):
        store.show_acceptance("", cast(Any, "bad"))
    with pytest.raises(HistoryError):
        store.Journal("", cast(Any, "bad"))
    migrate(pg_dsn)
    with journal_role(pg_dsn) as writer:
        with store.Journal(writer, uuid4()).session() as journal:
            with pytest.raises(HistoryError):
                journal.register(cast(Any, None))
            outcome = Outcome("a" * 64, "refused", None, None, "acceptance_evidence")
            with pytest.raises(HistoryError):
                journal.finish(outcome)
            intent = Intent("a" * 64, "b" * 64)
            journal.register(intent)
            with pytest.raises(HistoryError):
                journal.finish(outcome)
            with pytest.raises(HistoryError):
                journal.finish(replace(outcome, intent_sha256=intent.digest), b"forbidden")
            with pytest.raises(HistoryError):
                journal.finish(Outcome(intent.digest, "assessed", "ready", "c" * 64, None))
            with monkeypatch.context() as patch:
                patch.setattr(journal, "lookup", lambda: None)
                with pytest.raises(HistoryError):
                    journal.register(intent)
        with psycopg.connect(pg_dsn, autocommit=True) as c:
            c.execute("DROP TABLE nima.schema_migrations")
        with (
            pytest.raises(HistoryError, match="acceptance_history_schema"),
            store.Journal(writer, uuid4()).session(),
        ):
            pytest.fail("Unmigrated journal admitted")


def test_terminal_transaction_rolls_back_conflicting_readback(
    pg_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage.acceptance_history import Journal

    migrate(pg_dsn)
    with journal_role(pg_dsn) as writer, Journal(writer, uuid4()).session() as journal:
        pending = journal.register(Intent("a" * 64, "b" * 64))
        outcome = Outcome(pending.intent.digest, "refused", None, None, "acceptance_evidence")
        lookup = journal.lookup
        calls = 0

        def failed_readback() -> Any:
            nonlocal calls
            calls += 1
            return lookup() if calls == 1 else None

        with monkeypatch.context() as patch:
            patch.setattr(journal, "lookup", failed_readback)
            with pytest.raises(HistoryError):
                journal.finish(outcome)
        assert journal.lookup() == pending


def test_populated_legacy_journal_survives_additive_upgrade(pg_dsn: str) -> None:
    from nima.contracts.history import Outcome as LegacyOutcome
    from tests.test_validation_history import intent as legacy_intent

    with psycopg.connect(pg_dsn, autocommit=True) as c, c.transaction():
        c.execute(
            "CREATE SCHEMA nima; CREATE TABLE nima.schema_migrations "
            "(version integer PRIMARY KEY,sha256 text NOT NULL)"
        )
        for version in range(1, 15):
            body = files("nima.storage").joinpath(f"migrations/{version:04d}.sql").read_bytes()
            c.execute(body.decode())
            c.execute(
                "INSERT INTO nima.schema_migrations VALUES (%s,%s)",
                (version, hashlib.sha256(body).hexdigest()),
            )
        intent = legacy_intent()
        outcome = LegacyOutcome(intent.digest, "passed", "byte_equivalence", "ok", "f" * 64, 7, 5)
        attempt = uuid4()
        c.execute(
            "INSERT INTO nima_validation.attempts (attempt_id,intent_sha256,document) "
            "VALUES (%s,%s,%s)",
            (attempt, intent.digest, Jsonb(intent.payload())),
        )
        c.execute(
            "INSERT INTO nima_validation.outcomes "
            "(attempt_id,intent_sha256,outcome_sha256,document) VALUES (%s,%s,%s,%s)",
            (attempt, intent.digest, outcome.digest, Jsonb(outcome.payload())),
        )

    def legacy() -> list[tuple[object, ...]]:
        with psycopg.connect(pg_dsn) as c:
            return c.execute(
                "SELECT row_to_json(a)::text,row_to_json(o)::text "
                "FROM nima_validation.attempts a JOIN nima_validation.outcomes o "
                "USING(attempt_id,intent_sha256)"
            ).fetchall()

    before = legacy()
    migrate(pg_dsn)
    migrate(pg_dsn)
    assert legacy() == before


@pytest.mark.parametrize(
    "table,privilege",
    [
        ("nima.schema_migrations", "SELECT"),
        ("nima_validation.acceptance_attempts", "SELECT"),
        ("nima_validation.acceptance_attempts", "INSERT"),
        ("nima_validation.acceptance_outcomes", "SELECT"),
        ("nima_validation.acceptance_outcomes", "INSERT"),
    ],
)
def test_every_writer_table_grant_is_necessary(pg_dsn: str, table: str, privilege: str) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage.acceptance_history import Journal

    migrate(pg_dsn)
    with journal_role(pg_dsn) as writer, psycopg.connect(pg_dsn, autocommit=True) as c:
        role = str(psycopg.conninfo.conninfo_to_dict(writer)["user"])
        c.execute(
            sql.SQL("REVOKE {} ON {} FROM {}").format(
                sql.SQL(privilege), sql.Identifier(*table.split(".")), sql.Identifier(role)
            )
        )
        with (
            pytest.raises(HistoryError, match="acceptance_history_database"),
            Journal(writer, uuid4()).session(),
        ):
            pytest.fail("Insufficient journal role admitted")


def test_rls_cannot_hide_an_existing_attempt(pg_dsn: str) -> None:
    from nima.contracts.acceptance_history import HistoryError
    from nima.storage.acceptance_history import Journal, show_acceptance

    migrate(pg_dsn)
    attempt = uuid4()
    with journal_role(pg_dsn) as writer, Journal(writer, attempt).session() as journal:
        journal.register(Intent("a" * 64, "b" * 64))
    with psycopg.connect(pg_dsn) as c:
        c.execute("ALTER TABLE nima_validation.acceptance_attempts ENABLE ROW LEVEL SECURITY")
        c.execute("CREATE POLICY hide ON nima_validation.acceptance_attempts USING(false)")
    with (
        journal_role(pg_dsn, write=False) as reader,
        pytest.raises(HistoryError, match="acceptance_history_database"),
    ):
        show_acceptance(reader, attempt)
