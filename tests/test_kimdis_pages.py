"""Pagination and record-level quarantine are independent source boundaries."""

import json
from decimal import Decimal

import pytest

from nima.sources.kimdis import InvalidRecord, normalize_page


def page_body(*records: object, **metadata: object) -> bytes:
    page: dict[str, object] = {
        "content": list(records),
        "number": 0,
        "size": 50,
        "totalElements": len(records),
        "totalPages": int(bool(records)),
        "last": True,
    }
    page.update(metadata)
    return json.dumps(page, ensure_ascii=False).encode()


def record(reference: str = "26SYMV000000001") -> dict[str, object]:
    return {"referenceNumber": reference, "title": "ΔΟΚΙΜΑΣΤΙΚΗ", "totalCostWithoutVAT": "0.10"}


def test_normalizes_a_page_and_quarantines_bad_rows_in_place() -> None:
    page = normalize_page(page_body(record(), {**record("26SYMV000000002"), "title": 12}))
    assert page.record_count == 2
    assert page.contracts[0].net_amount == Decimal("0.10")
    assert page.contracts[0].evidence.json_pointer == "/content/0"
    assert page.issues[0].evidence.json_pointer == "/content/1"
    assert "title" in page.issues[0].reason
    assert len(page.source_ids) == 2


def test_empty_results_are_a_valid_single_response() -> None:
    page = normalize_page(page_body())
    assert page.total_pages == 0
    assert page.total_records == 0
    assert page.last and page.contracts == () and page.issues == ()


def test_source_fingerprint_tracks_full_records_independently_of_neighbors() -> None:
    original = normalize_page(page_body(record(), record("neighbor")))
    changed_neighbor = normalize_page(page_body(record(), {**record("neighbor"), "title": "new"}))
    changed_unprojected_field = normalize_page(page_body({**record(), "extra": "changed"}))
    reordered = normalize_page(page_body(dict(reversed(list(record().items())))))
    assert (
        original.record_hashes[0] == changed_neighbor.record_hashes[0] == reordered.record_hashes[0]
    )
    assert original.record_hashes[1] != changed_neighbor.record_hashes[1]
    assert original.record_hashes[0] != changed_unprojected_field.record_hashes[0]


def test_source_fingerprint_distinguishes_exact_numbers_and_strings() -> None:
    def digest(value: str) -> str:
        raw = page_body(record()).replace(b'"0.10"', value.encode())
        return normalize_page(raw).record_hashes[0]

    assert len({digest('"0.10"'), digest("0.10"), digest("0.100000000000000001")}) == 3


def test_nested_source_types_are_fingerprinted_without_tag_collisions() -> None:
    nested = {"extra": {"values": [None, True, 1], "empty": []}}
    first = normalize_page(page_body({**record(), **nested}))
    changed = normalize_page(page_body({**record(), "extra": ["object", nested["extra"]]}))
    assert first.record_hashes != changed.record_hashes


def test_excessive_canonical_depth_is_a_structured_source_failure() -> None:
    nested = b"[" * 700 + b"0" + b"]" * 700
    raw = page_body(record()).replace(b'"0.10"', b'"0.10", "extra":' + nested)
    with pytest.raises(InvalidRecord):
        normalize_page(raw)


def test_non_object_rows_and_missing_ids_remain_quarantined() -> None:
    page = normalize_page(page_body(42, {"title": "Missing ID"}, record()))
    assert len(page.issues) == 2
    assert page.contracts[0].evidence.json_pointer == "/content/2"
    assert page.source_ids == ("kimdis:26SYMV000000001",)


@pytest.mark.parametrize(
    "metadata",
    [
        {"number": True},
        {"number": -1},
        {"size": 0},
        {"size": "50"},
        {"totalElements": -1},
        {"totalElements": True},
        {"totalPages": 2},
        {"last": "true"},
        {"last": False},
        {"numberOfElements": 2},
        {"totalElements": 2},
        {"number": 1},
    ],
)
def test_rejects_inconsistent_or_invalid_pagination(metadata: dict[str, object]) -> None:
    with pytest.raises(InvalidRecord):
        normalize_page(page_body(record(), **metadata))
