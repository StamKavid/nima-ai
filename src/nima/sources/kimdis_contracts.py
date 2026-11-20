"""Nima-owned source/producer boundaries, never government guarantees or repairs."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from nima.contracts.schema import ContractError, canonical, validate_contract, value_schema

if TYPE_CHECKING:
    from nima.sources.kimdis import Contract

NORMALIZER_VERSION = "kimdis-normalized-v1"
type Boundary = Literal["source", "normalized"]


def policy(boundary: Boundary) -> dict[str, str]:
    """Describe existing rules; neither duplicate their calculation nor execute text."""
    common = {"source": "kimdis.contract", "normalizer_version": NORMALIZER_VERSION}
    if boundary == "source":
        return {
            **common,
            "grain": "one_decoded_response_page",
            "decoding": "strict_json_decimal_no_duplicate_or_nonfinite",
            "pagination": "existing_arithmetic_and_cardinality_checks",
            "record_items": "opaque_until_normalized_or_quarantined",
            "unknown_fields": "retained_in_original_bytes_and_source_fingerprint",
            "guarantee": "nima_acceptance_not_government_sla",
        }
    return {
        **common,
        "grain": "one_reported_contract_with_original_evidence",
        "version_key": "source_id_normalizer_source_content_hash",
        "money": "finite_Decimal_in_model_exact_text_in_json",
        "supplier_list": "missing_distinct_from_empty",
        "source_dates": "source_text_not_observation_time",
        "procurement_stage": "contract_not_award_or_payment",
        "bad_output": "stop_page_not_source_quarantine",
    }


@cache
def _compiled(boundary: Boundary) -> Draft202012Validator:
    """Only immutable packaged metadata is cached; never source data or results."""
    document = validate_contract(
        json.loads(files("nima.contracts").joinpath(f"kimdis-{boundary}-v1.odcs.json").read_bytes())
    )
    metadata = {entry["property"]: entry["value"] for entry in document["customProperties"]}
    if (
        document["id"] != f"nima.kimdis-{boundary}"
        or document["version"] != "1.0.1"
        or canonical(metadata["nima.semanticDefinition"]) != canonical(policy(boundary))
    ):
        raise ContractError("ingestion_contract")
    return Draft202012Validator(value_schema(document))


def validate_source(response: dict[str, object]) -> None:
    """Minimum structure only; strict decoding and pagination checks precede this."""
    try:
        _compiled("source").validate(response)
    except (OSError, KeyError, TypeError, ValueError, ValidationError, RecursionError):
        raise ContractError("source_contract") from None


def _decimal(value: object) -> str:
    if not isinstance(value, Decimal):
        raise TypeError("Unsupported normalized value")
    return str(value)


def validate_record(record: Contract, *, expected_digest: str, index: int) -> None:
    """Refuse producer drift without coercing/replacing the original dataclass."""
    try:
        for amount in (record.net_amount, record.gross_amount):
            if amount is not None and (not isinstance(amount, Decimal) or not amount.is_finite()):
                raise ContractError("normalized_contract")
        if record.bidder_count is not None and type(record.bidder_count) is not int:
            raise ContractError("normalized_contract")
        value = json.loads(json.dumps(asdict(record), default=_decimal, allow_nan=False))
        _compiled("normalized").validate(value)
        if value["evidence"] != {
            "response_sha256": expected_digest,
            "json_pointer": f"/content/{index}",
        }:
            raise ContractError("normalized_contract")
    except (
        OSError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        ValidationError,
        RecursionError,
    ):
        raise ContractError("normalized_contract") from None
