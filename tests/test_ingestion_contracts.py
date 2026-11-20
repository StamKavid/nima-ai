"""Source acceptance and producer guarantees preserve exact captured meanings."""

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from importlib.resources import files
from typing import Any

import pytest

from nima.contracts.schema import ContractError, validate_contract
from nima.sources import kimdis_contracts as gates
from nima.sources.kimdis import Evidence, normalize_contract
from tests.test_collection import body
from tests.test_kimdis_contracts import source_page


@pytest.mark.parametrize("boundary", ["source", "normalized"])
def test_owned_metadata_is_draft_odcs_with_explicit_policy(boundary: gates.Boundary) -> None:
    name = f"kimdis-{boundary}-v1.odcs.json"
    value = validate_contract(json.loads(files("nima.contracts").joinpath(name).read_bytes()))
    assert value["status"] == "draft" and value["version"] == "1.0.1"
    assert value["id"] == f"nima.kimdis-{boundary}"
    assert value["customProperties"][0]["value"] == gates.policy(boundary)
    assert not value.get("slaProperties")


def test_raw_acceptance_does_not_discard_malformed_items_or_unknown_fields() -> None:
    raw = json.loads(body(total=1))
    raw["content"] = [None, 1, "bad", {"title": 42}]
    raw["size"] = raw["totalElements"] = 4
    raw["new_source_field"] = {"reported": "unchanged"}
    before = json.dumps(raw, sort_keys=True)
    gates.validate_source(raw)
    assert json.dumps(raw, sort_keys=True) == before


def test_normalized_view_keeps_decimal_greek_identifiers_and_unknowns() -> None:
    raw = source_page().replace(b'"1234.56"', b"1234.56000000000000000001")
    record = normalize_contract(raw)
    before = repr(record)
    gates.validate_record(record, expected_digest=hashlib.sha256(raw).hexdigest(), index=0)
    assert repr(record) == before
    assert record.net_amount == Decimal("1234.56000000000000000001")
    assert record.title == "ΔΟΚΙΜΑΣΤΙΚΗ ΣΥΜΒΑΣΗ"
    assert record.buyer.tax_id == "012345678" and record.source_updated_at is None


@pytest.mark.parametrize(
    "change",
    [
        {"net_amount": 1.5},
        {"net_amount": "1.5"},
        {"gross_amount": Decimal("Infinity")},
        {"bidder_count": True},
        {"bidder_count": 1.0},
        {"title": 42},
        {"evidence": Evidence("0" * 64, "/content/0")},
        {"evidence": Evidence("0" * 64, "/content/7")},
    ],
)
def test_invalid_producer_values_are_rejected_without_coercion(change: dict[str, Any]) -> None:
    raw = source_page()
    record = replace(normalize_contract(raw), **change)
    with pytest.raises(ContractError, match="^normalized_contract$"):
        gates.validate_record(record, expected_digest=hashlib.sha256(raw).hexdigest(), index=0)


def test_compiled_packaged_rules_are_reused_without_following_metadata_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = source_page()
    record = normalize_contract(raw)
    gates.validate_source(json.loads(body(total=1)))
    gates.validate_record(record, expected_digest=hashlib.sha256(raw).hexdigest(), index=0)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Previously validated immutable rules must not be reloaded or fetched")

    monkeypatch.setattr(gates, "files", forbidden)
    monkeypatch.setattr("httpx.Client.request", forbidden)
    gates.validate_source(json.loads(body(total=1)))
    gates.validate_record(record, expected_digest=hashlib.sha256(raw).hexdigest(), index=0)
