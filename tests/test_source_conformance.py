"""Source adapter conformance: every adapter must satisfy the same parser-level guarantees.

The suite is parametrized over adapter cases. KIMDIS is the first; later slices add more cases
and every one of them must pass every test here without changing the engine.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from nima.sources import base
from nima.sources.base import NormalizedPage, SourceAdapter, SourcePageError
from nima.sources.kimdis import InvalidRecord, KimdisAdapter
from scripts import dependency_graph as dg
from tests.test_collection import QUERY, body
from tests.test_kimdis_pages import page_body
from tests.test_participation import joint_record

SRC = Path(__file__).resolve().parents[1] / "src"


@dataclass(frozen=True)
class AdapterCase:
    name: str
    make: Callable[[], SourceAdapter]
    pages: tuple[bytes, ...]  # valid pages, each with at least one normalizable record
    money_page: bytes  # a valid page whose record carries an exact money value
    quarantine_page: bytes  # a valid envelope with exactly one bad record
    broken_envelope: bytes  # bytes that are not a valid page


KIMDIS = AdapterCase(
    name="kimdis",
    make=lambda: KimdisAdapter(QUERY),
    pages=(body(page=0, total=2), body(page=1, total=2)),
    money_page=page_body(joint_record()),
    quarantine_page=body(total=1, title=42),
    broken_envelope=b'{"content": 1}',
)
CASES = [pytest.param(KIMDIS, id="kimdis")]


def floats_in(value: object) -> list[object]:
    if isinstance(value, float):
        return [value]
    if isinstance(value, dict):
        return [f for v in value.values() for f in floats_in(v)]
    if isinstance(value, (list, tuple)):
        return [f for v in value for f in floats_in(v)]
    return []


@pytest.mark.parametrize("case", CASES)
def test_adapter_identity_is_stable_and_serializable(case: AdapterCase) -> None:
    adapter = case.make()
    assert re.fullmatch(r"[a-z][a-z0-9_-]*", adapter.name)
    assert adapter.connector_version and adapter.normalizer_version
    payload = adapter.query_payload()
    assert isinstance(payload, dict) and json.loads(json.dumps(payload)) == payload


@pytest.mark.parametrize("case", CASES)
def test_normalization_is_deterministic(case: AdapterCase) -> None:
    adapter = case.make()
    for raw in case.pages:
        assert adapter.normalize_page(raw) == adapter.normalize_page(raw)


@pytest.mark.parametrize("case", CASES)
def test_source_ids_carry_the_adapter_namespace(case: AdapterCase) -> None:
    adapter = case.make()
    prefix = adapter.name + ":"
    for raw in (*case.pages, case.money_page, case.quarantine_page):
        page = adapter.normalize_page(raw)
        assert all(r.source_id.startswith(prefix) for r in page.records)
        assert all(s.startswith(prefix) for s in page.source_ids)


@pytest.mark.parametrize("case", CASES)
def test_every_record_is_accounted_for_exactly_once(case: AdapterCase) -> None:
    adapter = case.make()
    for raw in (*case.pages, case.money_page, case.quarantine_page):
        page = adapter.normalize_page(raw)
        indexes = [r.index for r in page.records] + [i.index for i in page.issues]
        assert len(indexes) == page.record_count == len(set(indexes))
        assert all(0 <= i < page.record_count for i in indexes)


@pytest.mark.parametrize("case", CASES)
def test_content_hashes_are_hex_digests_that_follow_content(case: AdapterCase) -> None:
    adapter = case.make()
    first, second = (adapter.normalize_page(raw) for raw in case.pages[:2])
    for record in (*first.records, *second.records):
        assert re.fullmatch(r"[0-9a-f]{64}", record.content_sha256)
    assert first.records[0].content_sha256 != second.records[0].content_sha256
    assert (
        first.records[0].content_sha256
        == adapter.normalize_page(case.pages[0]).records[0].content_sha256
    )


@pytest.mark.parametrize("case", CASES)
def test_normalized_records_are_exact_and_json_ready(case: AdapterCase) -> None:
    page = case.make().normalize_page(case.money_page)
    assert page.records
    for record in page.records:
        assert floats_in(record.normalized) == []
        assert isinstance(json.loads(json.dumps(record.normalized)), dict)
    assert any("123456789012345678.90" in json.dumps(r.normalized) for r in page.records)


@pytest.mark.parametrize("case", CASES)
def test_a_bad_record_is_quarantined_and_does_not_stop_the_page(case: AdapterCase) -> None:
    page = case.make().normalize_page(case.quarantine_page)
    assert page.records == () and len(page.issues) == 1
    assert isinstance(page.issues[0].reason, str) and page.issues[0].reason
    assert page.issues[0].index == 0


@pytest.mark.parametrize("case", CASES)
def test_a_broken_envelope_is_rejected_as_a_source_page_error(case: AdapterCase) -> None:
    with pytest.raises(SourcePageError):
        case.make().normalize_page(case.broken_envelope)


@pytest.mark.parametrize("case", CASES)
def test_the_size_limit_is_enforced(case: AdapterCase) -> None:
    with pytest.raises(SourcePageError):
        case.make().normalize_page(case.pages[0], max_bytes=10)


@pytest.mark.parametrize("case", CASES)
def test_pagination_fields_are_exposed(case: AdapterCase) -> None:
    page = case.make().normalize_page(case.pages[1])
    assert isinstance(page, NormalizedPage)
    assert page.number == 1 and page.size == 1 and page.total_records == 2
    assert page.total_pages == 2 and page.last is True and page.record_count == 1


def test_the_protocol_module_is_neutral_and_the_kimdis_error_is_a_source_error() -> None:
    graph = dg.build_graph(SRC)
    assert graph["nima.sources.base"] == frozenset()
    assert issubclass(InvalidRecord, SourcePageError)
    assert base.SourceAdapter is SourceAdapter


def test_kimdis_adapter_keeps_the_exact_processing_identity() -> None:
    from nima.ingestion.config import CONNECTOR_VERSION
    from nima.storage.postgres import NORMALIZER_VERSION

    adapter = KimdisAdapter(QUERY)
    assert (adapter.name, adapter.connector_version, adapter.normalizer_version) == (
        "kimdis",
        CONNECTOR_VERSION,
        NORMALIZER_VERSION,
    )
    assert adapter.query_payload() == QUERY.payload()
