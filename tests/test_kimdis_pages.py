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
