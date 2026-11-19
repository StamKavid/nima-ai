"""The review ledger is additive, constrained and immutable on real PostgreSQL."""

import hashlib
from importlib.resources import files
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import Connection, _migrations, check_schema, migrate
from tests.test_identity_report import seed
from tests.test_kimdis_pages import record
from tests.test_registry_cohort import registry_import

OLD_HASHES = (
    "333be400de3b608f124e76e1c685b510869630f3e6a902d82cbf82f538e7f451",
    "aff9c553dde163ceea0ce750e1f064cf47bf609298cabd16d57c1002af771faf",
    "3d1934a362ef9afbe2e08d20dc28eea62c855b3f6b959aeabc95186a19fb12cb",
    "d8532d0d003e11b50b9a8c1cdfb0876f5fa7c2e5ae4e33e7b4b121643e0be215",
    "15b8283d2a64615bc1f4b1cb611fd990abbbacb177c46d3c82178c5e110f3902",
    "de8c7af5ec1643847f2145c247e4d12deb4bf90f1ecf056f774895345c3bce0d",
)


def test_packaged_migration_preserves_all_six_original_checksums() -> None:
    migrations = _migrations()
    assert [item[0] for item in migrations] == list(range(1, 14))
    assert tuple(item[2] for item in migrations[:6]) == OLD_HASHES
    assert migrations[6][1] == files("nima.storage").joinpath("migrations/0007.sql").read_text()


def head(connection: Connection, run: UUID, *, role: str = "buyer") -> int:
    row = connection.execute(
        """INSERT INTO nima.identity_review_heads
        (observation_id, projection_version, role, ordinal,
         run_id, source_id, normalizer_version, content_sha256)
        SELECT observation_id, %s, %s, 0, run_id, source_id, normalizer_version, content_sha256
        FROM nima.observations WHERE run_id=%s RETURNING observation_id""",
        (PROJECTION_VERSION, role, run),
    ).fetchone()
    assert row is not None and isinstance(row[0], int)
    return row[0]


def event(
    connection: Connection,
    observation: int,
    selected: UUID,
    *,
    request: UUID | None = None,
    entity: UUID | None = None,
    operation: str = "reject",
    revision: int = 1,
    number: str = "1",
) -> UUID:
    request = request or uuid4()
    connection.execute(
        """INSERT INTO nima.identity_review_events
        (event_id, observation_id, projection_version, role, ordinal, subject_revision,
         candidate_import_id, registry_number, operation, entity_id,
         request_sha256, request_payload, report_sha256, rationale, issues, policy_version)
        VALUES (%s,%s,%s,'buyer',0,%s,%s,%s,%s,%s,repeat('a',64),%s,
                repeat('b',64),' Έλεγχος ',ARRAY[]::text[],'reviewed-identity-v1')""",
        (
            request,
            observation,
            PROJECTION_VERSION,
            revision,
            selected,
            number,
            operation,
            entity,
            Jsonb({"synthetic": True}),
        ),
    )
    return request


def test_upgrade_of_populated_v6_preserves_source_and_workflow_rows(pg_dsn: str) -> None:
    # Install the original six bodies, not the current migrate() implementation.
    with psycopg.connect(pg_dsn, autocommit=True) as connection:
        connection.execute(
            "CREATE SCHEMA nima; CREATE TABLE nima.schema_migrations "
            "(version integer PRIMARY KEY, sha256 text NOT NULL)"
        )
        for version, digest in enumerate(OLD_HASHES, 1):
            body = files("nima.storage").joinpath(f"migrations/{version:04d}.sql").read_text()
            assert hashlib.sha256(body.encode()).hexdigest() == digest
            connection.execute(body)
            connection.execute(
                "INSERT INTO nima.schema_migrations VALUES (%s,%s)", (version, digest)
            )
        connection.execute("INSERT INTO nima.raw_objects VALUES (repeat('c',64),123)")
        request = uuid4()
        connection.execute(
            "INSERT INTO nima.workflow_requests "
            "(request_id,parameters,parameters_sha256) VALUES (%s,'{}',repeat('d',64))",
            (request,),
        )
        before = connection.execute("SELECT to_jsonb(w) FROM nima.workflow_requests w").fetchall()
    migrate(pg_dsn)
    migrate(pg_dsn)
    check_schema(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT * FROM nima.raw_objects").fetchall() == [("c" * 64, 123)]
        assert (
            connection.execute("SELECT to_jsonb(w) FROM nima.workflow_requests w").fetchall()
            == before
        )
        assert connection.execute(
            "SELECT count(*) FROM nima.identity_review_events"
        ).fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM nima.identity_entities").fetchone() == (0,)


def test_acceptance_entity_and_head_commit_together_with_exact_anchor(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    entity, request = uuid4(), uuid4()
    with psycopg.connect(pg_dsn) as connection:
        observation = head(connection, run)
        # Both references are deferred, so either insertion order can be atomic.
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) "
            "VALUES (%s,%s,'1',%s)",
            (entity, selected, request),
        )
        event(connection, observation, selected, request=request, entity=entity, operation="accept")
        connection.execute(
            "UPDATE nima.identity_review_heads SET revision=1,latest_event_id=%s", (request,)
        )
    with psycopg.connect(pg_dsn) as connection:
        row = connection.execute(
            "SELECT kind,registry_number FROM nima.identity_entities"
        ).fetchone()
        assert row == ("unclassified", "1")
        row = connection.execute(
            "SELECT database_principal=session_user,recorded_at IS NOT NULL,"
            "rationale FROM nima.identity_review_events"
        ).fetchone()
        assert row == (True, True, " Έλεγχος ")
        assert connection.execute(
            "SELECT revision,latest_event_id FROM nima.identity_review_heads"
        ).fetchone() == (1, request)


@pytest.mark.parametrize("table", ["identity_entities", "identity_review_events"])
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
def test_entity_and_event_history_cannot_be_rewritten(
    pg_dsn: str, tmp_path: Path, table: str, action: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        observation = head(connection, run)
        request, entity = uuid4(), uuid4()
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) "
            "VALUES (%s,%s,'1',%s)",
            (entity, selected, request),
        )
        event(connection, observation, selected, request=request, entity=entity, operation="accept")
    with (
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
        psycopg.connect(pg_dsn) as connection,
    ):
        statement = (
            sql.SQL("DELETE FROM nima.{}")
            if action == "DELETE"
            else sql.SQL("UPDATE nima.{} SET registry_number=registry_number")
        )
        connection.execute(statement.format(sql.Identifier(table)))


@pytest.mark.parametrize("fault", ["run", "source", "normalizer", "hash", "mention", "receipt"])
def test_subject_requires_exact_observation_and_projected_occurrence(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    values: dict[str, object] = {
        "run": run,
        "source": "kimdis:1",
        "normalizer": "kimdis-normalized-v1",
    }
    with psycopg.connect(pg_dsn) as connection:
        row = connection.execute(
            "SELECT observation_id,source_id,content_sha256 FROM nima.observations"
        ).fetchone()
        assert row is not None
        values["source"], values["hash"] = row[1], row[2]
    if fault == "run":
        values[fault] = uuid4()
    elif fault in {"source", "normalizer", "hash"}:
        values[fault] = "e" * 64 if fault == "hash" else "other"
    with pytest.raises(psycopg.IntegrityError), psycopg.connect(pg_dsn) as connection:
        connection.execute(
            """INSERT INTO nima.identity_review_heads
        (observation_id,projection_version,role,ordinal,run_id,source_id,normalizer_version,content_sha256)
        VALUES (%s,%s,'buyer',%s,%s,%s,%s,%s)""",
            (
                row[0],
                "unsupported" if fault == "receipt" else PROJECTION_VERSION,
                1 if fault == "mention" else 0,
                values["run"],
                values["source"],
                values["normalizer"],
                values["hash"],
            ),
        )


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_revision",
        "duplicate_request",
        "accept_without_entity",
        "reject_with_entity",
        "revoke_without_reference",
        "not_found",
        "blank_rationale",
        "oversize_rationale",
        "bad_digest",
    ],
)
def test_invalid_event_does_not_leave_a_partial_transaction(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        observation = head(connection, run)
        original = event(connection, observation, selected)
    with pytest.raises(psycopg.IntegrityError), psycopg.connect(pg_dsn) as connection:
        if fault.startswith("duplicate"):
            event(
                connection,
                observation,
                selected,
                request=original if fault == "duplicate_request" else None,
                revision=2 if fault == "duplicate_request" else 1,
            )
        else:
            operation = (
                "accept"
                if fault == "accept_without_entity"
                else "revoke"
                if fault == "revoke_without_reference"
                else "reject"
            )
            request = event(
                connection,
                observation,
                selected,
                revision=2,
                operation=operation,
                entity=uuid4() if fault == "reject_with_entity" else None,
                number="2" if fault == "not_found" else "1",
            )
            # These cases need invalid values on insertion (history itself is immutable).
            if fault in {"blank_rationale", "oversize_rationale", "bad_digest"}:
                connection.rollback()
                with connection.transaction():
                    connection.execute(
                        """INSERT INTO nima.identity_review_events
                    (event_id,observation_id,projection_version,role,ordinal,subject_revision,
                     candidate_import_id,registry_number,operation,request_sha256,request_payload,
                     report_sha256,rationale,issues,policy_version)
                    VALUES (%s,%s,%s,'buyer',0,2,%s,'1','reject',%s,'{}',repeat('b',64),%s,
                            ARRAY[]::text[],'reviewed-identity-v1')""",
                        (
                            request,
                            observation,
                            PROJECTION_VERSION,
                            selected,
                            "bad" if fault == "bad_digest" else "a" * 64,
                            " " if fault == "blank_rationale" else "λ" * 2049,
                        ),
                    )
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT count(*) FROM nima.identity_review_events"
        ).fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM nima.identity_entities").fetchone() == (0,)


@pytest.mark.parametrize("number", ["1", "2"])
def test_orphan_or_not_found_entity_cannot_commit(pg_dsn: str, tmp_path: Path, number: str) -> None:
    seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with pytest.raises(psycopg.IntegrityError), psycopg.connect(pg_dsn) as connection:
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) "
            "VALUES (%s,%s,%s,%s)",
            (uuid4(), selected, number, uuid4()),
        )


def test_new_relations_grant_no_public_or_existing_role_access(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        rows = connection.execute("""SELECT c.relname, a.grantee
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
        WHERE n.nspname='nima' AND c.relname IN
            ('identity_review_heads','identity_review_events','identity_entities')
        AND a.grantee<>c.relowner""").fetchall()
        assert rows == []


@pytest.mark.parametrize("fault", ["identity", "jump", "wrong_event", "delete"])
def test_head_cannot_change_subject_skip_revisions_or_reference_another_revision(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        observation = head(connection, run)
        request = event(connection, observation, selected)
    statement = {
        "identity": "UPDATE nima.identity_review_heads "
        "SET source_id='other',revision=1,latest_event_id=%s",
        "jump": "UPDATE nima.identity_review_heads SET revision=2,latest_event_id=%s",
        "wrong_event": "UPDATE nima.identity_review_heads SET revision=1,latest_event_id=%s",
        "delete": "DELETE FROM nima.identity_review_heads "
        "WHERE latest_event_id IS DISTINCT FROM %s",
    }[fault]
    with pytest.raises(psycopg.Error), psycopg.connect(pg_dsn) as connection:
        connection.execute(statement, (uuid4() if fault == "wrong_event" else request,))
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute(
            "SELECT revision,latest_event_id FROM nima.identity_review_heads"
        ).fetchone() == (0, None)


def test_exact_anchor_cannot_initialize_two_entity_handles(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        observation = head(connection, run)
        request, entity = uuid4(), uuid4()
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) "
            "VALUES (%s,%s,'1',%s)",
            (entity, selected, request),
        )
        event(connection, observation, selected, request=request, entity=entity, operation="accept")
    with pytest.raises(psycopg.errors.UniqueViolation), psycopg.connect(pg_dsn) as connection:
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) "
            "VALUES (%s,%s,'1',%s)",
            (uuid4(), selected, uuid4()),
        )


def test_reversal_reference_binds_the_same_candidate_and_prior_decision(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    other = registry_import(pg_dsn, tmp_path / "other")
    with psycopg.connect(pg_dsn) as connection:
        observation = head(connection, run)
        original = event(connection, observation, selected)
    for imported, reversed_operation in ((other, "reject"), (selected, "accept")):
        with (
            pytest.raises(psycopg.errors.ForeignKeyViolation),
            psycopg.connect(pg_dsn) as connection,
        ):
            connection.execute(
                """INSERT INTO nima.identity_review_events
            (event_id,observation_id,projection_version,role,ordinal,subject_revision,
             candidate_import_id,registry_number,operation,reverses_event_id,reversed_operation,
             request_sha256,request_payload,rationale,issues,policy_version)
            VALUES (%s,%s,%s,'buyer',0,2,%s,'1','revoke',%s,%s,
                    repeat('a',64),'{}','Έλεγχος',ARRAY[]::text[],'reviewed-identity-v1')""",
                (uuid4(), observation, PROJECTION_VERSION, imported, original, reversed_operation),
            )
    with psycopg.connect(pg_dsn) as connection:
        reversal = uuid4()
        connection.execute(
            """INSERT INTO nima.identity_review_events
        (event_id,observation_id,projection_version,role,ordinal,subject_revision,
         candidate_import_id,registry_number,operation,reverses_event_id,reversed_operation,
         request_sha256,request_payload,rationale,issues,policy_version)
        VALUES (%s,%s,%s,'buyer',0,2,%s,'1','revoke',%s,'reject',
                repeat('a',64),'{}','Έλεγχος',ARRAY[]::text[],'reviewed-identity-v1')""",
            (reversal, observation, PROJECTION_VERSION, selected, original),
        )
        assert connection.execute(
            "SELECT count(*) FROM nima.identity_review_events"
        ).fetchone() == (2,)
