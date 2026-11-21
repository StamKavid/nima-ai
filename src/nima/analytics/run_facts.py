"""Decide from stored counters whether a run is a complete capture; read-only, no archive access.

The rule is the one written in ``docs/semantics/observed-change.md``. A run's collection is complete
only if it ended ``complete`` under a managed lease, its page count and page sizes agree with the
totals the source reported, and every page it should hold is stored with the record count it
should have. Its normalization is complete only if every reported record is accounted for as
either a normalized observation or a quarantined record. Quarantined records are counted and make
the metric abstain, so a capture is never called complete while records are missing from it.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from nima.analytics.snapshot import SnapshotError
from nima.semantics.observed_change import RunFacts
from nima.storage.connection import Connection

_FACTS = """SELECT r.run_id, r.query, r.status, r.owner IS NOT NULL AND r.settings IS NOT NULL,
    r.next_page, r.total_records, r.total_pages, r.page_size,
    coalesce((SELECT jsonb_agg(jsonb_build_array(p.page_number, p.record_count)
        ORDER BY p.page_number) FROM nima.run_pages p WHERE p.run_id = r.run_id), '[]'),
    (SELECT count(*) FROM nima.observations o WHERE o.run_id = r.run_id),
    (SELECT count(*) FROM nima.quarantine q WHERE q.run_id = r.run_id),
    coalesce((SELECT min(p.observed_at) FROM nima.run_pages p WHERE p.run_id = r.run_id),
        r.created_at),
    coalesce((SELECT max(p.observed_at) FROM nima.run_pages p WHERE p.run_id = r.run_id),
        r.created_at)
    FROM nima.ingest_runs r WHERE r.run_id = ANY(%s) ORDER BY r.run_id"""


@dataclass(frozen=True)
class StoredRun:
    run_id: UUID
    query: object
    status: str
    managed: bool
    next_page: int
    total_records: int | None
    total_pages: int | None
    page_size: int | None
    pages: tuple[tuple[int, int], ...]
    observations: int
    quarantined: int
    observed_from: datetime
    observed_to: datetime


def collection_complete(run: StoredRun) -> bool:
    total, size, count = run.total_records, run.page_size, run.total_pages
    if (
        run.status != "complete"
        or not run.managed
        or total is None
        or size is None
        or count is None
        or count != (total + size - 1) // size
        or run.next_page != max(1, count)
    ):
        return False
    stored = [number for number, _ in run.pages]
    expected = [min(size, max(0, total - number * size)) for number in range(max(1, count))]
    return stored == list(range(max(1, count))) and [n for _, n in run.pages] == expected


def normalization_complete(run: StoredRun) -> bool:
    return run.total_records is not None and run.observations + run.quarantined == run.total_records


def query_sha256(query: object) -> str:
    body = json.dumps(query, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode()).hexdigest()


def facts(run: StoredRun) -> RunFacts:
    return RunFacts(
        str(run.run_id),
        query_sha256(run.query),
        collection_complete(run),
        normalization_complete(run),
        run.quarantined,
        run.observed_from,
        run.observed_to,
    )


def read_run_facts(connection: Connection, run_ids: tuple[UUID, ...]) -> dict[UUID, RunFacts]:
    """Counters of the selected runs on the caller's SELECT-only snapshot."""
    rows = connection.execute(_FACTS, (list(run_ids),)).fetchall()
    if len(rows) != len(run_ids):
        raise SnapshotError("analytics_coverage")
    result: dict[UUID, RunFacts] = {}
    for row in rows:
        stored = StoredRun(
            cast(UUID, row[0]),
            row[1],
            cast(str, row[2]),
            cast(bool, row[3]),
            cast(int, row[4]),
            cast(int | None, row[5]),
            cast(int | None, row[6]),
            cast(int | None, row[7]),
            tuple((int(page[0]), int(page[1])) for page in cast(list[list[int]], row[8])),
            cast(int, row[9]),
            cast(int, row[10]),
            cast(datetime, row[11]).astimezone(UTC),
            cast(datetime, row[12]).astimezone(UTC),
        )
        result[stored.run_id] = facts(stored)
    return result
