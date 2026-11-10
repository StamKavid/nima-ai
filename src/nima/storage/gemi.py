"""One atomic offline registry import; no procurement outbox or identity writes.

Transactions: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
Locks: https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS
"""

import hashlib
import json
from dataclasses import astuple, dataclass
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from nima.sources.gemi import NORMALIZER_VERSION
from nima.storage.gemi_archive import CONTRACT, ImportFailure, VerifiedRun, verify_run
from nima.storage.postgres import Connection, MigrationError, _connect, check_schema

IMPORT_VERSION = "gemi-import-v1"


@dataclass(frozen=True)
class ImportSummary:
    run_id: str
    manifest_sha256: str
    profiles: int
    not_found: int
    responses: int
    reused: bool
    status: str = "imported"
    import_version: str = IMPORT_VERSION


def _assert_equal(actual: object, expected: object) -> None:
    if actual != expected:
        raise ImportFailure("import_conflict")


def _metadata(connection: Connection, run: VerifiedRun, *, reused: bool) -> None:
    bodies = {r.sha256: r.byte_length for r in run.responses if r.sha256 is not None}
    for digest, length in sorted(bodies.items()):
        if not reused:
            connection.execute(
                "INSERT INTO nima.raw_objects VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (digest, length),
            )
        _assert_equal(
            connection.execute(
                "SELECT byte_length FROM nima.raw_objects WHERE sha256=%s", (digest,)
            ).fetchone(),
            (length,),
        )
    for observation in sorted(run.observations, key=lambda o: o.number):
        if observation.profile is None:
            continue
        key = (f"gemi:{observation.number}", NORMALIZER_VERSION, observation.sha256)
        payload = Jsonb(json.loads(observation.profile))
        if not reused:
            connection.execute(
                "INSERT INTO nima.gemi_profile_versions VALUES (%s, %s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (*key, payload),
            )
        _assert_equal(
            connection.execute(
                "SELECT normalized=%s FROM nima.gemi_profile_versions "
                "WHERE source_id=%s AND normalizer_version=%s AND raw_sha256=%s",
                (payload, *key),
            ).fetchone(),
            (True,),
        )


def _observations(run: VerifiedRun) -> list[tuple[object, ...]]:
    return [
        (
            o.number,
            o.attempt,
            o.outcome,
            200 if o.profile is not None else 404,
            o.sha256,
            o.observed_at,
            f"gemi:{o.number}" if o.profile is not None else None,
            NORMALIZER_VERSION if o.profile is not None else None,
        )
        for o in sorted(run.observations, key=lambda o: o.number)
    ]


def _commit(connection: Connection, run: VerifiedRun) -> ImportSummary:
    # A transaction-scoped lock also serializes first imports without a parent row.
    lock = int.from_bytes(
        hashlib.sha256(b"nima.gemi.import:" + run.run_id.bytes).digest()[:8], "big", signed=True
    )
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
    profiles = sum(o.profile is not None for o in run.observations)
    expected = (
        IMPORT_VERSION,
        run.archive_root,
        run.manifest,
        run.manifest_sha256,
        NORMALIZER_VERSION,
        CONTRACT["source"],
        CONTRACT["license"],
        CONTRACT["publisher"],
        profiles,
        len(run.observations) - profiles,
        len(run.responses),
    )
    previous = connection.execute(
        "SELECT import_version, archive_root, manifest, manifest_sha256, normalizer_version, "
        "source_url, license, publisher, profile_count, not_found_count, response_count "
        "FROM nima.gemi_imports WHERE run_id=%s",
        (run.run_id,),
    ).fetchone()
    reused = previous is not None
    if reused:
        _assert_equal(previous, expected)
    else:
        connection.execute(
            "INSERT INTO nima.gemi_imports (run_id, import_version, archive_root, manifest, "
            "manifest_sha256, normalizer_version, source_url, license, publisher, "
            "profile_count, not_found_count, response_count) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (run.run_id, *expected),
        )
    _metadata(connection, run, reused=reused)
    responses = [astuple(r) for r in sorted(run.responses, key=lambda r: (r.number, r.attempt))]
    observations = _observations(run)
    if reused:
        _assert_equal(
            connection.execute(
                "SELECT registry_number, attempt, started_at, finished_at, status, failure, "
                "raw_sha256, byte_length, observed_at FROM nima.gemi_responses WHERE run_id=%s "
                "ORDER BY registry_number, attempt",
                (run.run_id,),
            ).fetchall(),
            responses,
        )
        _assert_equal(
            connection.execute(
                "SELECT registry_number, attempt, outcome, status, raw_sha256, observed_at, "
                "source_id, normalizer_version FROM nima.gemi_observations WHERE run_id=%s "
                "ORDER BY registry_number",
                (run.run_id,),
            ).fetchall(),
            observations,
        )
    else:
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO nima.gemi_responses VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(run.run_id, *row) for row in responses],
            )
            cursor.executemany(
                "INSERT INTO nima.gemi_observations VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(run.run_id, *row) for row in observations],
            )
    return ImportSummary(
        run.run_id.hex,
        run.manifest_sha256,
        profiles,
        len(observations) - profiles,
        len(responses),
        reused,
    )


def import_run(dsn: str, archive_root: Path, run_id: UUID) -> ImportSummary:
    """Reverify all source evidence on every invocation, then commit or verify reuse."""
    run = verify_run(archive_root, run_id)
    try:
        check_schema(dsn)
        with _connect(dsn) as connection, connection.transaction():
            result = _commit(connection, run)
        return result
    except MigrationError:
        raise ImportFailure("database_schema") from None
    except psycopg.Error:
        raise ImportFailure("database") from None
