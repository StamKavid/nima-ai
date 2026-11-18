"""Ingestion can import schema support without loading consumer/domain layers."""

import subprocess
import sys
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from nima.contracts import contract
from nima.contracts.schema import (
    ContractError,
    check_compatibility,
    validate_contract,
    value_schema,
)


def test_schema_import_does_not_load_semantics_analytics_or_storage() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import nima.contracts.schema; "
            "assert not any(n.startswith(('nima.semantics', 'nima.analytics', 'nima.storage')) "
            "for n in sys.modules)",
        ],
        check=True,
    )


def example(field: dict[str, Any]) -> dict[str, Any]:
    value = contract()
    value["schema"][0]["properties"] = [field]
    return value


def test_nullable_present_is_distinct_from_optional() -> None:
    value = example(
        {
            "name": "value",
            "logicalType": "string",
            "required": False,
            "customProperties": [{"property": "nima.present", "value": True}],
        }
    )
    validator = Draft202012Validator(value_schema(validate_contract(value)))
    validator.validate({"value": None})
    validator.validate({"value": "Ελληνικό κείμενο"})
    with pytest.raises(ValidationError):
        validator.validate({})


def test_opaque_source_items_remain_available_for_quarantine() -> None:
    value = example(
        {
            "name": "content",
            "logicalType": "array",
            "required": True,
            "customProperties": [{"property": "nima.opaqueItems", "value": True}],
        }
    )
    validator = Draft202012Validator(value_schema(validate_contract(value)))
    validator.validate({"content": [None, 1, "bad", {"title": 42}]})
    with pytest.raises(ValidationError):
        validator.validate({"content": {}})


@pytest.mark.parametrize("fault", ["unknown", "false", "duplicate", "not_array", "both"])
def test_custom_profile_flags_must_be_explicit_and_unambiguous(fault: str) -> None:
    field: dict[str, Any] = {
        "name": "content",
        "logicalType": "array",
        "required": True,
        "customProperties": [{"property": "nima.opaqueItems", "value": True}],
    }
    flag = field["customProperties"][0]
    if fault == "unknown":
        flag["property"] = "nima.execute_arbitrary_rule"
    elif fault == "false":
        flag["value"] = False
    elif fault == "duplicate":
        field["customProperties"].append(flag)
    elif fault == "not_array":
        field["logicalType"] = "string"
    else:
        field["items"] = {"logicalType": "object"}
    with pytest.raises(ContractError, match="^analytics_contract$"):
        validate_contract(example(field))


def test_removing_presence_guarantee_requires_a_major_version() -> None:
    import copy

    old = example(
        {
            "name": "value",
            "logicalType": "string",
            "required": False,
            "customProperties": [{"property": "nima.present", "value": True}],
        }
    )
    new = copy.deepcopy(old)
    new["schema"][0]["properties"][0].pop("customProperties")
    new["version"] = "1.1.0"
    with pytest.raises(ContractError, match="^contract_breaking_change$"):
        check_compatibility(old, new)


def test_invalid_declared_regex_fails_as_metadata_before_any_data_check() -> None:
    value = example(
        {
            "name": "value",
            "logicalType": "string",
            "required": True,
            "logicalTypeOptions": {"pattern": "["},
        }
    )
    with pytest.raises(ContractError, match="^analytics_contract$"):
        validate_contract(value)
