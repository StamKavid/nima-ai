"""Promoted normalization is derived data, not a new source observation."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from nima.dataops import promotion
from nima.dataops.promotion import PromotionError, promote_run
from nima.dataops.replay import prepare_replay
from nima.storage.postgres import NORMALIZER_VERSION, _migrations, migrate
from tests.test_analytics_snapshot import reader, seed, state
from tests.test_connection import migration_owner


def test_additive_upgrade_keeps_old_bodies_and_source_data(pg_dsn: str, tmp_path: Path) -> None:
    # Install exactly the seven recorded original migrations before testing upgrade.
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        c.execute(
            "CREATE SCHEMA nima; CREATE TABLE nima.schema_migrations "
            "(version integer PRIMARY KEY,sha256 text NOT NULL)"
        )
        for version in range(1, 8):
            body = files("nima.storage").joinpath(f"migrations/{version:04d}.sql").read_text()
            c.execute(body)
            c.execute(
                "INSERT INTO nima.schema_migrations VALUES (%s,%s)",
                (version, hashlib.sha256(body.encode()).hexdigest()),
            )
        old = c.execute(
            "SELECT version,sha256 FROM nima.schema_migrations ORDER BY version"
        ).fetchall()
        c.execute("INSERT INTO nima.raw_objects VALUES (repeat('a',64),12)")
    assert old[-1][1] == "c14bb9c4f84d6b5035b101a494b2ce01b7097f5a2ef49a5ab0ae70786d00e0c2"
    migrate(pg_dsn)
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as c:
        assert (
            c.execute(
                "SELECT version,sha256 FROM nima.schema_migrations "
                "WHERE version<=7 ORDER BY version"
            ).fetchall()
            == old
        )
        assert c.execute("SELECT * FROM nima.raw_objects").fetchall() == [("a" * 64, 12)]
        assert c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='nima_processing' ORDER BY tablename"
        ).fetchall() == [("metadata_snapshots",), ("replay_batches",), ("replay_results",)]
        assert c.execute("SELECT to_regclass('nima_processing.replayed_contracts')").fetchone() == (
            "nima_processing.replayed_contracts",
        )
        assert len(_migrations()) == 14


def test_configured_nologin_owner_owns_processing_schema_too(pg_dsn: str) -> None:
    from psycopg.conninfo import make_conninfo

    with migration_owner(pg_dsn) as owner:
        migrate(make_conninfo(pg_dsn, options="-c role=" + owner))
        with psycopg.connect(pg_dsn) as c:
            assert c.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='nima_processing'"
            ).fetchone() == (owner,)
            assert c.execute(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='nima_processing' AND pg_get_userbyid(c.relowner)<>%s",
                (owner,),
            ).fetchone() == (0,)


def test_prepared_replay_matches_published_bytes_without_creating_output(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.dataops.replay import prepare_replay, replay_run
    from nima.storage.postgres import NORMALIZER_VERSION
    from tests.test_analytics_snapshot import seed

    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    raw, prepared = prepare_replay(pg_dsn, run, root, NORMALIZER_VERSION)
    published = replay_run(pg_dsn, run, root, tmp_path / "out", NORMALIZER_VERSION)
    assert prepared == published
    assert raw == (tmp_path / "out" / (published.artifact_sha256 + ".json")).read_bytes()


def test_promoted_view_keeps_capture_time_and_exact_money_without_source_writes(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.dataops.promotion import promote_run
    from nima.dataops.replay import prepare_replay
    from nima.storage.postgres import NORMALIZER_VERSION
    from tests.test_analytics_snapshot import seed, state

    root = tmp_path / "archive"
    run = seed(pg_dsn, root, project=False)
    _, prepared = prepare_replay(pg_dsn, run, root, NORMALIZER_VERSION)
    before = state(pg_dsn)
    first = promote_run(pg_dsn, run, root, NORMALIZER_VERSION, prepared.artifact_sha256)
    again = promote_run(pg_dsn, run, root, NORMALIZER_VERSION, prepared.artifact_sha256)
    assert not first.replayed and again.replayed
    assert first.record_count == again.record_count == 1
    assert state(pg_dsn) == before
    with psycopg.connect(pg_dsn) as c:
        row = c.execute(
            "SELECT normalized,observed_at,processed_at,json_pointer "
            "FROM nima_processing.replayed_contracts"
        ).fetchone()
        assert row is not None and row[0]["net_amount"] == "1E+2"
        assert row[1].isoformat() == "2026-01-01T00:00:00+00:00" and row[2] > row[1]
        assert row[3] == "/content/0"
        assert c.execute("SELECT count(*) FROM nima_processing.replay_batches").fetchone() == (1,)


@contextmanager
def promoter(dsn: str) -> Iterator[str]:
    from psycopg import sql

    with reader(dsn) as (limited, role):
        with psycopg.connect(dsn) as admin:
            admin.execute(
                sql.SQL("GRANT USAGE ON SCHEMA nima_processing TO {}").format(sql.Identifier(role))
            )
            admin.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT ON nima_processing.replay_batches,"
                    "nima_processing.replay_results TO {}"
                ).format(sql.Identifier(role))
            )
            admin.execute(
                sql.SQL("GRANT SELECT ON nima_processing.replayed_contracts TO {}").format(
                    sql.Identifier(role)
                )
            )
        yield limited


def selection(dsn: str, root: Path) -> tuple[UUID, str]:
    run = seed(dsn, root, project=False)
    return run, prepare_replay(dsn, run, root, NORMALIZER_VERSION)[1].artifact_sha256


def test_limited_promoter_cannot_write_source_and_reader_cannot_promote(
    pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    before = state(pg_dsn)
    with (
        reader(pg_dsn) as (limited, _),
        pytest.raises(PromotionError, match="^promotion_database$"),
    ):
        promote_run(limited, run, root, NORMALIZER_VERSION, digest)
    with promoter(pg_dsn) as limited:
        with psycopg.connect(limited) as c:
            assert c.execute(
                "SELECT has_table_privilege('nima.ingest_runs','UPDATE'),"
                "has_table_privilege('nima.observations','INSERT')"
            ).fetchone() == (False, False)
        assert not promote_run(limited, run, root, NORMALIZER_VERSION, digest).replayed
        assert promote_run(limited, run, root, NORMALIZER_VERSION, digest).replayed
    assert state(pg_dsn) == before


@pytest.mark.parametrize("bad", ["bad", "A" * 64, None, []])
def test_invalid_selected_digest_fails_before_io(
    bad: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import cast
    from uuid import uuid4

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Bad digest must not touch SQL or files")

    monkeypatch.setattr(promotion, "prepare_replay", forbidden)
    with pytest.raises(PromotionError, match="^promotion_input$"):
        promote_run("not-read", uuid4(), tmp_path / "raw", NORMALIZER_VERSION, cast(str, bad))


def test_wrong_selection_and_missing_originals_publish_no_sql(pg_dsn: str, tmp_path: Path) -> None:
    from nima.dataops.replay import ReplayError

    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    with pytest.raises(PromotionError, match="^promotion_selection$"):
        promote_run(pg_dsn, run, root, NORMALIZER_VERSION, "0" * 64)
    next(root.rglob("*.body")).unlink()
    with pytest.raises(ReplayError, match="^replay_evidence$"):
        promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest)
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima_processing.replay_batches").fetchone() == (0,)


@pytest.mark.parametrize("status", ["running", "failed", "interrupted", "unmanaged"])
def test_nonfinal_captures_remain_replay_only(status: str, pg_dsn: str, tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run, _ = selection(pg_dsn, root)
    with psycopg.connect(pg_dsn) as c:
        c.execute("UPDATE nima.ingest_runs SET status=%s WHERE run_id=%s", (status, run))
    digest = prepare_replay(pg_dsn, run, root, NORMALIZER_VERSION)[1].artifact_sha256
    with pytest.raises(PromotionError, match="^promotion_capture$"):
        promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest)


@pytest.mark.parametrize("kind", ["scope", "lease"])
def test_source_recheck_and_existing_collector_lease_guard_promotion(
    kind: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage.runs import run_lock_key

    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    original = prepare_replay

    def changed(*args: object, **kwargs: object) -> object:
        prepared = original(pg_dsn, run, root, NORMALIZER_VERSION)
        with psycopg.connect(pg_dsn) as c:
            c.execute("UPDATE nima.ingest_runs SET status='quarantined' WHERE run_id=%s", (run,))
        return prepared

    with psycopg.connect(pg_dsn, autocommit=True) as collector:
        if kind == "lease":
            collector.execute("SELECT pg_advisory_lock(%s)", (run_lock_key(run),))
        else:
            monkeypatch.setattr(promotion, "prepare_replay", changed)
        with pytest.raises(
            PromotionError, match="^promotion_busy$" if kind == "lease" else "^promotion_scope$"
        ):
            promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest)
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima_processing.replay_batches").fetchone() == (0,)


@pytest.mark.parametrize("damage", ["header", "record"])
def test_conflicting_persisted_batch_cannot_be_silently_reused(
    damage: str, pg_dsn: str, tmp_path: Path
) -> None:
    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest)
    # Deliberate privileged corruption in a disposable database, not app role behaviour.
    with psycopg.connect(pg_dsn) as c:
        if damage == "header":
            c.execute(
                "ALTER TABLE nima_processing.replay_batches "
                "DISABLE TRIGGER replay_batches_immutable"
            )
            c.execute("UPDATE nima_processing.replay_batches SET normalized_count=0")
            c.execute(
                "ALTER TABLE nima_processing.replay_batches ENABLE TRIGGER replay_batches_immutable"
            )
        else:
            c.execute(
                "ALTER TABLE nima_processing.replay_results "
                "DISABLE TRIGGER replay_results_immutable"
            )
            c.execute(
                "UPDATE nima_processing.replay_results "
                "SET normalized=jsonb_set(normalized,'{title}','\"changed\"')"
            )
            c.execute(
                "ALTER TABLE nima_processing.replay_results ENABLE TRIGGER replay_results_immutable"
            )
    with pytest.raises(PromotionError, match="^promotion_conflict$"):
        promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest)


@pytest.mark.parametrize("table", ["replay_batches", "replay_results"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_processing_rows_are_immutable_even_to_owner(
    table: str, operation: str, pg_dsn: str, tmp_path: Path
) -> None:
    from psycopg import sql

    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest)
    statement = (
        sql.SQL("UPDATE {} SET replay_sha256=replay_sha256")
        if operation == "UPDATE"
        else sql.SQL("DELETE FROM {}")
        if operation == "DELETE"
        else sql.SQL("TRUNCATE {} CASCADE")
    )
    with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        c.execute(statement.format(sql.Identifier("nima_processing", table)))


@pytest.mark.parametrize("default_isolation", ["read committed", "repeatable read"])
def test_two_concurrent_promoters_converge_to_one_complete_batch(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, default_isolation: str
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    barrier = Barrier(2)

    def together(*args: object, **kwargs: object) -> object:
        result = prepare_replay(pg_dsn, run, root, NORMALIZER_VERSION)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(promotion, "prepare_replay", together)
    with promoter(pg_dsn) as limited, ThreadPoolExecutor(max_workers=2) as pool:
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict

        role = conninfo_to_dict(limited)["user"]
        assert isinstance(role, str)
        with psycopg.connect(pg_dsn) as admin:
            admin.execute(
                sql.SQL("ALTER ROLE {} SET default_transaction_isolation TO {}").format(
                    sql.Identifier(role),
                    sql.Literal(default_isolation),
                )
            )
        a = pool.submit(promote_run, limited, run, root, NORMALIZER_VERSION, digest)
        b = pool.submit(promote_run, limited, run, root, NORMALIZER_VERSION, digest)
        assert sorted([a.result(timeout=10).replayed, b.result(timeout=10).replayed]) == [
            False,
            True,
        ]
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima_processing.replay_batches").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM nima_processing.replay_results").fetchone() == (1,)


@pytest.mark.parametrize("empty", [False, True])
def test_quarantine_and_committed_empty_capture_promote_explicitly(
    empty: bool, pg_dsn: str, tmp_path: Path
) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from nima.ingestion.archive import Archive
    from nima.storage.postgres import PageStore
    from tests.test_collection import QUERY, body

    root = tmp_path / "raw"
    migrate(pg_dsn)
    run = uuid4()
    store = PageStore(pg_dsn, Archive(root))
    store.start_run(run, QUERY)
    raw = body(total=0) if empty else body(total=1, title=False)
    store.commit_page(run, raw, observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    with psycopg.connect(pg_dsn) as c:
        c.execute("UPDATE nima.ingest_runs SET status='quarantined' WHERE run_id=%s", (run,))
    digest = prepare_replay(pg_dsn, run, root, NORMALIZER_VERSION)[1].artifact_sha256
    before = state(pg_dsn)
    with promoter(pg_dsn) as limited:
        result = promote_run(limited, run, root, NORMALIZER_VERSION, digest)
    assert result.normalized_count == 0 and result.quarantined_count == (0 if empty else 1)
    assert state(pg_dsn) == before
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima_processing.replayed_contracts").fetchone() == (
            0,
        )
        rows = c.execute(
            "SELECT status,quarantine_reason FROM nima_processing.replay_results"
        ).fetchall()
        assert rows == [] if empty else rows[0][0] == "quarantined" and rows[0][1]


@pytest.mark.parametrize("bad", ["location", "run", "source_id"])
def test_sql_rejects_results_outside_the_selected_source_location(
    bad: str, pg_dsn: str, tmp_path: Path
) -> None:
    from uuid import uuid4

    from psycopg.types.json import Jsonb

    root = tmp_path / "raw"
    run, digest = selection(pg_dsn, root)
    promote_run(pg_dsn, run, root, NORMALIZER_VERSION, digest)
    with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.IntegrityError):
        c.execute(
            """INSERT INTO nima_processing.replay_results
            (replay_sha256,source_run_id,page_number,record_index,content_sha256,status,
            source_id,normalized) VALUES (%s,%s,0,%s,repeat('a',64),'normalized',%s,%s)""",
            (
                digest,
                uuid4() if bad == "run" else run,
                1 if bad == "location" else 0,
                "kimdis:X",
                Jsonb({"source_id": "kimdis:Y" if bad == "source_id" else "kimdis:X"}),
            ),
        )
