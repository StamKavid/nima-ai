"""U1 fitness over one fresh verified readout; no source requests or journal writes."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

import psycopg

from nima.analytics.export import PreparedReadout, prepare_readout
from nima.analytics.metric_readout import definition_hash
from nima.analytics.request import (
    ReadoutRequest,
    RequestError,
    constant_hook,
    decode_request,
    pairs_hook,
    read_request,
)
from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.analytics.snapshot import MAX_INPUT_BYTES, ReadoutSnapshot
from nima.contracts import acceptance as policy
from nima.contracts.history import valid_digest
from nima.dataops.acceptance_files import AcceptanceError, read_subject, valid_path
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.semantics.participation import MetricResult

FORMAT = "nima-participation-acceptance-v1"
MAX_ACCEPTANCE_BYTES = 64 * 1024
POLICY_SHA256 = "f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06"
_ROOT = (
    "version source metric request request_sha256 snapshot_sha256 quality "
    "interpretation_limits coverage evidence"
)
_DEFINITION = (
    "metric status source connector normalizer projection country "
    "country_aliases trim tax_id buyer_key revision grain cancellation identity "
    "sql_sha256"
)
_RUN = (
    "run_id query connector_version normalizer_version status managed next_page "
    "total_records total_pages page_size quarantine_count"
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
    "analytics_input": "acceptance_input",
    "analytics_limit": "acceptance_limit",
    "analytics_archive": "acceptance_evidence",
    "analytics_coverage": "acceptance_evidence",
    "analytics_projection": "acceptance_evidence",
    "analytics_evidence": "acceptance_evidence",
    "analytics_role": "acceptance_database",
    "analytics_schema": "acceptance_database",
    "analytics_database": "acceptance_database",
    "analytics_version": "acceptance_contract",
    "analytics_metric": "acceptance_contract",
    "analytics_contract": "acceptance_contract",
    "analytics_output": "acceptance_output",
}


class ParticipationAcceptanceError(AcceptanceError):
    """Fixed closed reasons; supplier selections never enter terminal errors."""


@dataclass(frozen=True)
class PreparedParticipationAcceptance:
    body: bytes = field(repr=False)
    assessment: policy.Assessment
    subject_sha256: str


@dataclass(frozen=True)
class ParticipationAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str


def _object(value: object, fields: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ParticipationAcceptanceError("acceptance_contract")
    return cast(dict[str, object], value)


def _load(body: bytes | str) -> object:
    return json.loads(body, object_pairs_hook=pairs_hook, parse_constant=constant_hook)


def _number(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ParticipationAcceptanceError("acceptance_contract")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ParticipationAcceptanceError("acceptance_contract")
    return value


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ParticipationAcceptanceError("acceptance_contract")
    return cast(list[dict[str, object]], value)


def _facts(
    request: ReadoutRequest, prepared: PreparedReadout
) -> tuple[policy.DatasetFacts, dict[str, object]]:
    snap = prepared.snapshot
    if (
        not isinstance(snap, ReadoutSnapshot)
        or not isinstance(snap.document_json, str)
        or not isinstance(snap.metric, MetricResult)
    ):
        raise ParticipationAcceptanceError("acceptance_contract")
    if len(snap.document_json.encode()) > MAX_INPUT_BYTES:
        raise ParticipationAcceptanceError("acceptance_limit")
    document = _object(_load(snap.document_json), "runs pages records")
    body = _object(_load(prepared.body), _ROOT)
    metric = _object(body["metric"], "definition definition_sha256 result")
    definition = _object(metric["definition"], _DEFINITION)
    for name in _DEFINITION.split():
        value = definition[name]
        if name == "country_aliases":
            if not isinstance(value, list):
                raise ParticipationAcceptanceError("acceptance_contract")
            for alias in value:
                _text(alias)
        else:
            _text(value)
    coverage = _object(
        body["coverage"],
        "runs pages observation_count source_record_count version_count raw_object_count "
        "verified_raw_bytes first_page_observed_at last_page_observed_at",
    )
    runs, pages, records = (
        _rows(document["runs"]),
        _rows(document["pages"]),
        _rows(document["records"]),
    )
    evidence = _rows(body["evidence"])
    result = snap.metric
    if (
        body["version"] != "nima-supplier-buyers-v1"
        or body["source"] != "kimdis.contract"
        or body["request"] != request.semantic_payload()
        or body["request_sha256"] != request.request_sha256
        or not valid_digest(snap.input_sha256)
        or body["snapshot_sha256"] != snap.input_sha256
        or definition["metric"] != "captured_contract_record_count.v1"
        or definition["source"] != "kimdis.contract"
        or definition["status"] not in {"draft", "reviewed", "certified"}
        or not valid_digest(definition["sql_sha256"])
        or definition_hash(definition) != metric["definition_sha256"]
        or encode(metric["result"]) != encode(result.payload())
        or encode(coverage["runs"]) != encode(runs)
        or _number(coverage["observation_count"]) != len(snap.observations)
        or len(records) != len(snap.observations)
        or len(evidence) != len(records)
        or result.status
        not in {
            "empty_capture",
            "no_observations_before_cutoff",
            "observed_participation",
            "selection_unresolved",
            "no_observed_participation",
        }
    ):
        raise ParticipationAcceptanceError("acceptance_contract")
    expected_quality = {
        "raw_bytes": "verified_against_archived_bytes",
        "projection": "reconciled_against_archived_records",
        "identity": "reported_identifier_only",
        "coverage": "selected_complete_runs_only",
        "source_current": "not_established",
        "legal_identity": "not_verified",
        "lineage": "record_to_original_not_field_level",
    }
    if body["quality"] != expected_quality or not isinstance(body["interpretation_limits"], list):
        raise ParticipationAcceptanceError("acceptance_contract")
    for item in body["interpretation_limits"]:
        _text(item)
    page_fields = [
        "run_id",
        "page_number",
        "raw_sha256",
        "byte_length",
        "observed_at",
        "record_count",
    ]
    page_view = [{name: row[name] for name in page_fields} for row in pages]
    if encode(_rows(coverage["pages"])) != encode(page_view):
        raise ParticipationAcceptanceError("acceptance_contract")
    observation_ids = tuple(_number(o.observation_id) for o in snap.observations)
    if (
        not all(observation_ids)
        or len(observation_ids) != len(set(observation_ids))
        or tuple(_number(row["observation_id"]) for row in records) != observation_ids
        or tuple(_number(row["observation_id"]) for row in evidence) != observation_ids
    ):
        raise ParticipationAcceptanceError("acceptance_contract")
    bindings = []
    for row in runs:
        run = _object(row, _RUN)
        if (
            run["managed"] is not True
            or run["status"] != "complete"
            or not isinstance(run["query"], dict)
        ):
            raise ParticipationAcceptanceError("acceptance_contract")
        for name in ("next_page", "total_records", "total_pages", "page_size", "quarantine_count"):
            _number(run[name])
        bindings.append(
            policy.RunBinding(
                "kimdis",
                _text(run["run_id"]),
                _text(run["connector_version"]),
                _text(run["normalizer_version"]),
            )
        )
    if [r.run_id for r in bindings] != [str(r) for r in request.run_ids]:
        raise ParticipationAcceptanceError("acceptance_contract")
    for name in ("source_record_count", "version_count", "raw_object_count", "verified_raw_bytes"):
        _number(coverage[name])
    for name in ("first_page_observed_at", "last_page_observed_at"):
        _text(coverage[name])
    ids = []
    for record in result.records:
        ids.append(_text(record.source_id))
        if any(
            type(v) is not bool
            for v in (record.ambiguous, record.unknown_suppliers, record.unassessed)
        ):
            raise ParticipationAcceptanceError("acceptance_contract")
    if len(ids) != len(set(ids)) or result.ambiguous_source_ids != tuple(
        r.source_id for r in result.records if r.ambiguous
    ):
        raise ParticipationAcceptanceError("acceptance_contract")
    selected = tuple(r for r in result.records if not r.ambiguous)
    counts = (
        policy.Count("observations", "observation", len(snap.observations)),
        policy.Count("pages", "page", len(pages)),
        policy.Count(
            "page_records", "reported_record", sum(_number(p["record_count"]) for p in pages)
        ),
        policy.Count(
            "quarantined", "quarantined_record", sum(_number(r["quarantine_count"]) for r in runs)
        ),
        policy.Count("selected_records", "source_record", len(selected)),
        policy.Count("ambiguous_records", "source_record", len(result.ambiguous_source_ids)),
        policy.Count(
            "unknown_suppliers",
            "source_record",
            sum(r.unknown_suppliers or r.unassessed for r in selected),
        ),
        policy.Count("unassigned_buyers", "source_record", len(result.unassigned_source_ids)),
        policy.Count(
            "invalid_supplier_occurrences",
            "supplier_occurrence",
            _number(result.invalid_supplier_count),
        ),
        policy.Count(
            "unknown_cancellations", "source_record", _number(result.unknown_cancellation_count)
        ),
        policy.Count("cancelled_records", "source_record", _number(result.cancelled_count)),
    )
    checks = tuple(
        policy.CheckResult(c, "not_applicable", "not_required_for_use")
        if c == "comparability"
        else policy.CheckResult(c, "passed", "ok")
        for c in _CHECKS
    )
    facts = policy.DatasetFacts(
        policy.DatasetBinding(
            "U1",
            request.request_sha256,
            snap.input_sha256,
            request.observation_cutoff,
            tuple(bindings),
            metric["definition_sha256"],
            cast(str, definition["sql_sha256"]),
        ),
        result.status,
        checks,
        counts,
    )
    return facts, definition


def _compose(
    request: ReadoutRequest, prepared: PreparedReadout, subject: str
) -> PreparedParticipationAcceptance:
    try:
        metadata = policy.definition()
        if hashlib.sha256(encode(metadata)).hexdigest() != POLICY_SHA256:
            raise ParticipationAcceptanceError("acceptance_contract")
        facts, definition = _facts(request, prepared)
        assessment = policy.evaluate(facts)
        if (
            not isinstance(assessment, policy.Assessment)
            or assessment.policy_sha256 != POLICY_SHA256
            or assessment.policy_id != metadata["id"]
            or assessment.policy_version != metadata["version"]
            or assessment.use != "U1"
            or assessment.request_sha256 != facts.binding.request_sha256
            or assessment.cohort_sha256 != facts.binding.cohort_sha256
            or assessment.definition_sha256 != facts.binding.definition_sha256
            or assessment.sql_sha256 != facts.binding.sql_sha256
            or assessment.provider_status != facts.provider_status
            or not valid_digest(assessment.facts_sha256)
            or assessment.status not in {"ready", "limited", "blocked", "not_assessed"}
            or assessment.amount_eligibility != "not_applicable"
            or assessment.counts != tuple(sorted(facts.counts, key=lambda c: c.name))
            or assessment.required_checks
            != tuple(cast(dict[str, list[str]], metadata["required_checks"])["U1"])
            or tuple(c.check_id for c in assessment.checks) != _CHECKS
        ):
            raise ParticipationAcceptanceError("acceptance_contract")
        failures = cast(dict[str, tuple[str, ...]], metadata["failure_reasons"])
        for check in assessment.checks:
            reasons = {
                "passed": (metadata["successful_check_reason"],),
                "failed": failures[check.check_id],
                "not_assessed": cast(tuple[str, ...], metadata["unassessed_reasons"]),
                "not_applicable": (metadata["not_applicable_reason"],),
            }
            if check.status not in reasons or check.reason not in reasons[check.status]:
                raise ParticipationAcceptanceError("acceptance_contract")
        allowed = set(cast(dict[str, tuple[str, ...]], metadata["limiting_counts"])["U1"])
        if (
            not isinstance(assessment.limitations, tuple)
            or set(assessment.limitations) - allowed
            or assessment.limitations != tuple(sorted(set(assessment.limitations)))
            or (assessment.status != "limited" and assessment.limitations)
        ):
            raise ParticipationAcceptanceError("acceptance_contract")
        output = {
            "version": FORMAT,
            "subject": {
                "version": "nima-supplier-buyers-v1",
                "artifact_sha256": subject,
                "request_sha256": request.request_sha256,
                "snapshot_sha256": facts.binding.cohort_sha256,
                "observation_cutoff": request.observation_cutoff.isoformat(),
                "run_profiles": [asdict(r) for r in facts.binding.runs],
                "evidence_scope": "all_admitted_pages",
                "metric": {
                    "id": definition["metric"],
                    "status": definition["status"],
                    "definition_sha256": facts.binding.definition_sha256,
                    "sql_sha256": facts.binding.sql_sha256,
                },
            },
            "policy": {"definition": metadata, "definition_sha256": POLICY_SHA256},
            "assessment": asdict(assessment),
            "interpretation_limits": [
                "Data fitness for captured supplier-buyer records only; no metric certification.",
                "Provider status remains authoritative for unresolved or empty results; "
                "no market-absence claim.",
                "Reported identifiers establish no legal identity or paid spending; "
                "verification concerns inspected evidence only.",
            ],
        }
        return PreparedParticipationAcceptance(
            encode(output, limit=MAX_ACCEPTANCE_BYTES), assessment, subject
        )
    except ParticipationAcceptanceError:
        raise
    except AssessmentError:
        raise ParticipationAcceptanceError("acceptance_limit") from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
        raise ParticipationAcceptanceError("acceptance_contract") from None


def prepare_participation_acceptance(
    dsn: str, request: ReadoutRequest, report: Path
) -> PreparedParticipationAcceptance:
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not valid_path(report)
        or report.suffix != ".json"
        or not valid_digest(report.stem)
    ):
        raise ParticipationAcceptanceError("acceptance_input")
    try:
        if (
            not isinstance(request, ReadoutRequest)
            or decode_request(
                encode(
                    {
                        **request.semantic_payload(),
                        "archive_bindings": [
                            {"run_id": str(b.run_id), "root": str(b.root)}
                            for b in request.archive_bindings
                        ],
                    }
                )
            )
            != request
        ):
            raise ParticipationAcceptanceError("acceptance_input")
    except RequestError as error:
        raise ParticipationAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    except (ValueError, TypeError, AttributeError):
        raise ParticipationAcceptanceError("acceptance_input") from None
    try:
        original = read_subject(report, limit=MAX_RESULT_BYTES)
        fresh = prepare_readout(dsn, request)
    except AcceptanceError as error:
        raise ParticipationAcceptanceError(str(error)) from None
    except ReadoutError as error:
        raise ParticipationAcceptanceError(
            _ERRORS.get(error.reason, "acceptance_contract")
        ) from None
    except psycopg.Error:
        raise ParticipationAcceptanceError("acceptance_database") from None
    if not isinstance(fresh, PreparedReadout) or not isinstance(fresh.body, bytes):
        raise ParticipationAcceptanceError("acceptance_contract")
    if len(fresh.body) > MAX_RESULT_BYTES:
        raise ParticipationAcceptanceError("acceptance_limit")
    if original != fresh.body:
        raise ParticipationAcceptanceError("acceptance_evidence")
    return _compose(request, fresh, report.stem)


def export_participation_acceptance(
    dsn: str, request_file: Path, report: Path, output_directory: Path
) -> ParticipationAcceptanceExport:
    if not valid_path(request_file) or not valid_path(output_directory):
        raise ParticipationAcceptanceError("acceptance_input")
    try:
        request = read_request(request_file)
    except RequestError as error:
        raise ParticipationAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    prepared = prepare_participation_acceptance(dsn, request, report)
    try:
        digest = publish(output_directory, prepared.body)
    except (OSError, AssessmentError):
        raise ParticipationAcceptanceError("acceptance_output") from None
    return ParticipationAcceptanceExport(
        digest, prepared.subject_sha256, prepared.assessment.status, POLICY_SHA256
    )
