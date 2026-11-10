"""Validate persisted normalizer-v1 output before projecting source occurrences."""

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, cast


class InvalidProjection(ValueError):
    """Unsupported or inconsistent source assertions must remain pending."""


@dataclass(frozen=True)
class Mention:
    role: Literal["buyer", "supplier"]
    ordinal: int
    name: str | None
    tax_id: str | None
    source_key: str | None
    country_code: str | None


@dataclass(frozen=True)
class ContractProjection:
    source_id: str
    title: str
    net_amount: Decimal | None
    gross_amount: Decimal | None
    currency: str | None
    bidder_count: int | None
    cancelled: bool | None
    source_submitted_at: str | None
    source_updated_at: str | None
    supplier_count: int | None
    mentions: tuple[Mention, ...]

    def payload(self) -> dict[str, object]:
        payload = asdict(self)
        for field in ("net_amount", "gross_amount"):
            if payload[field] is not None:
                payload[field] = str(payload[field])
        return payload

    def digest(self) -> str:
        encoded = json.dumps(
            self.payload(),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise InvalidProjection("Unexpected normalized fields")
    return cast(dict[str, object], value)


def _text(value: object, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidProjection("Invalid normalized text")
    return value


def _money(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidProjection("Expected exact decimal text")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise InvalidProjection("Invalid money") from None
    if not amount.is_finite():
        raise InvalidProjection("Nonfinite money")
    return amount


def _mention(value: object, role: Literal["buyer", "supplier"], ordinal: int) -> Mention:
    party = _object(value, {"name", "tax_id", "source_key", "country_code"})
    return Mention(
        role,
        ordinal,
        *(_text(party[key]) for key in ("name", "tax_id", "source_key", "country_code")),
    )


def project_contract(value: object) -> ContractProjection:
    contract = _object(
        value,
        {
            "source_id",
            "title",
            "buyer",
            "suppliers",
            "net_amount",
            "gross_amount",
            "currency",
            "bidder_count",
            "cancelled",
            "source_submitted_at",
            "source_updated_at",
            "references",
        },
    )
    suppliers = contract["suppliers"]
    if suppliers is not None and (not isinstance(suppliers, list) or len(suppliers) > 1000):
        raise InvalidProjection("Invalid or excessive supplier occurrences")
    bidder_count, cancelled = contract["bidder_count"], contract["cancelled"]
    if bidder_count is not None and (type(bidder_count) is not int or bidder_count < 0):
        raise InvalidProjection("Invalid bidder count")
    if cancelled is not None and not isinstance(cancelled, bool):
        raise InvalidProjection("Invalid cancellation flag")
    if not isinstance(contract["references"], list):
        raise InvalidProjection("Invalid references")
    source_id, title = (
        _text(contract["source_id"], required=True),
        _text(contract["title"], required=True),
    )
    return ContractProjection(
        cast(str, source_id),  # _text(required=True) rejects None.
        cast(str, title),
        _money(contract["net_amount"]),
        _money(contract["gross_amount"]),
        _text(contract["currency"]),
        bidder_count,
        cancelled,
        _text(contract["source_submitted_at"]),
        _text(contract["source_updated_at"]),
        None if suppliers is None else len(suppliers),
        (
            _mention(contract["buyer"], "buyer", 0),
            *(_mention(party, "supplier", index) for index, party in enumerate(suppliers or [])),
        ),
    )
