"""Offline analytics contract API; schema support remains source-neutral."""

import hashlib
import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from nima.contracts.schema import (
    SCHEMA_SHA256 as SCHEMA_SHA256,
)
from nima.contracts.schema import (
    ContractError as ContractError,
)
from nima.contracts.schema import (
    canonical,
    value_schema,
)
from nima.contracts.schema import (
    check_compatibility as check_compatibility,
)
from nima.contracts.schema import (
    validate_contract as validate_contract,
)

CONTRACT_ID = "nima.supplier-buyers-readout"


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
    from nima.semantics.participation import definition

    try:
        value = contract()
        metadata = {entry["property"]: entry["value"] for entry in value["customProperties"]}
        policy = definition()
        if value["id"] != CONTRACT_ID or canonical(
            metadata["nima.semanticDefinition"]
        ) != canonical(policy):
            raise ContractError("analytics_contract")
        result = json.loads(body)
        Draft202012Validator(value_schema(value)).validate(result)
        expected_hash = hashlib.sha256(canonical(policy).encode()).hexdigest()
        if (
            canonical(result["metric"]["definition"]) != canonical(policy)
            or result["metric"]["definition_sha256"] != expected_hash
            or canonical(result["metric"]["result"]) != canonical(metric)
            or result["coverage"]["observation_count"] != observation_count
            or len(result["evidence"]) != observation_count
            or len({row["observation_id"] for row in result["evidence"]}) != observation_count
        ):
            raise ContractError("analytics_contract")
    except (OSError, ValidationError, KeyError, TypeError, ValueError, RecursionError):
        raise ContractError("analytics_contract") from None
