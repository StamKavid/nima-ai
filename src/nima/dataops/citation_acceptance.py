"""Reconstruct one citation subject before evaluating and privately publishing fitness."""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

import psycopg

from nima.analytics.citation_readout import prepare_citation_readout
from nima.analytics.citation_request import (
    CitationRequest,
    read_citation_request,
    validate_citation_request,
)
from nima.analytics.metric_readout import definition_hash
from nima.analytics.request import RequestError, constant_hook, pairs_hook, uuid_value
from nima.analytics.result import ReadoutError
from nima.contracts import acceptance as policy
from nima.contracts.history import valid_digest
from nima.evidence import EvidenceError, artifacts
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.semantics.citations import MAX_OUTPUT_BYTES, OUTCOMES, CitationResult

FORMAT = "nima-citation-acceptance-v1"
MAX_ACCEPTANCE_BYTES = 64 * 1024
POLICY_SHA256 = "f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06"
_ROOT = (
    "version model request request_sha256 cohort_sha256 quality captures "
    "verified_pages evidence interpretation_limits"
)
_CAPTURE = (
    "collection_complete committed_page_count connector_version normalization_complete "
    "normalized_observations normalizer_version observed_from observed_to quarantined_count query "
    "query_sha256 reported_page_size reported_total_pages reported_total_records run_id source "
    "source_attribution status"
)
_PAGE = (
    "byte_length observed_at page_number quarantined_count raw_sha256 record_count "
    "run_id source source_ids"
)
_EVIDENCE = (
    "content_sha256 field_locations json_pointer normalizer_version observation_id observed_at "
    "page_number raw_sha256 record_index run_id selection source source_id"
)
_MODEL = (
    "model status matching selection lineage relation source_field reported_relation "
    "expected_target_type "
    "kimdis_normalizer diavgeia_normalizers outcomes scope sql_sha256"
)
_CHECKS = (
    "bindings",
    "evidence",
    "keys",
    "membership",
    "page_accounting",
    "capture_completeness",
    "selection",
    "eligibility",
    "comparability",
)
_ERRORS = {
    "citation_input": "acceptance_input",
    "citation_limit": "acceptance_limit",
    "citation_evidence": "acceptance_evidence",
    "citation_database": "acceptance_database",
    "citation_contract": "acceptance_contract",
    "citation_output": "acceptance_output",
}


class CitationAcceptanceError(ValueError):
    """Fixed codes only; no driver details, paths or source values."""

    def __init__(self, reason: str) -> None:
        codes = {
            "acceptance_input",
            "acceptance_limit",
            "acceptance_evidence",
            "acceptance_database",
            "acceptance_contract",
            "acceptance_output",
            "acceptance_interrupted",
        }
        super().__init__(reason if reason in codes else "acceptance_contract")


@dataclass(frozen=True)
class PreparedCitationAcceptance:
    body: bytes = field(repr=False)
    assessment: policy.Assessment
    subject_sha256: str


@dataclass(frozen=True)
class CitationAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str


def _path(value: Path) -> bool:
    return (
        isinstance(value, Path)
        and value.is_absolute()
        and "\x00" not in str(value)
        and not str(value).startswith("//")
        and not {"..", ".git"}.intersection(value.parts)
    )


def _subject(path: Path) -> bytes:
    fd = -1
    try:
        fd = artifacts.directory(path.parent, private=True)
        info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        if info.st_size > MAX_OUTPUT_BYTES:
            raise CitationAcceptanceError("acceptance_limit")
        if info.st_nlink != 1:
            raise CitationAcceptanceError("acceptance_evidence")
        body = artifacts.read(fd, path.name, limit=MAX_OUTPUT_BYTES, private=True)
        if (
            os.stat(path.name, dir_fd=fd, follow_symlinks=False).st_nlink != 1
            or hashlib.sha256(body).hexdigest() != path.stem
        ):
            raise CitationAcceptanceError("acceptance_evidence")
        return body
    except (EvidenceError, OSError):
        raise CitationAcceptanceError("acceptance_evidence") from None
    finally:
        if fd >= 0:
            os.close(fd)


def _object(value: object, fields: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise CitationAcceptanceError("acceptance_contract")
    return cast(dict[str, object], value)


def _rows(value: object, fields: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise CitationAcceptanceError("acceptance_contract")
    return tuple(_object(row, fields) for row in value)


def _number(value: object) -> int:
    if type(value) is not int or value < 0:
        raise CitationAcceptanceError("acceptance_contract")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CitationAcceptanceError("acceptance_contract")
    return value


def _run(row: dict[str, object], request: CitationRequest) -> str:
    run = uuid_value(row["run_id"])
    source = "kimdis" if run in request.kimdis_run_ids else "diavgeia"
    if run not in request.run_ids or row["source"] != source:
        raise CitationAcceptanceError("acceptance_contract")
    return str(run)


def _frame_metadata(
    pages: tuple[dict[str, object], ...],
    evidence: tuple[dict[str, object], ...],
    request: CitationRequest,
) -> None:
    for row in (*pages, *evidence):
        _run(row, request)
        _text(row["observed_at"])
        _number(row["page_number"])
        if not valid_digest(row["raw_sha256"]):
            raise CitationAcceptanceError("acceptance_contract")
    page_ids = set()
    for page in pages:
        key = (page["run_id"], page["page_number"])
        if key in page_ids or not isinstance(page["source_ids"], list):
            raise CitationAcceptanceError("acceptance_contract")
        page_ids.add(key)
        for value in page["source_ids"]:
            _text(value)
        for name in ("record_count", "quarantined_count", "byte_length"):
            _number(page[name])
    ids = set()
    for row in evidence:
        value = _number(row["observation_id"])
        if (
            not value
            or value in ids
            or not isinstance(row["field_locations"], dict)
            or not valid_digest(row["content_sha256"])
            or row["selection"]
            not in {
                "after_cutoff",
                "earlier_content",
                "ambiguous_candidate",
                "selected_content_observation",
            }
        ):
            raise CitationAcceptanceError("acceptance_contract")
        ids.add(value)
        _number(row["record_index"])
        for name in ("source_id", "normalizer_version", "json_pointer"):
            _text(row[name])


def _facts(
    request: CitationRequest, body: bytes, result: CitationResult
) -> tuple[policy.DatasetFacts, dict[str, object]]:
    document = _object(
        json.loads(body, object_pairs_hook=pairs_hook, parse_constant=constant_hook), _ROOT
    )
    model = _object(document["model"], "definition definition_sha256 result")
    definition = _object(model["definition"], _MODEL)
    for name in _MODEL.split():
        if name in {"diavgeia_normalizers", "outcomes"}:
            items = definition[name]
            if not isinstance(items, list):
                raise CitationAcceptanceError("acceptance_contract")
            for item in items:
                _text(item)
        else:
            _text(definition[name])
    if not isinstance(document["interpretation_limits"], list):
        raise CitationAcceptanceError("acceptance_contract")
    for item in document["interpretation_limits"]:
        _text(item)
    captures = _rows(document["captures"], _CAPTURE)
    pages = _rows(document["verified_pages"], _PAGE)
    evidence = _rows(document["evidence"], _EVIDENCE)
    _frame_metadata(pages, evidence, request)
    quality = _object(
        document["quality"],
        "assertion coverage legal_identity metric_eligibility normalized_records "
        "raw_bytes source_current",
    )
    if (
        document["version"] != "nima-source-citations-v1"
        or document["request"] != request.semantic_payload()
        or document["request_sha256"] != request.request_sha256
        or not valid_digest(document["cohort_sha256"])
        or definition["model"] != "explicit_procurement_citations.v1"
        or definition["status"] not in {"draft", "reviewed", "certified"}
        or not valid_digest(definition["sql_sha256"])
        or definition_hash(definition) != model["definition_sha256"]
        or not isinstance(result, CitationResult)
        or result.payload() != model["result"]
        or set(result.outcome_counts) != set(OUTCOMES)
    ):
        raise CitationAcceptanceError("acceptance_contract")
    ids = []
    bindings = []
    for capture in captures:
        run = uuid_value(_run(capture, request))
        expected = "kimdis" if run in request.kimdis_run_ids else "diavgeia"
        if (
            run not in request.run_ids
            or capture["source"] != expected
            or type(capture["collection_complete"]) is not bool
            or type(capture["normalization_complete"]) is not bool
        ):
            raise CitationAcceptanceError("acceptance_contract")
        for name in ("committed_page_count", "normalized_observations", "quarantined_count"):
            _number(capture[name])
        for name in ("reported_page_size", "reported_total_pages", "reported_total_records"):
            if capture[name] is not None:
                _number(capture[name])
        for name in ("observed_from", "observed_to"):
            if capture[name] is not None:
                _text(capture[name])
        attribution = _object(capture["source_attribution"], "documentation_url license statements")
        if (
            not isinstance(capture["query"], dict)
            or not valid_digest(capture["query_sha256"])
            or not isinstance(attribution["statements"], list)
        ):
            raise CitationAcceptanceError("acceptance_contract")
        for value in attribution["statements"]:
            _text(value)
        for name in ("documentation_url", "license"):
            _text(attribution[name])
        _text(capture["status"])
        ids.append(run)
        bindings.append(
            policy.RunBinding(
                expected,
                str(run),
                _text(capture["connector_version"]),
                _text(capture["normalizer_version"]),
            )
        )
    if sorted(ids) != list(request.run_ids):
        raise CitationAcceptanceError("acceptance_contract")
    quarantined = sum(_number(c["quarantined_count"]) for c in captures)
    complete = all(c["collection_complete"] and c["normalization_complete"] for c in captures)
    expected_quality = {
        "assertion": "reported_citation_only",
        "legal_identity": "not_established",
        "metric_eligibility": "not_assessed_v1_08",
        "source_current": "not_established",
        "normalized_records": "reconciled_with_sql_and_installed_source_adapter",
        "coverage": "selected_complete_captures"
        if complete and not quarantined
        else "partial_capture",
        "raw_bytes": "verified_against_archived_bytes" if pages else "no_admitted_pages",
    }
    if quality != expected_quality:
        raise CitationAcceptanceError("acceptance_contract")
    selected = [s.versions[0] for s in result.sources if len(s.versions) == 1]
    counts = (
        policy.Count("observations", "observation", len(evidence)),
        policy.Count("pages", "page", len(pages)),
        policy.Count(
            "page_records", "reported_record", sum(_number(p["record_count"]) for p in pages)
        ),
        policy.Count("quarantined", "quarantined_record", quarantined),
        policy.Count(
            "selected_records", "source_record", result.records - len(result.source_ambiguous_ids)
        ),
        policy.Count("ambiguous_records", "source_record", len(result.source_ambiguous_ids)),
        policy.Count("unknown_reference_lists", "source_record", len(result.unknown_reference_ids)),
        policy.Count(
            "unresolved_citations", "citation", _number(result.outcome_counts["unresolved"])
        ),
        policy.Count(
            "ambiguous_targets", "citation", _number(result.outcome_counts["target_ambiguous"])
        ),
        policy.Count(
            "unknown_target_types",
            "citation",
            _number(result.outcome_counts["target_type_unknown"]),
        ),
        policy.Count(
            "mismatched_target_types",
            "citation",
            _number(result.outcome_counts["target_type_mismatch"]),
        ),
        policy.Count(
            "unknown_cancellations", "source_record", sum(v.cancelled is None for v in selected)
        ),
        policy.Count(
            "cancelled_records", "source_record", sum(v.cancelled is True for v in selected)
        ),
        policy.Count(
            "revoked_targets",
            "citation",
            sum(
                len(e.target_versions) == 1 and e.target_versions[0].decision_status == "REVOKED"
                for e in result.edges
            ),
        ),
    )
    completeness = (
        ("failed", "quarantined_records")
        if quarantined
        else (("passed", "ok") if complete else ("failed", "incomplete_capture"))
    )
    checks = tuple(
        policy.CheckResult(c, *completeness)
        if c == "capture_completeness"
        else policy.CheckResult(c, "not_applicable", "not_required_for_use")
        if c == "comparability"
        else policy.CheckResult(c, "passed", "ok")
        for c in _CHECKS
    )
    facts = policy.DatasetFacts(
        policy.DatasetBinding(
            "citations",
            request.request_sha256,
            cast(str, document["cohort_sha256"]),
            request.observation_cutoff,
            tuple(sorted(bindings, key=lambda r: r.run_id)),
            model["definition_sha256"],
            cast(str, definition["sql_sha256"]),
        ),
        result.status,
        checks,
        counts,
    )
    return facts, definition


def _assessment_shape(value: policy.Assessment, metadata: dict[str, object]) -> None:
    failures = cast(dict[str, tuple[str, ...]], metadata["failure_reasons"])
    unassessed = cast(tuple[str, ...], metadata["unassessed_reasons"])
    for check in value.checks:
        reasons = {
            "passed": (metadata["successful_check_reason"],),
            "failed": failures[check.check_id],
            "not_assessed": unassessed,
            "not_applicable": (metadata["not_applicable_reason"],),
        }
        if check.status not in reasons or check.reason not in reasons[check.status]:
            raise CitationAcceptanceError("acceptance_contract")
    allowed = set(cast(dict[str, tuple[str, ...]], metadata["limiting_counts"])["citations"])
    allowed.update({"partial_capture", "capture_completeness_unknown"})
    if (
        not isinstance(value.limitations, tuple)
        or set(value.limitations) - allowed
        or value.limitations != tuple(sorted(set(value.limitations)))
        or (value.status != "limited" and value.limitations)
    ):
        raise CitationAcceptanceError("acceptance_contract")


def _compose(
    request: CitationRequest, body: bytes, result: CitationResult, subject: str
) -> PreparedCitationAcceptance:
    try:
        metadata = policy.definition()
        if hashlib.sha256(encode(metadata)).hexdigest() != POLICY_SHA256:
            raise CitationAcceptanceError("acceptance_contract")
        facts, model = _facts(request, body, result)
        assessment = policy.evaluate(facts)
        if (
            not isinstance(assessment, policy.Assessment)
            or assessment.policy_sha256 != POLICY_SHA256
            or assessment.policy_id != metadata["id"]
            or assessment.policy_version != metadata["version"]
            or assessment.use != "citations"
            or assessment.request_sha256 != facts.binding.request_sha256
            or assessment.cohort_sha256 != facts.binding.cohort_sha256
            or assessment.definition_sha256 != facts.binding.definition_sha256
            or assessment.sql_sha256 != facts.binding.sql_sha256
            or assessment.provider_status != result.status
            or not valid_digest(assessment.facts_sha256)
            or assessment.status not in {"ready", "limited", "blocked", "not_assessed"}
            or assessment.amount_eligibility != "not_applicable"
            or assessment.counts != tuple(sorted(facts.counts, key=lambda c: c.name))
            or assessment.required_checks
            != tuple(cast(dict[str, list[str]], metadata["required_checks"])["citations"])
            or tuple(c.check_id for c in assessment.checks) != _CHECKS
        ):
            raise CitationAcceptanceError("acceptance_contract")
        _assessment_shape(assessment, metadata)
        output = {
            "version": FORMAT,
            "subject": {
                "version": "nima-source-citations-v1",
                "artifact_sha256": subject,
                "request": request.semantic_payload(),
                "cohort_sha256": facts.binding.cohort_sha256,
                "run_profiles": [asdict(r) for r in facts.binding.runs],
                "evidence_scope": "all_admitted_pages",
                "raw_bytes": "verified_against_archived_bytes"
                if any(c.name == "pages" and c.value for c in facts.counts)
                else "no_admitted_pages",
                "model": {
                    "id": model["model"],
                    "status": model["status"],
                    "definition_sha256": facts.binding.definition_sha256,
                    "sql_sha256": facts.binding.sql_sha256,
                },
            },
            "policy": {"definition": metadata, "definition_sha256": POLICY_SHA256},
            "assessment": asdict(assessment),
            "interpretation_limits": [
                "Data fitness for citation inspection only; "
                "no numeric-use approval or certification.",
                "A reported citation establishes no legal identity, validity, payment "
                "or economic equivalence.",
                "Verification concerns inspected bytes and a captured cohort, "
                "not future availability or source truth.",
            ],
        }
        return PreparedCitationAcceptance(
            encode(output, limit=MAX_ACCEPTANCE_BYTES), assessment, subject
        )
    except CitationAcceptanceError:
        raise
    except AssessmentError:
        raise CitationAcceptanceError("acceptance_limit") from None
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError):
        raise CitationAcceptanceError("acceptance_contract") from None


def prepare_citation_acceptance(
    dsn: str, request: CitationRequest, report: Path
) -> PreparedCitationAcceptance:
    """One reconstruction per call; a previous sidecar is never used as a cached pass."""
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not _path(report)
        or report.suffix != ".json"
        or not valid_digest(report.stem)
    ):
        raise CitationAcceptanceError("acceptance_input")
    try:
        validate_citation_request(request)
        original = _subject(report)
        fresh, result = prepare_citation_readout(dsn, request)
    except RequestError as error:
        raise CitationAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    except ReadoutError as error:
        raise CitationAcceptanceError(_ERRORS.get(error.reason, "acceptance_contract")) from None
    except psycopg.Error:
        raise CitationAcceptanceError("acceptance_database") from None
    if not isinstance(fresh, bytes):
        raise CitationAcceptanceError("acceptance_contract")
    if len(fresh) > MAX_OUTPUT_BYTES:
        raise CitationAcceptanceError("acceptance_limit")
    if original != fresh:
        raise CitationAcceptanceError("acceptance_evidence")
    return _compose(request, fresh, result, report.stem)


def export_citation_acceptance(
    dsn: str, request_file: Path, report: Path, output_directory: Path
) -> CitationAcceptanceExport:
    if not _path(output_directory):
        raise CitationAcceptanceError("acceptance_input")
    try:
        request = read_citation_request(request_file)
    except RequestError as error:
        raise CitationAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    prepared = prepare_citation_acceptance(dsn, request, report)
    try:
        digest = publish(output_directory, prepared.body)
    except (OSError, AssessmentError):
        raise CitationAcceptanceError("acceptance_output") from None
    return CitationAcceptanceExport(
        digest, prepared.subject_sha256, prepared.assessment.status, POLICY_SHA256
    )
