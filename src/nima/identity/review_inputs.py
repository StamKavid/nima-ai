"""Bounded private codecs; decoded reports still require SQL evidence validation."""

import hashlib
import json
import os
import re
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, cast
from uuid import UUID

from nima.evidence import EvidenceError, artifacts
from nima.identity import (
    MAX_COMPARISON_MENTIONS,
    MAX_REGISTRY_OBSERVATIONS,
    MAX_REPORT_BYTES,
    AssessmentError,
    ComparisonError,
)
from nima.identity.artifacts import encode
from nima.identity.registry_cohort import (
    ComparisonCohort,
    ImportEvidence,
    PartyEvidence,
    RegistryEvidence,
    _fields,
    _when,
)
from nima.identity.registry_policy import RegistryObservation
from nima.identity.registry_report import build_report
from nima.identity.review_types import (
    CONFLICT_CODES,
    MAX_RATIONALE_BYTES,
    MAX_REQUEST_BYTES,
    REQUEST_FORMAT,
    ReviewCandidate,
    ReviewError,
    ReviewReport,
    ReviewRequest,
    ReviewSubject,
)
from nima.ingestion.config import CONNECTOR_VERSION
from nima.projections.worker import PROJECTION_VERSION
from nima.sources.gemi import NORMALIZER_VERSION as GEMI_VERSION
from nima.sources.gemi import registry_number
from nima.storage.gemi import IMPORT_VERSION
from nima.storage.postgres import NORMALIZER_VERSION


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ReviewError("review_input")
        result[key] = value
    return result


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ReviewError("review_input")
    return cast(dict[str, object], value)


def _reject_constant(value: str) -> NoReturn:
    raise ValueError


def _json(body: bytes, limit: int) -> dict[str, object]:
    if len(body) > limit:
        raise ReviewError("review_limit")
    try:
        value: object = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
        return _object(value)
    except (UnicodeError, ValueError, RecursionError):
        raise ReviewError("review_input") from None


def _keys(value: dict[str, object], expected: str) -> None:
    if set(value) != set(expected.split()):
        raise ReviewError("review_input")


def _text(value: object) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise ReviewError("review_input")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ReviewError("review_input") from None
    return value


def _uuid(value: object) -> UUID:
    try:
        return UUID(_text(value))
    except ValueError:
        raise ReviewError("review_input") from None


def _integer(value: object, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReviewError("review_input")
    return value


def _hash(value: object) -> str:
    text = _text(value)
    if re.fullmatch("[0-9a-f]{64}", text) is None:
        raise ReviewError("review_input")
    return text


def _subject(value: object) -> ReviewSubject:
    data = _object(value)
    _keys(
        data,
        "run_id observation_id projection_version source_id normalizer_version "
        "content_sha256 role ordinal",
    )
    source = _text(data["source_id"])
    role = data["role"]
    ordinal = _integer(data["ordinal"], maximum=999)
    if (
        data["projection_version"] != PROJECTION_VERSION
        or data["normalizer_version"] != NORMALIZER_VERSION
        or not source.startswith("kimdis:")
        or source == "kimdis:"
        or role not in ("buyer", "supplier")
        or (role == "buyer" and ordinal != 0)
    ):
        raise ReviewError("review_input")
    return ReviewSubject(
        _uuid(data["run_id"]),
        _integer(data["observation_id"], 1),
        PROJECTION_VERSION,
        source,
        NORMALIZER_VERSION,
        _hash(data["content_sha256"]),
        role,
        ordinal,
    )


def decode_request(request_id: UUID, body: bytes) -> ReviewRequest:
    if not isinstance(request_id, UUID):
        raise ReviewError("review_input")
    data = _json(body, MAX_REQUEST_BYTES)
    operation = data.get("operation")
    if data.get("request_format") != REQUEST_FORMAT or operation not in (
        "accept",
        "reject",
        "revoke",
    ):
        raise ReviewError("review_input")
    fields = "request_format operation subject candidate expected_revision rationale"
    fields += " reverses_event_id" if operation == "revoke" else " report_sha256"
    if operation == "accept":
        fields += " entity_id acknowledged_issues"
    _keys(data, fields)
    candidate = _object(data["candidate"])
    _keys(candidate, "import_id registry_number")
    number = _text(candidate["registry_number"])
    try:
        if registry_number(number) != number:
            raise ValueError
    except ValueError:
        raise ReviewError("review_input") from None
    rationale = _text(data["rationale"])
    if not rationale.strip() or len(rationale.encode()) > MAX_RATIONALE_BYTES:
        raise ReviewError("review_input")
    issues: tuple[str, ...] = ()
    if operation == "accept":
        claims = data["acknowledged_issues"]
        if not isinstance(claims, list) or any(
            not isinstance(item, str) or item not in CONFLICT_CODES for item in claims
        ):
            raise ReviewError("review_input")
        issues = tuple(sorted(cast(list[str], claims)))
        if len(set(issues)) != len(issues):
            raise ReviewError("review_input")
    return ReviewRequest(
        request_id,
        operation,
        _subject(data["subject"]),
        ReviewCandidate(_uuid(candidate["import_id"]), number),
        _integer(data["expected_revision"]),
        rationale,
        _hash(data["report_sha256"]) if operation != "revoke" else None,
        _uuid(data["entity_id"]) if operation == "accept" else None,
        _uuid(data["reverses_event_id"]) if operation == "revoke" else None,
        issues,
    )


def _read(path: Path, limit: int) -> bytes:
    descriptor = None
    try:
        descriptor = artifacts.directory(path.parent, private=True)
        return artifacts.read(descriptor, path.name, limit=limit, private=True)
    except EvidenceError as exc:
        raise ReviewError(
            "review_limit" if exc.reason == "file_limit" else "review_input_io"
        ) from None
    except (OSError, ValueError):
        raise ReviewError("review_input_io") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_request(request_id: UUID, path: Path) -> ReviewRequest:
    return decode_request(request_id, _read(path, MAX_REQUEST_BYTES))


def _rows(value: object, maximum: int, minimum: int = 0) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ReviewError("review_input")
    if len(value) > maximum:
        raise ReviewError("review_limit")
    return [_object(item) for item in value]


def _nullable(value: object) -> str | None:
    return None if value is None else _text(value)


def _coverage(value: object) -> dict[str, object]:
    data = _object(value)
    counts = (
        "checkpoint_next_page",
        "page_count",
        "quarantine_count",
        "observation_count",
        "expected_mentions",
        "unknown_supplier_lists",
        "empty_supplier_lists",
    )
    _keys(
        data,
        " ".join(counts)
        + " reported_total_records reported_total_pages normalizer_version connector_version "
        "stored_run_status collection_completeness",
    )
    if (
        data["normalizer_version"] != NORMALIZER_VERSION
        or data["connector_version"] != CONNECTOR_VERSION
        or data["collection_completeness"] != "not_certified"
    ):
        raise ReviewError("review_input")
    _text(data["stored_run_status"])
    for name in counts:
        _integer(data[name])
    for name in ("reported_total_records", "reported_total_pages"):
        if data[name] is not None:
            _integer(data[name])
    return data


def _import(data: dict[str, object]) -> ImportEvidence:
    if data["import_version"] != IMPORT_VERSION or data["normalizer_version"] != GEMI_VERSION:
        raise ReviewError("review_input")
    profiles = _integer(data["profile_count"], maximum=10)
    missing = _integer(data["not_found_count"], maximum=10)
    responses = _integer(data["response_count"], 1, 30)
    if not 1 <= profiles + missing <= 10 or responses < profiles + missing:
        raise ReviewError("review_input")
    return ImportEvidence(
        _uuid(data["import_id"]),
        IMPORT_VERSION,
        GEMI_VERSION,
        _hash(data["manifest_sha256"]),
        _text(data["source_url"]),
        _text(data["license"]),
        _text(data["publisher"]),
        _when(_text(data["imported_at"])),
        profiles,
        missing,
        responses,
    )


def _registry(data: dict[str, object]) -> RegistryEvidence:
    number = _text(data["registry_number"])
    if registry_number(number) != number:
        raise ReviewError("review_input")
    selected = _uuid(data["import_id"])
    if data["outcome"] == "found":
        fields = _fields(data["fields"], number)
        if (
            data["status"] != 200
            or data["source_id"] != "gemi:" + number
            or data["normalizer_version"] != GEMI_VERSION
        ):
            raise ReviewError("review_input")
        claim = RegistryObservation(
            selected, number, "found", _nullable(fields["reported_afm"].value)
        )
    elif (
        data["outcome"] == "not_found_at_observation"
        and data["status"] == 404
        and data["fields"] == {}
        and data["source_id"] is None
        and data["normalizer_version"] is None
    ):
        fields = MappingProxyType({})
        claim = RegistryObservation(selected, number, "not_found_at_observation", None)
    else:
        raise ReviewError("review_input")
    return RegistryEvidence(
        claim,
        _integer(data["attempt"], 1, 3),
        _integer(data["status"], 200, 404),
        _hash(data["raw_sha256"]),
        _when(_text(data["observed_at"])),
        _nullable(data["source_id"]),
        _nullable(data["normalizer_version"]),
        fields,
    )


def _party(data: dict[str, object], run: UUID) -> PartyEvidence:
    subject = _subject(
        {
            "run_id": str(run),
            "projection_version": PROJECTION_VERSION,
            **{
                key: data[key]
                for key in (
                    "observation_id",
                    "source_id",
                    "normalizer_version",
                    "content_sha256",
                    "role",
                    "ordinal",
                )
            },
        }
    )
    pointer = _text(data["json_pointer"])
    if re.fullmatch("/content/(0|[1-9][0-9]*)", pointer) is None:
        raise ReviewError("review_input")
    return PartyEvidence(
        subject.source_id,
        subject.normalizer_version,
        subject.content_sha256,
        subject.observation_id,
        subject.role,
        subject.ordinal,
        _nullable(data["name"]),
        _nullable(data["tax_id"]),
        _nullable(data["source_key"]),
        _nullable(data["country_code"]),
        _hash(data["raw_sha256"]),
        pointer,
        _when(_text(data["observed_at"])),
        _nullable(data["source_submitted_at"]),
        _nullable(data["source_updated_at"]),
    )


def decode_report(body: bytes) -> ReviewReport:
    data = _json(body, MAX_REPORT_BYTES)
    try:
        if data["projection_version"] != PROJECTION_VERSION:
            raise ReviewError("review_input")
        run = _uuid(data["run_id"])
        imports = tuple(_import(row) for row in _rows(data["registry_imports"], 10, 1))
        registry = tuple(
            _registry(row)
            for row in _rows(data["registry_observations"], MAX_REGISTRY_OBSERVATIONS)
        )
        parties = tuple(
            _party(row, run) for row in _rows(data["occurrences"], MAX_COMPARISON_MENTIONS)
        )
        if len({row.import_id for row in imports}) != len(imports):
            raise ReviewError("review_input")
        if len({(row.observation_id, row.role, row.ordinal) for row in parties}) != len(parties):
            raise ReviewError("review_input")
        if {row.claim.import_id for row in registry} != {row.import_id for row in imports}:
            raise ReviewError("review_input")
        for selected in imports:
            found = sum(
                row.claim.import_id == selected.import_id and row.claim.outcome == "found"
                for row in registry
            )
            missing = sum(
                row.claim.import_id == selected.import_id
                and row.claim.outcome == "not_found_at_observation"
                for row in registry
            )
            if (found, missing) != (selected.profile_count, selected.not_found_count):
                raise ReviewError("review_input")
        cohort = ComparisonCohort(
            run,
            PROJECTION_VERSION,
            MappingProxyType(_coverage(data["coverage"])),
            parties,
            imports,
            registry,
        )
        # Exact roundtrip rejects extra/missing fields and altered derived policy.
        # This is still NOT a SQL proof: a forger can copy internally consistent claims.
        if encode(build_report(cohort)) != body:
            raise ReviewError("review_input")
        return ReviewReport(hashlib.sha256(body).hexdigest(), cohort)
    except (KeyError, ValueError, ComparisonError, AssessmentError, RecursionError):
        raise ReviewError("review_input") from None


def read_report(path: Path, *, expected_sha256: str | None = None) -> ReviewReport:
    body = _read(path, MAX_REPORT_BYTES)
    if expected_sha256 is not None and _hash(expected_sha256) != hashlib.sha256(body).hexdigest():
        raise ReviewError("review_evidence")
    return decode_report(body)
