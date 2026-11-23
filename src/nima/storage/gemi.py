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

from nima.ingestion.gemi import SearchRules
from nima.sources.gemi import NORMALIZER_VERSION
from nima.storage.gemi_archive import (
    CONTRACT,
    SEARCH_CONTRACT,
    ImportFailure,
    VerifiedRun,
    VerifiedSearch,
    verify_run,
    verify_search_run,
)
from nima.storage.postgres import Connection, MigrationError, _connect, check_schema

IMPORT_VERSION = "gemi-import-v1"
SEARCH_IMPORT_VERSION = "gemi-search-import-v1"


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


@dataclass(frozen=True)
class SearchImportSummary:
    run_id: str
    manifest_sha256: str
    afms: int
    requests: int
    hits: int
    unconfirmed_quarantines: int
    reused: bool
    status: str = "imported"
    import_version: str = SEARCH_IMPORT_VERSION


def _search_rows(
    run: VerifiedSearch,
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]], list[tuple[object, ...]]]:
    """The expected requests, outcomes and hits of a verified search run, in stored order."""
    answers = sorted(run.answers, key=lambda a: a.afm)
    requests = [astuple(r) for r in sorted(run.requests, key=lambda r: (r.number, r.attempt))]
    outcomes: list[tuple[object, ...]] = [
        (
            a.afm,
            a.attempt,
            a.outcome,
            a.status,
            a.sha256,
            a.observed_at,
            a.truncated,
            a.unconfirmed,
            len(a.hits),
        )
        for a in answers
    ]
    hits: list[tuple[object, ...]] = [
        (
            a.afm,
            h.index,
            h.registry_number,
            h.afm_matches,
            a.sha256,
            f"gemi:{h.registry_number}",
            NORMALIZER_VERSION,
        )
        for a in answers
        for h in a.hits
    ]
    return requests, outcomes, hits


def _search_metadata(connection: Connection, run: VerifiedSearch, *, reused: bool) -> None:
    bodies = {r.sha256: r.byte_length for r in run.requests if r.sha256 is not None}
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
    for answer in sorted(run.answers, key=lambda a: a.afm):
        for hit in answer.hits:
            key = (f"gemi:{hit.registry_number}", NORMALIZER_VERSION, answer.sha256)
            payload = Jsonb(json.loads(hit.payload))
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


_STORED = (
    (
        "SELECT afm, attempt, started_at, finished_at, status, failure, raw_sha256, "
        "byte_length, observed_at FROM nima.gemi_search_requests WHERE run_id=%s "
        "ORDER BY afm, attempt"
    ),
    (
        "SELECT afm, attempt, outcome, status, raw_sha256, observed_at, truncated, "
        "unconfirmed_quarantine, hit_count FROM nima.gemi_search_outcomes "
        "WHERE run_id=%s ORDER BY afm"
    ),
    (
        "SELECT afm, hit_index, registry_number, afm_matches, raw_sha256, source_id, "
        "normalizer_version FROM nima.gemi_search_hits WHERE run_id=%s ORDER BY afm, hit_index"
    ),
)


def _commit_search(connection: Connection, run: VerifiedSearch) -> SearchImportSummary:
    lock = int.from_bytes(
        hashlib.sha256(b"nima.gemi.search.import:" + run.run_id.bytes).digest()[:8],
        "big",
        signed=True,
    )
    connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
    rows = _search_rows(run)
    hit_count = len(rows[2])
    expected = (
        SEARCH_IMPORT_VERSION,
        run.archive_root,
        run.manifest,
        run.manifest_sha256,
        SEARCH_CONTRACT["connector_version"],
        NORMALIZER_VERSION,
        CONTRACT["source"],
        CONTRACT["license"],
        CONTRACT["publisher"],
        len(run.outcomes),
        len(run.requests),
        hit_count,
        run.unconfirmed_quarantines,
    )
    previous = connection.execute(
        "SELECT import_version, archive_root, manifest, manifest_sha256, connector_version, "
        "normalizer_version, source_url, license, publisher, afm_count, request_count, "
        "hit_count, unconfirmed_quarantine_count FROM nima.gemi_search_imports WHERE run_id=%s",
        (run.run_id,),
    ).fetchone()
    reused = previous is not None
    if reused:
        _assert_equal(previous, expected)
    else:
        connection.execute(
            "INSERT INTO nima.gemi_search_imports (run_id, import_version, archive_root, "
            "manifest, manifest_sha256, connector_version, normalizer_version, source_url, "
            "license, publisher, afm_count, request_count, hit_count, "
            "unconfirmed_quarantine_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (run.run_id, *expected),
        )
    _search_metadata(connection, run, reused=reused)
    if reused:
        for query, stored in zip(_STORED, rows, strict=True):
            _assert_equal(connection.execute(query, (run.run_id,)).fetchall(), stored)
    else:
        with connection.cursor() as cursor:
            for statement, stored in zip(
                (
                    "INSERT INTO nima.gemi_search_requests VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    "INSERT INTO nima.gemi_search_outcomes VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    "INSERT INTO nima.gemi_search_hits VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                ),
                rows,
                strict=True,
            ):
                cursor.executemany(statement, [(run.run_id, *row) for row in stored])
    return SearchImportSummary(
        run.run_id.hex,
        run.manifest_sha256,
        len(run.outcomes),
        len(run.requests),
        hit_count,
        run.unconfirmed_quarantines,
        reused,
    )


def import_search_run(
    dsn: str, archive_root: Path, run_id: UUID, rules: SearchRules
) -> SearchImportSummary:
    """Reverify the search archive on every invocation, then commit or verify reuse."""
    run = verify_search_run(archive_root, run_id, rules)
    try:
        check_schema(dsn)
        with _connect(dsn) as connection, connection.transaction():
            result = _commit_search(connection, run)
        return result
    except MigrationError:
        raise ImportFailure("database_schema") from None
    except psycopg.Error:
        raise ImportFailure("database") from None
