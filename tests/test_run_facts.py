"""The completeness rule: a run is a complete capture only if its stored counters all agree."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from nima.analytics.run_facts import (
    StoredRun,
    collection_complete,
    facts,
    normalization_complete,
    query_sha256,
)

WHEN = datetime(2026, 1, 1, tzinfo=UTC)
QUERY = {"dateFrom": "2026-01-01", "dateTo": "2026-01-01"}


def run(**changes: object) -> StoredRun:
    base = StoredRun(
        uuid4(),
        QUERY,
        "complete",
        True,
        3,
        120,
        3,
        50,
        ((0, 50), (1, 50), (2, 20)),
        120,
        0,
        WHEN,
        WHEN,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def test_a_finished_managed_run_with_every_page_is_complete() -> None:
    assert collection_complete(run())
    assert normalization_complete(run())
    fact = facts(run())
    assert fact.collection_complete and fact.normalization_complete and fact.quarantined == 0


def test_an_empty_result_is_one_stored_page_with_no_records() -> None:
    empty = run(total_records=0, total_pages=0, next_page=1, pages=((0, 0),), observations=0)
    assert collection_complete(empty) and normalization_complete(empty)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "running"},
        {"status": "failed"},
        {"managed": False},
        {"total_records": None},
        {"total_pages": None},
        {"page_size": None},
        {"total_pages": 4},
        {"next_page": 2},
        {"next_page": 4},
        {"pages": ((0, 50), (1, 50))},
        {"pages": ((0, 50), (2, 50), (3, 20))},
        {"pages": ((0, 50), (1, 49), (2, 20))},
        {"pages": ((0, 50), (1, 50), (2, 21))},
        {"pages": ((0, 50), (1, 50), (2, 20), (3, 0))},
        {"pages": ()},
    ],
)
def test_each_disagreeing_counter_makes_the_collection_incomplete(
    changes: dict[str, object],
) -> None:
    assert not collection_complete(run(**changes))
    assert not facts(run(**changes)).collection_complete


def test_a_page_that_is_exactly_full_leaves_no_partial_page() -> None:
    exact = run(total_records=100, total_pages=2, next_page=2, pages=((0, 50), (1, 50)))
    assert collection_complete(exact)
    assert not collection_complete(replace(exact, pages=((0, 50), (1, 50), (2, 0))))


def test_normalization_counts_every_record_as_normalized_or_quarantined() -> None:
    assert normalization_complete(run(observations=119, quarantined=1))
    assert not normalization_complete(run(observations=119))
    assert not normalization_complete(run(observations=121))
    assert not normalization_complete(run(total_records=None))
    fact = facts(run(observations=119, quarantined=1))
    assert fact.normalization_complete and fact.quarantined == 1


def test_the_query_hash_is_canonical_and_distinguishes_queries() -> None:
    assert query_sha256({"b": 1, "a": 2}) == query_sha256({"a": 2, "b": 1})
    assert query_sha256(QUERY) != query_sha256({**QUERY, "dateTo": "2026-01-02"})
    assert facts(run()).query_sha256 == query_sha256(QUERY)
