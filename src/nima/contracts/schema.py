"""Source-neutral, offline ODCS schema/profile and conservative evolution checks."""

import hashlib
import json
import re
from importlib.resources import files
from typing import Any, cast

from jsonschema import Draft201909Validator
from jsonschema.exceptions import ValidationError

SCHEMA_SHA256 = "edb41f33ec46e84780e99872ab2bd67f074959d2bf3e9c9fc54e61f8982b0d93"

_OPTIONS = {
    "string": {"minLength", "maxLength", "pattern"},
    "integer": {"minimum", "maximum"},
    "number": {"minimum", "maximum"},
    "boolean": set(),
    "object": {"minProperties", "maxProperties"},
    "array": {"minItems", "maxItems", "uniqueItems"},
}

_ELEMENT_KEYS = {
    "name",
    "logicalType",
    "logicalTypeOptions",
    "required",
    "enum",
    "properties",
    "items",
    "description",
    "businessName",
    "dataGranularityDescription",
    "quality",
    "customProperties",
}


class ContractError(ValueError):
    """Fixed failure only; no source data or schema validation details escape."""


def canonical(value: object) -> str:
    """Keep JSON boolean/number distinctions that Python equality collapses."""
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _shape(element: dict[str, Any], *, root: bool = False) -> dict[str, Any]:
    kind = element.get("logicalType")
    options = element.get("logicalTypeOptions", {})
    entries = element.get("customProperties", [])
    flags = {entry["property"]: entry["value"] for entry in entries}
    if (
        element.keys() - _ELEMENT_KEYS
        or ("quality" in element and not root)
        or kind not in _OPTIONS
        or options.keys() - _OPTIONS[kind]
        or len(flags) != len(entries)
        or flags.keys() - {"nima.present", "nima.opaqueItems"}
        or any(value is not True for value in flags.values())
        or ("nima.present" in flags and (root or "name" not in element))
        or ("nima.opaqueItems" in flags and (kind != "array" or "items" in element))
    ):
        raise ContractError("analytics_contract")
    result: dict[str, Any] = {"type": kind, **options}
    if element.get("required") is False:
        result["type"] = [kind, "null"]
    if "enum" in element:
        result["enum"] = [entry["value"] for entry in element["enum"]]
    if kind == "object":
        fields = element.get("properties", [])
        names = [field["name"] for field in fields]
        if len(set(names)) != len(names):
            raise ContractError("analytics_contract")
        result["properties"] = {field["name"]: _shape(field) for field in fields}
        result["required"] = [
            field["name"]
            for field in fields
            if field.get("required")
            or any(flag["property"] == "nima.present" for flag in field.get("customProperties", []))
        ]
    if kind == "array":
        if "items" not in element and "nima.opaqueItems" not in flags:
            raise ContractError("analytics_contract")
        result["items"] = {} if "nima.opaqueItems" in flags else _shape(element["items"])
    return result


def _version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value):
        raise ContractError("analytics_contract")
    return cast(tuple[int, int, int], tuple(int(part) for part in value.split(".")))


def validate_contract(value: object) -> dict[str, Any]:
    """Validate metadata only; quality implementation names are never executed."""
    # The pinned official schema has only local fragment references, never URLs.
    try:
        raw = files(__package__).joinpath("odcs-3.2.0.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
            raise ContractError("analytics_contract")
        Draft201909Validator(json.loads(raw)).validate(value)
        document = cast(dict[str, Any], value)
        canonical(document)
        _version(document["version"])
        if document["apiVersion"] != "v3.2.0" or len(document.get("schema", [])) != 1:
            raise ContractError("analytics_contract")
        _shape(document["schema"][0], root=True)
        properties = document.get("customProperties", [])
        names = [entry["property"] for entry in properties]
        if len(set(names)) != len(names) or "nima.semanticDefinition" not in names:
            raise ContractError("analytics_contract")
        return document
    except (OSError, ValidationError, KeyError, TypeError, ValueError, RecursionError):
        raise ContractError("analytics_contract") from None


def _shape_change(previous: dict[str, Any], current: dict[str, Any]) -> int:
    """0 unchanged, 1 additive optional shape, 2 changed consumer guarantee."""
    keys = {"properties", "required", "items"}
    if canonical({k: v for k, v in previous.items() if k not in keys}) != canonical(
        {k: v for k, v in current.items() if k not in keys}
    ) or set(previous.get("required", [])) - set(current.get("required", [])):
        return 2
    old_fields, new_fields = previous.get("properties", {}), current.get("properties", {})
    if old_fields.keys() - new_fields.keys():
        return 2
    additions = new_fields.keys() - old_fields.keys()
    if set(current.get("required", [])) - set(previous.get("required", [])):
        return 2
    changes = [int(bool(additions))]
    changes.extend(_shape_change(field, new_fields[name]) for name, field in old_fields.items())
    if "items" in previous:
        changes.append(_shape_change(previous["items"], current.get("items", {})))
    return max(changes)


def check_compatibility(previous: object, current: object) -> str:
    """Conservative policy, not a universal ODCS compatibility implementation."""
    old, new = validate_contract(previous), validate_contract(current)
    if old["id"] != new["id"]:
        raise ContractError("contract_identity")
    if canonical(old) == canonical(new):
        return "unchanged"
    old_version, new_version = _version(old["version"]), _version(new["version"])
    if new_version <= old_version:
        raise ContractError("contract_version")
    descriptive = {"version", "name", "team", "support", "authoritativeDefinitions", "schema"}
    changed_guarantees = canonical(
        {k: v for k, v in old.items() if k not in descriptive}
    ) != canonical({k: v for k, v in new.items() if k not in descriptive})
    old_model, new_model = old["schema"][0], new["schema"][0]
    model_keys = {"properties", "description", "businessName", "authoritativeDefinitions"}
    changed_model = canonical(
        {k: v for k, v in old_model.items() if k not in model_keys}
    ) != canonical({k: v for k, v in new_model.items() if k not in model_keys})
    change = _shape_change(_shape(old_model, root=True), _shape(new_model, root=True))
    required = (
        "major"
        if changed_guarantees or changed_model or change == 2
        else ("minor" if change == 1 else "patch")
    )
    if (required == "major" and new_version[0] == old_version[0]) or (
        required == "minor" and new_version[:2] == old_version[:2]
    ):
        raise ContractError("contract_breaking_change")
    return required


def value_schema(document: dict[str, Any]) -> dict[str, Any]:
    """Compile the value shape of an already validated single-object contract."""
    return _shape(document["schema"][0], root=True)
