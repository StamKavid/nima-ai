"""Consumer promises, official-format conformance and conservative evolution."""

import copy
import json
import socket
from importlib.resources import files
from typing import Any

import pytest
from jsonschema import Draft201909Validator

from nima.contracts import (
    ContractError,
    check_compatibility,
    contract,
    validate_contract,
    validate_output,
)
from nima.semantics.participation import definition


def test_reviewed_contract_is_official_odcs_and_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Contract validation must not resolve any network reference")

    monkeypatch.setattr(socket, "socket", forbidden)
    value = contract()
    schema = json.loads(files("nima.contracts").joinpath("odcs-3.2.0.json").read_bytes())
    Draft201909Validator.check_schema(schema)
    Draft201909Validator(schema).validate(value)
    assert value["status"] == "draft"
    assert value["apiVersion"] == "v3.2.0" and value["version"] == "1.0.0"
    properties = {p["property"]: p["value"] for p in value["customProperties"]}
    assert properties["nima.semanticDefinition"] == definition()
    assert not value.get("slaProperties")  # No government or operator SLA invented.
    assert validate_contract(value) == value


@pytest.mark.parametrize("fault", ["kind", "apiVersion", "version", "duplicate", "profile"])
def test_bad_metadata_or_unsupported_profile_fails_closed(fault: str) -> None:
    value = contract()
    if fault in {"kind", "apiVersion", "version"}:
        value[fault] = "private-sentinel"
    elif fault == "duplicate":
        value["schema"][0]["properties"].append(value["schema"][0]["properties"][0])
    else:
        value["schema"][0]["properties"][0]["logicalType"] = "timestamp"
    with pytest.raises(ContractError, match="^analytics_contract$"):
        validate_contract(value)


def changed() -> tuple[dict[str, Any], dict[str, Any]]:
    previous = contract()
    return previous, copy.deepcopy(previous)


def test_unchanged_and_description_patch_are_compatible() -> None:
    old, new = changed()
    assert check_compatibility(old, new) == "unchanged"
    new["name"] += " documentation"
    new["version"] = "1.0.1"
    assert check_compatibility(old, new) == "patch"


def test_optional_addition_requires_minor_not_patch() -> None:
    old, new = changed()
    new["schema"][0]["properties"].append(
        {"name": "optional_annotation", "logicalType": "string", "required": False}
    )
    new["version"] = "1.0.1"
    with pytest.raises(ContractError, match="^contract_breaking_change$"):
        check_compatibility(old, new)
    new["version"] = "1.1.0"
    assert check_compatibility(old, new) == "minor"


@pytest.mark.parametrize(
    "fault", ["remove", "type", "nullability", "required_addition", "semantic", "terms", "enum"]
)
def test_changed_consumer_guarantees_need_major(fault: str) -> None:
    old, new = changed()
    fields = new["schema"][0]["properties"]
    if fault == "remove":
        fields.pop()
    elif fault == "type":
        fields[0]["logicalType"] = "integer"
        fields[0].pop("enum", None)
    elif fault == "nullability":
        fields[0]["required"] = False
    elif fault == "required_addition":
        fields.append({"name": "new_required", "logicalType": "string", "required": True})
    elif fault == "semantic":
        new["customProperties"][0]["value"]["revision"] = "supplier_filter_before_revision"
    elif fault == "terms":
        new["description"]["limitations"] += " New restriction."
    else:
        fields[0]["enum"] = [{"value": "different-output"}]
    new["version"] = "1.1.0"
    with pytest.raises(ContractError, match="^contract_breaking_change$"):
        check_compatibility(old, new)
    new["version"] = "2.0.0"
    assert check_compatibility(old, new) == "major"


@pytest.mark.parametrize("version", ["1.0.0", "0.9.0", "1.0", "01.0.1"])
def test_edits_cannot_reuse_or_downgrade_version(version: str) -> None:
    old, new = changed()
    new["name"] += " changed"
    new["version"] = version
    with pytest.raises(ContractError):
        check_compatibility(old, new)


def test_contract_identity_cannot_change_during_evolution() -> None:
    old, new = changed()
    new["id"] = "unrelated-product"
    new["version"] = "2.0.0"
    with pytest.raises(ContractError, match="^contract_identity$"):
        check_compatibility(old, new)


def test_semantic_drift_is_rejected_before_any_output_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = contract()
    value["customProperties"][0]["value"]["revision"] = "supplier_filter_before_revision"
    monkeypatch.setattr("nima.contracts.contract", lambda: value)
    with pytest.raises(ContractError, match="^analytics_contract$"):
        validate_output(b"{}")
