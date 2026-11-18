"""Offline ODCS metadata and the bounded Nima readout profile, never a code runner."""

import hashlib
import json
import re
from importlib.resources import files
from typing import Any, cast

from jsonschema import Draft201909Validator, Draft202012Validator
from jsonschema.exceptions import ValidationError

from nima.semantics.participation import definition

SCHEMA_SHA256 = "edb41f33ec46e84780e99872ab2bd67f074959d2bf3e9c9fc54e61f8982b0d93"
CONTRACT_ID = "nima.supplier-buyers-readout"
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
}


class ContractError(ValueError):
    """Fixed failure only; no source data or schema validation details escape."""


def _canonical(value: object) -> str:
    """Keep JSON boolean/number distinctions that Python equality collapses."""
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _shape(element: dict[str, Any], *, root: bool = False) -> dict[str, Any]:
    kind = element.get("logicalType")
    options = element.get("logicalTypeOptions", {})
    if (
        element.keys() - _ELEMENT_KEYS
        or ("quality" in element and not root)
        or kind not in _OPTIONS
        or options.keys() - _OPTIONS[kind]
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
        result["required"] = [field["name"] for field in fields if field.get("required")]
    if kind == "array":
        if "items" not in element:
            raise ContractError("analytics_contract")
        result["items"] = _shape(element["items"])
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
        _canonical(document)
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


def contract() -> dict[str, Any]:
    """Return a new validated copy of the reviewed contract, not generated promises."""
    try:
        return validate_contract(
            json.loads(files(__package__).joinpath("supplier-buyers-v1.odcs.json").read_bytes())
        )
    except (OSError, ValueError):
        raise ContractError("analytics_contract") from None


def validate_output(body: bytes, *, metric: dict[str, object], observation_count: int) -> None:
    """Gate shape and semantic binding; callers must reconcile originals first."""
    try:
        value = contract()
        metadata = {entry["property"]: entry["value"] for entry in value["customProperties"]}
        policy = definition()
        if value["id"] != CONTRACT_ID or _canonical(
            metadata["nima.semanticDefinition"]
        ) != _canonical(policy):
            raise ContractError("analytics_contract")
        result = json.loads(body)
        Draft202012Validator(_shape(value["schema"][0], root=True)).validate(result)
        expected_hash = hashlib.sha256(_canonical(policy).encode()).hexdigest()
        if (
            _canonical(result["metric"]["definition"]) != _canonical(policy)
            or result["metric"]["definition_sha256"] != expected_hash
            or _canonical(result["metric"]["result"]) != _canonical(metric)
            or result["coverage"]["observation_count"] != observation_count
            or len(result["evidence"]) != observation_count
            or len({row["observation_id"] for row in result["evidence"]}) != observation_count
        ):
            raise ContractError("analytics_contract")
    except (OSError, ValidationError, KeyError, TypeError, ValueError, RecursionError):
        raise ContractError("analytics_contract") from None


def _shape_change(previous: dict[str, Any], current: dict[str, Any]) -> int:
    """0 unchanged, 1 additive optional shape, 2 changed consumer guarantee."""
    keys = {"properties", "required", "items"}
    if _canonical({k: v for k, v in previous.items() if k not in keys}) != _canonical(
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
    if _canonical(old) == _canonical(new):
        return "unchanged"
    old_version, new_version = _version(old["version"]), _version(new["version"])
    if new_version <= old_version:
        raise ContractError("contract_version")
    descriptive = {"version", "name", "team", "support", "authoritativeDefinitions", "schema"}
    changed_guarantees = _canonical(
        {k: v for k, v in old.items() if k not in descriptive}
    ) != _canonical({k: v for k, v in new.items() if k not in descriptive})
    old_model, new_model = old["schema"][0], new["schema"][0]
    model_keys = {"properties", "description", "businessName", "authoritativeDefinitions"}
    changed_model = _canonical(
        {k: v for k, v in old_model.items() if k not in model_keys}
    ) != _canonical({k: v for k, v in new_model.items() if k not in model_keys})
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
