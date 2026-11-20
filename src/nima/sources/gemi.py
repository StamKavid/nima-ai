"""Strict source assertions from the documented GEMI Company schema.

https://opendata-api.businessportal.gr/api-docs
https://docs.python.org/3.12/library/json.html#json.loads
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, DecimalException
from types import MappingProxyType
from typing import Never, cast

ENDPOINT = "https://opendata-api.businessportal.gr/api/opendata/v1/companies"
NORMALIZER_VERSION = "gemi-company-v1"
MAX_BODY = 8 * 1024 * 1024
type Scalar = str | int | bool | tuple[str, ...] | None


class InvalidProfile(ValueError):
    """Only a controlled field path, never a source value, appears in this error."""


@dataclass(frozen=True)
class Assertion:
    value: Scalar
    json_pointer: str | None


@dataclass(frozen=True)
class RegistryCompany:
    source_id: str
    response_sha256: str
    fields: Mapping[str, Assertion]
    activities: tuple[Mapping[str, Assertion], ...] | None
    activities_pointer: str | None

    def payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "normalizer_version": NORMALIZER_VERSION,
            "response_sha256": self.response_sha256,
            "fields": {k: asdict(v) for k, v in self.fields.items()},
            "activities": None
            if self.activities is None
            else [{k: asdict(v) for k, v in row.items()} for row in self.activities],
            "activities_pointer": self.activities_pointer,
        }


def registry_number(value: str) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 64
        or not value.isascii()
        or not value.isdecimal()
        or int(value) <= 0
    ):
        raise ValueError("Invalid registry number")
    return str(int(value))


def _object(value: object, path: str, *, optional: bool = False) -> dict[str, object]:
    if value is None and optional:
        return {}
    if not isinstance(value, dict):
        raise InvalidProfile(path)
    return cast(dict[str, object], value)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise InvalidProfile("json")
        result[key] = value
    return result


def _constant(_: str) -> Never:
    raise InvalidProfile("json")


def _text(value: object) -> str | None:
    if value is not None:
        if not isinstance(value, str):
            raise ValueError
        value.encode("utf-8")
    return value


def _integer(value: object) -> int | None:
    if value is not None and type(value) is not int:
        raise ValueError
    return value


def _registry_id(value: object) -> int | None:
    """The schema declares an integer; the live API sends a canonical decimal string."""
    if isinstance(value, str) and value.isascii() and value.isdecimal() and value[0] != "0":
        return int(value)
    return _integer(value)


def _boolean(value: object) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError
    return value


def _array(value: object) -> list[object] | None:
    if value is not None and (not isinstance(value, list) or len(value) > 1000):
        raise ValueError
    return cast(list[object] | None, value)


def _aliases(value: object) -> tuple[str, ...] | None:
    items = _array(value)
    if items is None:
        return None
    if any(not isinstance(item, str) for item in items):
        raise ValueError
    return tuple(cast(str, _text(item)) for item in items)


def _date(value: object) -> str | None:
    text = _text(value)
    if text is not None and date.fromisoformat(text).isoformat() != text:
        raise ValueError
    return text


def _field(
    obj: dict[str, object], key: str, parent: str, convert: Callable[[object], Scalar]
) -> Assertion:
    path = f"{parent}/{key}"
    try:
        return Assertion(convert(obj.get(key)), path if key in obj else None)
    except (ValueError, TypeError, OverflowError):
        raise InvalidProfile(path) from None


def decode_body(raw: bytes) -> dict[str, object]:
    """Strict JSON object decoding shared by single profiles and search responses."""
    if len(raw) > MAX_BODY:
        raise InvalidProfile("body_size")
    try:
        return _object(
            json.loads(
                raw.decode("utf-8"),
                parse_float=Decimal,
                parse_constant=_constant,
                object_pairs_hook=_pairs,
            ),
            "json",
        )
    except (ValueError, RecursionError, DecimalException):
        raise InvalidProfile("json") from None


def normalize_profile(raw: bytes, expected_id: str) -> RegistryCompany:
    expected = registry_number(expected_id)
    return normalize_company(decode_body(raw), hashlib.sha256(raw).hexdigest(), expected=expected)


def normalize_company(
    obj: dict[str, object], response_sha256: str, *, expected: str | None, prefix: str = ""
) -> RegistryCompany:
    """Normalize one Company object; ``prefix`` locates it inside the original response body.

    A single profile has an empty prefix and an expected registry number. A search hit has the
    pointer of its array element and takes its registry number from the object itself.
    """
    try:
        number = _registry_id(obj.get("arGemi"))
    except ValueError:
        raise InvalidProfile(f"{prefix}/arGemi") from None
    if number is None or number <= 0 or (expected is not None and str(number) != expected):
        raise InvalidProfile(f"{prefix}/arGemi")
    fields = {
        name: _field(obj, source, prefix, converter)
        for name, source, converter in (
            ("registry_number", "arGemi", _registry_id),
            ("reported_afm", "afm", _text),
            ("name_el", "coNameEl", _text),
            ("names_en", "coNamesEn", _aliases),
            ("titles_el", "coTitlesEl", _aliases),
            ("titles_en", "coTitlesEn", _aliases),
            ("is_branch", "isBranch", _boolean),
            ("auto_registered", "autoRegistered", _boolean),
            ("incorporation_date", "incorporationDate", _date),
            ("last_status_change", "lastStatusChange", _date),
        )
    }
    for source, name in (("legalType", "legal_type"), ("status", "status")):
        nested = _object(obj.get(source), f"{prefix}/{source}", optional=True)
        fields[f"{name}_id"] = _field(nested, "id", f"{prefix}/{source}", _integer)
        fields[f"{name}_label"] = _field(nested, "descr", f"{prefix}/{source}", _text)
    try:
        activities = _array(obj.get("activities"))
    except ValueError:
        raise InvalidProfile(f"{prefix}/activities") from None
    rows = []
    for index, value in enumerate(activities or []):
        path = f"{prefix}/activities/{index}"
        row = _object(value, path)
        activity = _object(row.get("activity"), f"{path}/activity", optional=True)
        rows.append(
            MappingProxyType(
                {
                    "code": _field(activity, "id", f"{path}/activity", _text),
                    "label": _field(activity, "descr", f"{path}/activity", _text),
                    "version": _field(activity, "kadVersion", f"{path}/activity", _text),
                    "type": _field(row, "type", path, _text),
                    "date_from": _field(row, "dtFrom", path, _date),
                    "date_to": _field(row, "dtTo", path, _date),
                }
            )
        )
    return RegistryCompany(
        f"gemi:{number}",
        response_sha256,
        MappingProxyType(fields),
        None if activities is None else tuple(rows),
        f"{prefix}/activities" if "activities" in obj else None,
    )
