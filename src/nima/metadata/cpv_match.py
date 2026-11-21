"""Separate base-code annotations over one explicit unfiltered metadata snapshot."""

import hashlib
import re
from collections import Counter
from dataclasses import asdict
from typing import cast

from nima.identity import MAX_REPORT_BYTES, AssessmentError
from nima.identity.artifacts import encode
from nima.metadata.cpv import CpvEntry, CpvReference
from nima.sources.metadata_extract import MAX_ASSERTIONS, VERSION, MetadataError
from nima.sources.kimdis import InvalidRecord, decode_response

MATCH_VERSION = "cpv-matches-v1"


def _annotation(assertion: dict[str, object], entries: dict[str, CpvEntry]) -> dict[str, object]:
    code = assertion.get("code")
    if (
        assertion.get("status") != "reported"
        or not isinstance(code, str)
        or re.fullmatch("[0-9]{8}-[0-9]", code) is None
    ):
        return {"status": "source_ineligible", "base_code": None, "reference_entry": None}
    base = code[:8]
    if assertion.get("taxonomy_version") not in (None, "2008"):
        return {"status": "version_conflict", "base_code": base, "reference_entry": None}
    entry = entries.get(base)
    return {
        "status": "not_found_in_selected_release" if entry is None else "base_code_match",
        "base_code": base,
        "reference_entry": None if entry is None else asdict(entry),
    }


def _annotations(document: dict[str, object], reference: CpvReference) -> list[dict[str, object]]:
    entries = {entry.code: entry for entry in reference.entries}
    records = document.get("records")
    if not isinstance(records, list) or len(records) > 5000:
        raise MetadataError("reference_metadata")
    annotations: list[dict[str, object]] = []
    assertion_count = 0
    for record_ordinal, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("assertions"), list):
            raise MetadataError("reference_metadata")
        for assertion_ordinal, assertion in enumerate(record["assertions"]):
            assertion_count += 1
            if assertion_count > MAX_ASSERTIONS:
                raise MetadataError("reference_limit")
            if not isinstance(assertion, dict) or not isinstance(assertion.get("dimension"), str):
                raise MetadataError("reference_metadata")
            if assertion["dimension"] == "procurement_cpv":
                annotations.append(
                    {
                        "record_ordinal": record_ordinal,
                        "assertion_ordinal": assertion_ordinal,
                        **_annotation(assertion, entries),
                    }
                )
    return annotations


def match_metadata(raw: bytes, snapshot_sha256: str, reference: CpvReference) -> bytes:
    """Keep original assertions/evidence untouched; no legal or company-sector claim."""
    if (
        not isinstance(snapshot_sha256, str)
        or re.fullmatch("[0-9a-f]{64}", snapshot_sha256) is None
    ):
        raise MetadataError("reference_input")
    if len(raw) > MAX_REPORT_BYTES:
        raise MetadataError("reference_limit")
    if hashlib.sha256(raw).hexdigest() != snapshot_sha256:
        raise MetadataError("reference_selection")
    try:
        document = decode_response(raw, max_bytes=MAX_REPORT_BYTES)
        if (
            document.get("artifact_version") != VERSION
            or document.get("source") != "kimdis"
            or document.get("query") != {"dimension": None, "code": None}
            or encode(document) != raw
        ):
            raise MetadataError("reference_metadata")
        annotations = _annotations(document, reference)
        reference_raw = reference.body()
        reference_document = decode_response(reference_raw, max_bytes=MAX_REPORT_BYTES)
        return encode(
            {
                "artifact_version": MATCH_VERSION,
                "metadata_snapshot_sha256": snapshot_sha256,
                "reference_sha256": hashlib.sha256(reference_raw).hexdigest(),
                "reference": reference_document["reference"],
                "match_scope": "cpv_main_base_code",
                "check_digit_validation": "not_checked",
                "meaning": (
                    "Reported procurement-subject occurrences compared with a selected base-code "
                    "list; "
                    "no source correction, supplier-sector, identity or current-state claim"
                ),
                "metadata": document,
                "coverage": {
                    "cpv_assertion_count": len(annotations),
                    "statuses": dict(
                        sorted(Counter(cast(str, a["status"]) for a in annotations).items())
                    ),
                },
                "annotations": annotations,
            }
        )
    except (InvalidRecord, TypeError, UnicodeError):
        raise MetadataError("reference_metadata") from None
    except AssessmentError:
        raise MetadataError("reference_limit") from None
