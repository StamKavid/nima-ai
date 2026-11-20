"""The two invented sources parse their own shapes exactly; they share nothing with KIMDIS."""

import json

import pytest

from nima.sources.base import SourcePageError
from tests.synthetic_sources import (
    EventsAdapter,
    LedgerAdapter,
    event,
    events_page,
    ledger_page,
)

ledger = LedgerAdapter()
events = EventsAdapter()


def test_ledger_money_uses_a_decimal_comma_and_stays_exact() -> None:
    page = ledger.normalize_page(
        ledger_page(
            0,
            1,
            4,
            [
                ("L-0001", "1.234,56", "a"),
                ("L-0002", "0,05", "b"),
                ("L-0003", "-12,00", "c"),
                ("L-0004", "123.456.789.012.345.678,90", "d"),
            ],
        )
    )
    assert [r.normalized["amount"] for r in page.records] == [
        "1234.56",
        "0.05",
        "-12.00",
        "123456789012345678.90",
    ]


@pytest.mark.parametrize("amount", ["1234.56", "1,5", "1.23,45", "1,234,56", "abc", "", "1e3,00"])
def test_ledger_rejects_amounts_that_are_not_comma_decimals(amount: str) -> None:
    page = ledger.normalize_page(ledger_page(0, 1, 1, [("L-0001", amount, "x")]))
    assert page.records == ()
    assert [(i.index, i.reason) for i in page.issues] == [(0, "bad_amount")]
    assert page.source_ids == ("ledger:L-0001",)


def test_ledger_evidence_is_the_physical_line_not_a_json_pointer() -> None:
    raw = ledger_page(
        0, 1, 3, [("L-0001", "1,00", "a"), ("L-0002", "x", "b"), ("L-0003", "3,00", "c")]
    )
    page = ledger.normalize_page(raw)
    assert [r.evidence_pointer for r in page.records] == ["line:3", "line:5"]
    assert [i.evidence_pointer for i in page.issues] == ["line:4"]
    assert raw.decode().split("\n")[3 - 1].startswith("L-0001;")


def test_ledger_a_bad_identifier_is_quarantined_and_left_unidentified() -> None:
    page = ledger.normalize_page(
        ledger_page(0, 1, 2, [("bad id", "1,00", "a"), ("L-0002", "2,00", "b")])
    )
    assert [(i.index, i.reason) for i in page.issues] == [(0, "bad_id")]
    assert page.source_ids == ("ledger:L-0002",)
    assert page.record_count == 2 and len(page.record_hashes) == 2


def test_ledger_a_short_row_is_quarantined() -> None:
    raw = b"#ledger page=0 pages=1 total=1\nid;date;amount;memo\nL-0001;2026-11-06\n"
    page = ledger.normalize_page(raw)
    assert [(i.reason, i.evidence_pointer) for i in page.issues] == [("bad_row", "line:3")]


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff\xfe",
        b"#ledger page=0 pages=1\nid;date;amount;memo\n",
        b"#ledger page=0 pages=1 total=0\nid;amount\n",
        b"#ledger page=2 pages=2 total=0\nid;date;amount;memo\n",
        b"#ledger page=0 pages=0 total=0\nid;date;amount;memo\n",
        b'{"content": []}',
    ],
)
def test_ledger_a_broken_envelope_is_a_source_page_error(raw: bytes) -> None:
    with pytest.raises(SourcePageError):
        ledger.normalize_page(raw)


def test_ledger_pagination_comes_from_the_header() -> None:
    page = ledger.normalize_page(ledger_page(1, 3, 9, [("L-0004", "1,00", "a")]))
    assert (page.number, page.total_pages, page.total_records, page.last) == (1, 3, 9, False)
    assert ledger.normalize_page(ledger_page(2, 3, 9, [("L-0009", "1,00", "a")])).last is True


def test_events_money_is_minor_units_scaled_by_the_currency() -> None:
    items = [
        event("acme", 1, 12345),
        event("acme", 2, 5),
        event("acme", 3, 500, "JPY"),
        event("acme", 4, 1234, "KWD"),
        event("acme", 5, 12345678901234567890),
        event("acme", 6, -250),
    ]
    page = events.normalize_page(events_page(0, 1, 6, items))
    assert [(r.normalized["amount"], r.normalized["currency"]) for r in page.records] == [
        ("123.45", "EUR"),
        ("0.05", "EUR"),
        ("500", "JPY"),
        ("1.234", "KWD"),
        ("123456789012345678.90", "EUR"),
        ("-2.50", "EUR"),
    ]


def test_events_identifiers_are_composite_and_evidence_is_a_json_pointer() -> None:
    page = events.normalize_page(
        events_page(0, 1, 2, [event("acme", 7, 100), event("beta-1", 8, 200)])
    )
    assert [r.source_id for r in page.records] == ["events:acme/7", "events:beta-1/8"]
    assert [r.evidence_pointer for r in page.records] == ["/data/0", "/data/1"]


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (event("acme", 1, 100, "XXX"), "unknown_currency"),
        (event("acme", 1, "100"), "bad_minor"),
        (event("acme", 1, 1.5), "bad_minor"),
        (event("acme", 1, True), "bad_minor"),
        ({"key": {"ns": "acme", "n": 1}, "value": "free text"}, "bad_value"),
    ],
)
def test_events_a_bad_value_is_quarantined_but_the_record_stays_identified(
    item: dict[str, object], reason: str
) -> None:
    page = events.normalize_page(events_page(0, 1, 1, [item]))
    assert page.records == ()
    assert [(i.index, i.reason) for i in page.issues] == [(0, reason)]
    assert page.source_ids == ("events:acme/1",)


@pytest.mark.parametrize(
    "key",
    [None, "acme/1", {"ns": "ACME", "n": 1}, {"ns": "acme", "n": -1}, {"ns": "acme", "n": "1"}],
)
def test_events_a_bad_key_is_quarantined_and_unidentified(key: object) -> None:
    page = events.normalize_page(
        events_page(0, 1, 1, [{"key": key, "value": {"minor": 1, "ccy": "EUR"}}])
    )
    assert [i.reason for i in page.issues] == ["bad_key"]
    assert page.source_ids == ()


def test_events_pagination_follows_the_cursor_and_the_last_page_has_none() -> None:
    first = events.normalize_page(events_page(0, 2, 2, [event("a", 1, 1)]))
    second = events.normalize_page(events_page(1, 2, 2, [event("a", 2, 1)]))
    assert (first.number, first.last, second.number, second.last) == (0, False, 1, True)
    assert json.loads(events_page(0, 2, 2, []))["meta"]["next"] == "c1"
    assert json.loads(events_page(1, 2, 2, []))["meta"]["next"] is None


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b"[]",
        b'{"meta": {}, "data": []}',
        events_page(0, 2, 2, [], final=True),
        events_page(1, 2, 2, [], final=False),
        events_page(2, 2, 2, []),
        events_page(0, 0, 0, []),
        b'{"meta": {"seq": 0, "pages": 1, "total": 0, "next": null}, "data": {}}',
    ],
)
def test_events_a_broken_envelope_is_a_source_page_error(raw: bytes) -> None:
    with pytest.raises(SourcePageError):
        events.normalize_page(raw)


def test_the_two_sources_have_distinct_identities_and_namespaces() -> None:
    assert ledger.name != events.name
    assert ledger.connector_version != events.connector_version
    assert ledger.normalizer_version != events.normalizer_version
    left = ledger.normalize_page(ledger_page(0, 1, 1, [("L-0001", "1,00", "a")]))
    right = events.normalize_page(events_page(0, 1, 1, [event("ledger", 1, 100)]))
    assert not set(left.source_ids) & set(right.source_ids)
