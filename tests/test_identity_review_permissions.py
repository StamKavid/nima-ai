"""Separate disposable local logins prove DB attribution, not human authentication."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from nima.identity import review_store
from nima.identity.review_types import ReviewError
from tests.test_identity_review_accept import ledger, request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_support import source_snapshot


@contextmanager
def principals(dsn: str) -> Iterator[tuple[str, str, str]]:
    config = conninfo_to_dict(dsn)
    assert config.get("host") in {"127.0.0.1", "localhost", "::1"}
    database = config.get("dbname")
    assert isinstance(database, str) and database.startswith("nima_test_")
    roles = ["nima_review_test_" + uuid4().hex for _ in range(3)]
    created = []
    with psycopg.connect(dsn, autocommit=True) as admin:
        try:
            for index, role in enumerate(roles):
                identifier = sql.Identifier(role)
                admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(identifier))
                created.append(role)
                admin.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(database), identifier
                    )
                )
                admin.execute(sql.SQL("GRANT USAGE ON SCHEMA nima TO {}").format(identifier))
                admin.execute(
                    sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA nima TO {}").format(identifier)
                )
                if index < 2:
                    admin.execute(
                        sql.SQL(
                            "GRANT INSERT ON nima.identity_review_heads,"
                            "nima.identity_entities,nima.identity_review_events TO {}"
                        ).format(identifier)
                    )
                    admin.execute(
                        sql.SQL(
                            "GRANT UPDATE(revision,latest_event_id) ON "
                            "nima.identity_review_heads TO {}"
                        ).format(identifier)
                    )
            connections = [make_conninfo(dsn, user=role) for role in roles]
            yield connections[0], connections[1], connections[2]
        finally:
            errors = []
            for role in reversed(created):
                try:
                    # These unique roles own no application objects. DROP OWNED
                    # revokes only their disposable grants, including CONNECT.
                    admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                    admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
                except psycopg.Error as error:
                    errors.append(error)
            if errors:
                raise RuntimeError("test_review_role_cleanup") from None


def test_session_login_is_recorded_with_limited_operator_grants(
    pg_dsn: str, tmp_path: Path
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    before = source_snapshot(pg_dsn)
    with principals(pg_dsn) as (first, second, readonly):
        ack = review_store.review(first, chosen, report=parsed)
        assert ack.attribution_assurance == "database_principal_only"
        with psycopg.connect(first) as connection:
            assert connection.execute(
                "SELECT database_principal=session_user FROM nima.identity_review_events"
            ).fetchone() == (True,)
            assert connection.execute("SELECT current_user=session_user").fetchone() == (True,)
        assert review_store.review(first, chosen).replayed
        with pytest.raises(ReviewError, match="^review_conflict$") as error:
            review_store.review(second, chosen)
        assert str(error.value) == "review_conflict"
        assert ledger(pg_dsn) == (1, 1, 1)
        assert source_snapshot(pg_dsn) == before
    with psycopg.connect(pg_dsn) as connection:
        # No role created by this test remains; the recorded login is history.
        recorded = connection.execute(
            "SELECT database_principal FROM nima.identity_review_events"
        ).fetchone()
        assert recorded is not None
        assert (
            connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (recorded[0],)).fetchone()
            is None
        )


def test_read_only_login_cannot_write_or_replay_as_another_principal(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    with principals(pg_dsn) as (first, second, readonly):
        with pytest.raises(ReviewError, match="^review_permission$"):
            review_store.review(readonly, chosen, report=parsed)
        assert ledger(pg_dsn) == (0, 0, 0)
        review_store.review(first, chosen, report=parsed)
        with pytest.raises(ReviewError, match="^review_conflict$"):
            review_store.review(readonly, chosen)
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            psycopg.connect(readonly) as connection,
        ):
            connection.execute("UPDATE nima.identity_review_heads SET revision=revision+1")
        assert ledger(pg_dsn) == (1, 1, 1)
