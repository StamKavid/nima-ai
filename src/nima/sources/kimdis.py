"""Normalize reported KIMDIS contracts without inferring identity or wrongdoing.

Source contract: https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help
The response hash identifies bytes; collection and durable archival are separate work.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Never, cast

type Relation = Literal["award", "previous_record", "commitment_decision", "payment_order"]


class InvalidRecord(ValueError):
    """A source response cannot be normalized without guessing or losing meaning."""


@dataclass(frozen=True)
class Party:
    name: str | None
    tax_id: str | None
    source_key: str | None = None
    country_code: str | None = None


@dataclass(frozen=True)
class Evidence:
    response_sha256: str
    json_pointer: str


@dataclass(frozen=True)
class Reference:
    relation: Relation
    target_id: str
    source_field: str


@dataclass(frozen=True)
class Contract:
    source_id: str
    title: str
    buyer: Party
    suppliers: tuple[Party, ...] | None
    net_amount: Decimal | None
    gross_amount: Decimal | None
    currency: str | None
    bidder_count: int | None
    cancelled: bool | None
    source_submitted_at: str | None
    source_updated_at: str | None
    references: tuple[Reference, ...]
    evidence: Evidence


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidRecord(f"Expected an object at {path}")
    return cast(dict[str, object], value)


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise InvalidRecord(f"Expected an array at {path}")
    return cast(list[object], value)


def _text(value: object, path: str, *, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise InvalidRecord(f"Missing text at {path}")
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidRecord(f"Expected nonblank text at {path}")
    return value


def _money(value: object, path: str) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise InvalidRecord(f"Expected an exact monetary value at {path}")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidRecord(f"Invalid monetary value at {path}") from exc
    if not amount.is_finite():
        raise InvalidRecord(f"Non-finite monetary value at {path}")
    return amount


def _bidder_count(value: object) -> int | None:
    if value is None or value == "":
        return None
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise InvalidRecord("Invalid bidder count at bidsSubmitted")


def _suppliers(value: object) -> tuple[Party, ...] | None:
    if value is None:
        return None
    details = _object(value, "contractingDataDetails")
    members = details.get("contractingMembersDataList")
    if members is None:
        return None
    parties: list[Party] = []
    for index, member in enumerate(_array(members, "contractingMembersDataList")):
        path = f"contractingMembersDataList/{index}"
        supplier = _object(member, path)
        country = supplier.get("country")
        parties.append(
            Party(
                name=_text(supplier.get("name"), f"{path}/name"),
                tax_id=_text(supplier.get("vatNumber"), f"{path}/vatNumber"),
                country_code=(
                    None
                    if country is None
                    else _text(
                        _object(country, f"{path}/country").get("key"), f"{path}/country/key"
                    )
                ),
            )
        )
    return tuple(parties)


def _currency(value: object) -> str | None:
    if value is None:
        return None
    codes: set[str] = set()
    complete = True
    for item in _array(value, "objectDetailsList"):
        currency = _object(item, "objectDetailsList/item").get("currency")
        if currency is None:
            complete = False
            continue
        code = _text(_object(currency, "currency").get("key"), "currency/key")
        if code is None:
            complete = False
        else:
            codes.add(code)
    return next(iter(codes)) if complete and len(codes) == 1 else None


def _references(record: dict[str, object]) -> tuple[Reference, ...]:
    refs: list[Reference] = []
    fields: tuple[tuple[str, Relation, str], ...] = (
        ("auctionRefNo", "award", "kimdis"),
        ("prevReferenceNo", "previous_record", "kimdis"),
        ("diavgeiaADA", "commitment_decision", "diavgeia"),
    )
    for field, relation, namespace in fields:
        target = _text(record.get(field), field)
        if target is not None:
            refs.append(Reference(relation, f"{namespace}:{target}", field))
    payments = record.get("paymentRefNo")
    if payments is not None:
        for value in _array(payments, "paymentRefNo"):
            target = _text(value, "paymentRefNo/item", required=True)
            refs.append(Reference("payment_order", f"kimdis:{target}", "paymentRefNo"))
    return tuple(refs)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidRecord("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value: str) -> Never:
    raise InvalidRecord("Non-finite JSON number")


def normalize_contract(
    raw_response: bytes, *, index: int = 0, max_bytes: int = 8 * 1024 * 1024
) -> Contract:
    """Normalize one response record, preserving source evidence and unknowns.

    ``index`` selects an item in the response's ``content`` array. Source timestamps
    remain unqualified text. Currency is known only when every reported line item
    has the same code. No value is allocated among suppliers.
    """
    if len(raw_response) > max_bytes or max_bytes <= 0:
        raise InvalidRecord("Response exceeds the configured size limit")
    try:
        # https://docs.python.org/3.12/library/json.html#json.loads
        decoded: object = json.loads(
            raw_response,
            parse_float=Decimal,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except InvalidRecord:
        raise
    except (ValueError, RecursionError, InvalidOperation) as exc:
        raise InvalidRecord(f"Invalid JSON response: {type(exc).__name__}") from exc
    content = _array(_object(decoded, "response").get("content"), "content")
    if type(index) is not int or not 0 <= index < len(content):
        raise InvalidRecord("Record index is outside the response")
    record = _object(content[index], f"content/{index}")
    organization = record.get("organization")
    buyer = {} if organization is None else _object(organization, "organization")
    cancelled = record.get("cancelled")
    if cancelled is not None and not isinstance(cancelled, bool):
        raise InvalidRecord("Expected a boolean at cancelled")
    reference = _text(record.get("referenceNumber"), "referenceNumber", required=True)
    return Contract(
        source_id=f"kimdis:{reference}",
        title=cast(str, _text(record.get("title"), "title", required=True)),
        buyer=Party(
            name=_text(buyer.get("value"), "organization/value"),
            tax_id=_text(record.get("organizationVatNumber"), "organizationVatNumber"),
            source_key=_text(buyer.get("key"), "organization/key"),
        ),
        suppliers=_suppliers(record.get("contractingDataDetails")),
        net_amount=_money(record.get("totalCostWithoutVAT"), "totalCostWithoutVAT"),
        gross_amount=_money(record.get("totalCostWithVAT"), "totalCostWithVAT"),
        currency=_currency(record.get("objectDetailsList")),
        bidder_count=_bidder_count(record.get("bidsSubmitted")),
        cancelled=cancelled,
        source_submitted_at=_text(record.get("submissionDate"), "submissionDate"),
        source_updated_at=_text(record.get("lastUpdateDate"), "lastUpdateDate"),
        references=_references(record),
        evidence=Evidence(hashlib.sha256(raw_response).hexdigest(), f"/content/{index}"),
    )
