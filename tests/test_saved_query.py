"""A run's query is saved as plain JSON and rebuilt into its adapter without a KIMDIS ``Query``.

``QueryPayload`` carries a saved payload to code that wants a query-like object. The KIMDIS
adapter rebuilds itself from a saved payload only if the payload is exactly what
``Query.payload()`` writes, so a stored run cannot be resumed against a reshaped query.
"""

from datetime import date

import pytest

from nima.ingestion.config import Query
from nima.sources.base import QueryPayload
from nima.sources.kimdis import KimdisAdapter

SAMPLES = [
    Query(date(2026, 11, 6), date(2026, 11, 6)),
    Query(date(2026, 1, 1), date(2026, 6, 29), ("00123", "7")),
    Query(date(2025, 2, 28), date(2025, 3, 1), ("1",)),
]


def test_a_query_payload_is_an_independent_copy_of_what_it_was_given() -> None:
    organizations = ["1", "2"]
    given: dict[str, object] = {"organizations": organizations, "dateFrom": "2026-01-01"}
    saved = QueryPayload(given)
    organizations.append("added later")
    given["dateFrom"] = "changed"
    returned = saved.payload()
    assert returned == {"organizations": ["1", "2"], "dateFrom": "2026-01-01"}
    nested = returned["organizations"]
    assert isinstance(nested, list)
    nested.append("3")
    assert saved.payload()["organizations"] == ["1", "2"]


@pytest.mark.parametrize("query", SAMPLES)
def test_the_kimdis_adapter_rebuilds_from_exactly_what_a_query_writes(query: Query) -> None:
    adapter = KimdisAdapter.from_payload(query.payload())
    assert adapter.query_payload() == query.payload()
    assert adapter.request_for(2).json == query.payload()
    assert adapter.request_for(2).params == {"page": 2}


def test_the_rebuilt_adapter_does_not_alias_the_saved_payload() -> None:
    saved = SAMPLES[1].payload()
    adapter = KimdisAdapter.from_payload(saved)
    nested = saved["organizations"]
    assert isinstance(nested, list)
    nested.append("999")
    assert adapter.query_payload() == SAMPLES[1].payload()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "Invalid saved text option"),
        ({"dateFrom": "2026-11-06"}, "Invalid saved text option"),
        ({"dateFrom": 20261106, "dateTo": "2026-11-06"}, "Invalid saved text option"),
        ({"dateFrom": "2026-13-01", "dateTo": "2026-11-06"}, "Invalid saved date"),
        ({"dateFrom": "20261106", "dateTo": "2026-11-06"}, "Invalid saved date"),
        (
            {"dateFrom": "2026-11-06", "dateTo": "2026-11-06", "organizations": "00123"},
            "Invalid saved buyer filter",
        ),
        (
            {"dateFrom": "2026-11-06", "dateTo": "2026-11-06", "organizations": [123]},
            "Invalid saved buyer filter",
        ),
        (
            {"dateFrom": "2026-11-06", "dateTo": "2026-11-06", "organizations": []},
            "Saved query is not in canonical form",
        ),
        (
            {"dateFrom": "2026-11-06", "dateTo": "2026-11-06", "extra": 1},
            "Saved query is not in canonical form",
        ),
    ],
)
def test_a_saved_payload_that_is_not_exactly_a_kimdis_query_is_refused(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        KimdisAdapter.from_payload(payload)
