"""Source contracts preserve money, unknowns, and evidence needed downstream."""

import hashlib
import json
from decimal import Decimal

import pytest

from nima.sources.kimdis import InvalidRecord, normalize_contract


def source_page(**changes: object) -> bytes:
    record: dict[str, object] = {
        "referenceNumber": "26SYMV000000001",
        "title": "ΔΟΚΙΜΑΣΤΙΚΗ ΣΥΜΒΑΣΗ",
        "organization": {"key": "1001", "value": "ΔΟΚΙΜΑΣΤΙΚΟΣ ΦΟΡΕΑΣ"},
        "organizationVatNumber": "012345678",
        "totalCostWithoutVAT": "1234.56",
        "totalCostWithVAT": "1530.8544",
        "bidsSubmitted": None,
        "cancelled": False,
        "submissionDate": "2026-11-06T10:30:00",
        "lastUpdateDate": None,
        "contractingDataDetails": {
            "contractingMembersDataList": [
                {"name": "ΔΟΚΙΜΑΣΤΙΚΗ Α", "vatNumber": "001234567", "country": {"key": "GR"}},
                {"name": "ΔΟΚΙΜΑΣΤΙΚΗ Β", "vatNumber": "EL-EXAMPLE", "country": None},
            ]
        },
    }
    record.update(changes)
    return json.dumps({"content": [record]}, ensure_ascii=False).encode()


def test_preserves_exact_money_and_response_evidence() -> None:
    body = source_page().replace(b'"1234.56"', b"1234.56000000000000000001")
    contract = normalize_contract(body)
    assert contract.net_amount == Decimal("1234.56000000000000000001")
    assert contract.gross_amount == Decimal("1530.8544")
    assert contract.evidence.response_sha256 == hashlib.sha256(body).hexdigest()
    assert contract.evidence.json_pointer == "/content/0"


def test_preserves_greek_text_and_leading_zero_identifiers() -> None:
    contract = normalize_contract(source_page())
    assert contract.source_id == "kimdis:26SYMV000000001"
    assert contract.title == "ΔΟΚΙΜΑΣΤΙΚΗ ΣΥΜΒΑΣΗ"
    assert contract.buyer.tax_id == "012345678"
    assert contract.buyer.source_key == "1001"
    assert contract.suppliers is not None
    assert contract.suppliers[0].tax_id == "001234567"


def test_keeps_joint_participation_without_allocating_contract_value() -> None:
    contract = normalize_contract(source_page())
    assert contract.suppliers is not None
    assert len(contract.suppliers) == 2
    assert contract.suppliers[0].country_code == "GR"
    assert contract.suppliers[1].country_code is None
    assert contract.net_amount == Decimal("1234.56")
    assert not hasattr(contract.suppliers[0], "amount")


def test_missing_values_do_not_become_zero_or_an_empty_supplier_list() -> None:
    contract = normalize_contract(
        source_page(contractingDataDetails=None, totalCostWithoutVAT=None)
    )
    assert contract.suppliers is None
    assert contract.bidder_count is None
    assert contract.net_amount is None
    assert contract.source_updated_at is None


def test_an_explicit_empty_supplier_list_stays_distinct_from_missing() -> None:
    body = source_page(contractingDataDetails={"contractingMembersDataList": []})
    assert normalize_contract(body).suppliers == ()


@pytest.mark.parametrize("value", [0, "0", 2, "2"])
def test_accepts_documented_integer_and_text_bidder_counts(value: object) -> None:
    assert normalize_contract(source_page(bidsSubmitted=value)).bidder_count == int(str(value))


@pytest.mark.parametrize("value", [True, -1, "many", "1.5", 1.5])
def test_rejects_invalid_bidder_counts(value: object) -> None:
    with pytest.raises(InvalidRecord, match="bidsSubmitted"):
        normalize_contract(source_page(bidsSubmitted=value))


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", True, "1.234,56", {}])
def test_rejects_ambiguous_or_non_finite_money(value: object) -> None:
    with pytest.raises(InvalidRecord, match="totalCostWithoutVAT"):
        normalize_contract(source_page(totalCostWithoutVAT=value))


def test_preserves_cancellation_and_unqualified_source_time() -> None:
    contract = normalize_contract(source_page(cancelled=True))
    assert contract.cancelled is True
    assert contract.source_submitted_at == "2026-11-06T10:30:00"


def test_keeps_reference_meanings_separate() -> None:
    contract = normalize_contract(
        source_page(
            auctionRefNo="26AWRD000000002",
            prevReferenceNo="26SYMV000000003",
            paymentRefNo=["26PAY000000004"],
            diavgeiaADA="EXAMPLE-ADA",
        )
    )
    assert [(ref.relation, ref.target_id) for ref in contract.references] == [
        ("award", "kimdis:26AWRD000000002"),
        ("previous_record", "kimdis:26SYMV000000003"),
        ("commitment_decision", "diavgeia:EXAMPLE-ADA"),
        ("payment_order", "kimdis:26PAY000000004"),
    ]


def test_can_select_a_later_record_without_losing_its_evidence_location() -> None:
    record = json.loads(source_page())["content"][0]
    body = json.dumps(
        {"content": [record, {**record, "referenceNumber": "26SYMV000000005"}]}
    ).encode()
    contract = normalize_contract(body, index=1)
    assert contract.source_id == "kimdis:26SYMV000000005"
    assert contract.evidence.json_pointer == "/content/1"


@pytest.mark.parametrize("index", [-1, 1, True])
def test_rejects_invalid_record_indexes(index: int) -> None:
    with pytest.raises(InvalidRecord, match="index"):
        normalize_contract(source_page(), index=index)


@pytest.mark.parametrize("body", [b"{", b"[]", b"{}", b'{"content":{}}', b'{"content":[1]}'])
def test_rejects_malformed_envelopes(body: bytes) -> None:
    with pytest.raises(InvalidRecord):
        normalize_contract(body)


def test_rejects_duplicate_json_fields() -> None:
    body = source_page().replace(b'"1234.56"', b'100, "totalCostWithoutVAT": 200')
    with pytest.raises(InvalidRecord, match="Duplicate"):
        normalize_contract(body)


def test_limits_the_input_size_before_decoding() -> None:
    with pytest.raises(InvalidRecord, match="size"):
        normalize_contract(source_page(), max_bytes=20)


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([{"currency": {"key": "EUR"}}, {"currency": {"key": "EUR"}}], "EUR"),
        ([{"currency": {"key": "EUR"}}, {"currency": {"key": "USD"}}], None),
        ([{"currency": {"key": "EUR"}}, {"currency": None}], None),
        ([{"currency": {"key": "EUR"}}, {"currency": {"key": None}}], None),
        ([], None),
    ],
)
def test_only_uses_unambiguous_reported_currency(
    items: list[dict[str, object]], expected: str | None
) -> None:
    assert normalize_contract(source_page(objectDetailsList=items)).currency == expected


def test_native_json_non_finite_numbers_are_rejected() -> None:
    body = source_page().replace(b'"1234.56"', b"NaN")
    with pytest.raises(InvalidRecord, match="Non-finite"):
        normalize_contract(body)


def test_preserves_zero_and_negative_reported_amounts_without_clamping() -> None:
    contract = normalize_contract(source_page(totalCostWithoutVAT=0, totalCostWithVAT="-1.25"))
    assert contract.net_amount == Decimal("0")
    assert contract.gross_amount == Decimal("-1.25")


def test_validates_remaining_items_after_an_unknown_currency() -> None:
    with pytest.raises(InvalidRecord, match="objectDetailsList"):
        normalize_contract(source_page(objectDetailsList=[{"currency": None}, 42]))


@pytest.mark.parametrize(
    "changes",
    [
        {"referenceNumber": " "},
        {"referenceNumber": 123},
        {"title": {}},
        {"organization": []},
        {"organizationVatNumber": 123},
        {"contractingDataDetails": []},
        {"contractingDataDetails": {"contractingMembersDataList": "bad"}},
        {"contractingDataDetails": {"contractingMembersDataList": [1]}},
        {"cancelled": "false"},
        {"paymentRefNo": "26PAY000000004"},
        {"paymentRefNo": [None]},
    ],
)
def test_rejects_unexpected_field_types(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidRecord):
        normalize_contract(source_page(**changes))
