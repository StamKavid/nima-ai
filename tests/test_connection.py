"""Configured roles must own real migrations while connector limits remain enforced."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from nima.storage.connection import connect
from nima.storage.postgres import migrate


@contextmanager
def migration_owner(dsn: str) -> Iterator[str]:
    config = conninfo_to_dict(dsn)
    database = config["dbname"]
    assert isinstance(database, str) and database.startswith("nima_test_")
    role = "nima_connection_owner_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                sql.Identifier(role)
            )
        )
        try:
            admin.execute(
                sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                    sql.Identifier(database), sql.Identifier(role)
                )
            )
            yield role
        finally:
            admin.execute(sql.SQL("DROP OWNED BY {} CASCADE").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_requested_nologin_role_owns_schema_and_every_migrated_object(pg_dsn: str) -> None:
    with migration_owner(pg_dsn) as owner:
        with psycopg.connect(pg_dsn) as login:
            authenticated = login.execute("SELECT session_user").fetchone()
            assert authenticated is not None
        dsn = make_conninfo(pg_dsn, options="-c role=" + owner)
        migrate(dsn)
        migrate(dsn)
        with connect(dsn) as connection:
            assert connection.execute("SELECT current_user,session_user").fetchone() == (
                owner,
                authenticated[0],
            )
            assert connection.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='nima'"
            ).fetchone() == (owner,)
            assert connection.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname='nima'"
            ).fetchone() == (28,)
            assert connection.execute(
                """SELECT count(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='nima' AND pg_get_userbyid(c.relowner)<>%s""",
                (owner,),
            ).fetchone() == (0,)
            assert connection.execute(
                """SELECT count(*) FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='nima' AND pg_get_userbyid(p.proowner)<>%s""",
                (owner,),
            ).fetchone() == (0,)
            assert connection.execute("SHOW statement_timeout").fetchone() == ("30s",)
            assert connection.execute("SHOW lock_timeout").fetchone() == ("5s",)


@pytest.mark.parametrize("setting_source", ["dsn", "environment", "service"])
def test_startup_role_and_other_settings_survive_but_limits_are_enforced(
    setting_source: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with migration_owner(pg_dsn) as owner:
        options = (
            "-c role="
            + owner
            + " -c application_name=nima_role_regression -c statement_timeout=0 -c lock_timeout=0"
        )
        if setting_source == "dsn":
            dsn = make_conninfo(pg_dsn, options=options)
        elif setting_source == "environment":
            monkeypatch.setenv("PGOPTIONS", options)
            dsn = pg_dsn
        else:
            fields = conninfo_to_dict(pg_dsn)
            fields["options"] = options
            service = tmp_path / "pg_service.conf"
            pairs = []
            for key, value in fields.items():
                assert isinstance(value, str)
                pairs.append(key + "=" + value)
            service.write_text("[nima_connection_test]\n" + "\n".join(pairs) + "\n")
            service.chmod(0o600)
            monkeypatch.setenv("PGSERVICEFILE", str(service))
            dsn = "service=nima_connection_test"
        with connect(dsn) as connection:
            assert connection.autocommit
            assert connection.info.transaction_status is psycopg.pq.TransactionStatus.IDLE
            assert connection.execute("SELECT current_user").fetchone() == (owner,)
            assert connection.execute("SHOW application_name").fetchone() == (
                "nima_role_regression",
            )
            assert connection.execute("SHOW statement_timeout").fetchone() == ("30s",)
            assert connection.execute("SHOW lock_timeout").fetchone() == ("5s",)
            assert connection.info.get_parameters()["connect_timeout"] == "5"


def test_no_options_keeps_legacy_limits_and_autocommit(pg_dsn: str) -> None:
    with connect(pg_dsn) as connection:
        assert connection.autocommit
        assert connection.info.transaction_status is psycopg.pq.TransactionStatus.IDLE
        assert connection.execute("SHOW statement_timeout").fetchone() == ("30s",)
        assert connection.execute("SHOW lock_timeout").fetchone() == ("5s",)


def test_nonexistent_role_does_not_fall_back_or_create_schema(pg_dsn: str) -> None:
    with pytest.raises(psycopg.Error):
        migrate(make_conninfo(pg_dsn, options="-c role=nima_missing_" + uuid4().hex))
    with psycopg.connect(pg_dsn) as admin:
        assert admin.execute("SELECT to_regnamespace('nima')").fetchone() == (None,)


def test_unauthorized_role_cannot_fall_back_to_login_user(pg_dsn: str) -> None:
    limited = "nima_connection_login_" + uuid4().hex
    password = uuid4().hex
    with migration_owner(pg_dsn) as owner, psycopg.connect(pg_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                sql.Identifier(limited), sql.Literal(password)
            )
        )
        try:
            limited_dsn = make_conninfo(pg_dsn, user=limited, password=password)
            with psycopg.connect(limited_dsn) as login:
                assert login.execute("SELECT current_user").fetchone() == (limited,)
            with pytest.raises(psycopg.OperationalError, match="permission denied to set role"):
                connect(make_conninfo(limited_dsn, options="-c role=" + owner))
        finally:
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(limited)))


@pytest.mark.parametrize("fail_at", [1, 2])
@pytest.mark.parametrize(
    "error", [psycopg.OperationalError("synthetic setup failure"), KeyboardInterrupt()]
)
def test_setup_failure_or_interruption_closes_real_connection(
    fail_at: int, error: BaseException, pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = psycopg.connect(pg_dsn, autocommit=True)
    original = backend.execute
    calls = 0

    def execute(query: str) -> psycopg.Cursor[tuple[object, ...]]:
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise error
        return original(query)

    def connected(*args: object, **kwargs: object) -> psycopg.Connection[tuple[object, ...]]:
        return backend

    monkeypatch.setattr(backend, "execute", execute)
    monkeypatch.setattr(psycopg, "connect", connected)
    try:
        with pytest.raises(type(error)) as caught:
            connect(pg_dsn)
        assert caught.value is error and backend.closed
        assert calls == fail_at
    finally:
        backend.close()
