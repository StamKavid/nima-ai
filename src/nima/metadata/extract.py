"""Pure reported fields from the retained official KIMDIS/GEMI contracts.

https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help
https://opendata-api.businessportal.gr/api-docs
"""

import re
from typing import TypedDict, cast

from nima.sources.kimdis import decode_response, normalize_page

VERSION = "market-metadata-v1"
MAX_ASSERTIONS = 10_000
DIMENSIONS = (
    "buyer_function",
    "buyer_legal_class",
    "buyer_type",
    "procurement_cpv",
    "supplier_kad",
)


class MetadataError(ValueError):
    """Fixed private-safe reason; no input values or paths."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class Assertion(TypedDict):
    dimension: str
    code: str | None
    label: str | None
    status: str
    taxonomy_version: str | None
    taxonomy_validation: str
    expected_pointer: str
    json_pointer: str | None
    field_pointers: dict[str, str | None]
    details: dict[str, str | None]


class MetadataRecord(TypedDict):
    source_id: str | None
    record_index: int
    record_pointer: str
    content_sha256: str
    record_status: str
    assertions: list[Assertion]


def _text(value: object, maximum: int = 4096) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        return None
    try:
        value.encode("utf-8")
    except UnicodeError:
        return None
    return value


def _row(dimension: str, pointer: str, status: str, *, present: bool = True) -> Assertion:
    return {
        "dimension": dimension,
        "code": None,
        "label": None,
        "status": status,
        "taxonomy_version": None,
        "taxonomy_validation": "not_checked",
        "expected_pointer": pointer,
        "json_pointer": pointer if present else None,
        "field_pointers": {},
        "details": {},
    }


def _pair(value: object, dimension: str, pointer: str, *, present: bool) -> Assertion:
    if not present or value is None:
        return _row(dimension, pointer, "missing" if not present else "null", present=present)
    row = _row(dimension, pointer, "invalid")
    if not isinstance(value, dict):
        return row
    code, label = _text(value.get("key"), 512), _text(value.get("value"))
    row["code"], row["label"] = code, label
    row["field_pointers"] = {
        field: pointer + "/" + source if source in value else None
        for field, source in (("code", "key"), ("label", "value"))
    }
    pattern = r"[0-9]{8}-[0-9]" if dimension == "procurement_cpv" else r"[0-9]+"
    if (
        code
        and re.fullmatch(pattern, code)
        and (dimension == "procurement_cpv" or int(code) > 0)
        and (value.get("value") is None or label is not None)
    ):
        row["status"] = "reported"
    return row


def _cpvs(record: dict[str, object], parent: str) -> list[Assertion]:
    pointer = parent + "/objectDetailsList"
    objects = record.get("objectDetailsList")
    if not isinstance(objects, list) or not objects:
        status = (
            "missing"
            if "objectDetailsList" not in record
            else "null"
            if objects is None
            else "empty"
            if objects == []
            else "invalid"
        )
        return [_row("procurement_cpv", pointer, status, present="objectDetailsList" in record)]
    rows = []
    for index, obj in enumerate(objects):
        path = f"{pointer}/{index}/cpvs"
        if not isinstance(obj, dict):
            rows.append(_row("procurement_cpv", f"{pointer}/{index}", "invalid"))
            continue
        items = obj.get("cpvs")
        if not isinstance(items, list) or not items:
            status = (
                "missing"
                if "cpvs" not in obj
                else "null"
                if items is None
                else "empty"
                if items == []
                else "invalid"
            )
            rows.append(_row("procurement_cpv", path, status, present="cpvs" in obj))
        else:
            for ordinal, item in enumerate(items):
                rows.append(_pair(item, "procurement_cpv", f"{path}/{ordinal}", present=True))
                if len(rows) > MAX_ASSERTIONS:
                    raise MetadataError("metadata_limit")
        if len(rows) > MAX_ASSERTIONS:
            raise MetadataError("metadata_limit")
    return rows


def kimdis_metadata(raw: bytes) -> tuple[MetadataRecord, ...]:
    page = normalize_page(raw)
    content = cast(list[object], decode_response(raw)["content"])
    valid = {int(c.evidence.json_pointer.rsplit("/", 1)[1]) for c in page.contracts}
    result: list[MetadataRecord] = []
    count = 0
    for index, value in enumerate(content):
        parent = f"/content/{index}"
        record = cast(dict[str, object], value) if isinstance(value, dict) else {}
        rows = [
            _pair(record.get(field), dimension, parent + "/" + field, present=field in record)
            for field, dimension in (
                ("contractingAuthorityActivity", "buyer_function"),
                ("classificationOfPublicLawOrganization", "buyer_legal_class"),
                ("typeOfContractingAuthority", "buyer_type"),
            )
        ] + _cpvs(record, parent)
        count += len(rows)
        if count > MAX_ASSERTIONS:
            raise MetadataError("metadata_limit")
        reference = _text(record.get("referenceNumber"))
        result.append(
            {
                "source_id": None if reference is None else "kimdis:" + reference,
                "record_index": index,
                "record_pointer": parent,
                "content_sha256": page.record_hashes[index],
                "record_status": "normalized" if index in valid else "quarantined",
                "assertions": rows,
            }
        )
    return tuple(result)


def gemi_metadata(profile: dict[str, object]) -> list[Assertion]:
    """Accept the payload produced by the strict, hash-verified GEMI normalizer."""
    activities = profile["activities"]
    if activities is None or activities == []:
        status = (
            "empty"
            if activities == []
            else ("missing" if profile["activities_pointer"] is None else "null")
        )
        return [
            _row(
                "supplier_kad",
                "/activities",
                status,
                present=profile["activities_pointer"] is not None,
            )
        ]
    rows = []
    for index, item in enumerate(cast(list[dict[str, dict[str, object]]], activities)):
        pointer = f"/activities/{index}/activity"
        row = _row("supplier_kad", pointer, "reported")
        row["code"] = _text(item["code"]["value"], 512)
        row["label"] = _text(item["label"]["value"])
        row["taxonomy_version"] = _text(item["version"]["value"], 512)
        if (
            row["code"] is None
            or (item["label"]["value"] is not None and row["label"] is None)
            or (item["version"]["value"] is not None and row["taxonomy_version"] is None)
        ):
            row["status"] = "invalid"
        row["field_pointers"] = {
            key: cast(str | None, value["json_pointer"]) for key, value in item.items()
        }
        # The activity object itself may be absent; field pointers stay authoritative.
        if all(item[k]["json_pointer"] is None for k in ("code", "label", "version")):
            row["json_pointer"] = None
        row["details"] = {
            key: cast(str | None, item[key]["value"]) for key in ("type", "date_from", "date_to")
        }
        rows.append(row)
        if len(rows) > MAX_ASSERTIONS:
            raise MetadataError("metadata_limit")
    return rows


def select_assertions(
    rows: list[Assertion], dimension: str | None = None, code: str | None = None
) -> list[Assertion]:
    if (dimension is not None and dimension not in DIMENSIONS) or (
        code is not None and (dimension is None or _text(code, 512) is None)
    ):
        raise MetadataError("metadata_input")
    return [
        row
        for row in rows
        if (dimension is None or row["dimension"] == dimension)
        and (code is None or (row["status"] == "reported" and row["code"] == code))
    ]
