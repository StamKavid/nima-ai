"""U2 fitness over one fresh CPV preparation; no source requests or journal writes."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

import psycopg

from nima.analytics.cpv_readout import PreparedCpvReadout, prepare_cpv_result
from nima.analytics.cpv_request import CpvRequest, decode_cpv_request, read_cpv_request
from nima.analytics.metric_readout import cohort_hash, definition_hash
from nima.analytics.request import RequestError, constant_hook, pairs_hook
from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.analytics.snapshot import MAX_INPUT_BYTES
from nima.contracts import acceptance as policy
from nima.contracts.history import valid_digest
from nima.dataops.acceptance_files import AcceptanceError, read_subject, valid_path
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.semantics.cpv_period import MetricResult

FORMAT = "nima-cpv-acceptance-v1"
MAX_ACCEPTANCE_BYTES = 64 * 1024
POLICY_SHA256 = "f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06"
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


class CpvAcceptanceError(AcceptanceError):
    """Closed reasons without source values, selections or paths."""


@dataclass(frozen=True)
class PreparedCpvAcceptance:
    body: bytes = field(repr=False)
    assessment: policy.Assessment
    subject_sha256: str


@dataclass(frozen=True)
class CpvAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str


def _object(value: object, fields: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise CpvAcceptanceError("acceptance_contract")
    return cast(dict[str, object], value)


def _load(body: bytes | str) -> object:
    return json.loads(body, object_pairs_hook=pairs_hook, parse_constant=constant_hook)


def _number(value: object) -> int:
    if type(value) is not int or value < 0:
        raise CpvAcceptanceError("acceptance_contract")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CpvAcceptanceError("acceptance_contract")
    return value


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise CpvAcceptanceError("acceptance_contract")
    return cast(list[dict[str, object]], value)


def _facts(
    request: CpvRequest, prepared: PreparedCpvReadout
) -> tuple[policy.DatasetFacts, dict[str, object]]:
    if not isinstance(prepared.cohort_json, str) or not isinstance(prepared.metric, MetricResult):
        raise CpvAcceptanceError("acceptance_contract")
    if len(prepared.cohort_json.encode()) > MAX_INPUT_BYTES:
        raise CpvAcceptanceError("acceptance_limit")
    cohort = _object(_load(prepared.cohort_json), "runs pages records")
    body = _object(
        _load(prepared.body),
        "version source metric request request_sha256 cohort_sha256 quality interpretation_limits "
        "verified_pages evidence",
    )
    metric = _object(body["metric"], "definition definition_sha256 result")
    definition = _object(
        metric["definition"],
        "metric status source normalizer time_model period cpv taxonomy_validation unclassified "
        "unknown_period revision grain cancellation overlap sql_sha256",
    )
    for value in definition.values():
        _text(value)
    runs, pages, records = (_rows(cohort[k]) for k in ("runs", "pages", "records"))
    evidence = _rows(body["evidence"])
    result = prepared.metric
    if (
        body["version"] != "nima-cpv-period-v1"
        or body["source"] != "kimdis.contract"
        or body["request"] != request.semantic_payload()
        or body["request_sha256"] != request.request_sha256
        or body["cohort_sha256"] != cohort_hash(cohort)
        or definition["metric"] != "captured_record_count_by_cpv_period.v1"
        or definition["source"] != "kimdis.contract"
        or definition["status"] not in {"draft", "reviewed", "certified"}
        or not valid_digest(definition["sql_sha256"])
        or definition_hash(definition) != metric["definition_sha256"]
        or encode(metric["result"]) != encode(result.payload())
        or result.status
        not in {
            "empty_capture",
            "no_observations_before_cutoff",
            "observed_activity",
            "selection_unresolved",
            "no_observed_activity",
        }
        or not isinstance(prepared.observations, tuple)
        or not isinstance(prepared.pages, tuple)
    ):
        raise CpvAcceptanceError("acceptance_contract")
    expected_quality = {
        "raw_bytes": "verified_against_archived_bytes",
        "cpv": "re_extracted_from_archived_bytes_not_checked_against_taxonomy",
        "coverage": "selected_complete_runs_only",
        "source_current": "not_established",
        "lineage": "record_to_original_not_field_level",
    }
    if body["quality"] != expected_quality or not isinstance(body["interpretation_limits"], list):
        raise CpvAcceptanceError("acceptance_contract")
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
    verified = [{**asdict(p), "run_id": str(p.run_id)} for p in prepared.pages]
    if encode(_rows(body["verified_pages"])) != encode(page_view) or encode(verified) != encode(
        page_view
    ):
        raise CpvAcceptanceError("acceptance_contract")
    ids = tuple(_number(o.observation_id) for o in prepared.observations)
    if (
        not all(ids)
        or len(ids) != len(set(ids))
        or tuple(_number(r["observation_id"]) for r in records) != ids
        or tuple(_number(r["observation_id"]) for r in evidence) != ids
    ):
        raise CpvAcceptanceError("acceptance_contract")
    page_keys = {(p["run_id"], p["page_number"]) for p in pages}
    for observation, record, cited in zip(prepared.observations, records, evidence, strict=True):
        if (
            any(
                record[k] != cited[k]
                for k in (
                    "source_id",
                    "normalizer_version",
                    "content_sha256",
                    "run_id",
                    "page_number",
                )
            )
            or (record["run_id"], record["page_number"]) not in page_keys
            or record["source_id"] != observation.source_id
            or record["normalizer_version"] != observation.normalizer_version
            or record["content_sha256"] != observation.content_sha256
            or cited["json_pointer"] != f"/content/{_number(record['record_index'])}"
            or cited["observed_at"] != observation.observed_at.isoformat()
            or cited["reported_submission_text"] != observation.submitted_text
            or cited["cancelled"] is not observation.cancelled
        ):
            raise CpvAcceptanceError("acceptance_contract")
    bindings = []
    for row in runs:
        run = _object(
            row,
            "run_id query connector_version normalizer_version status managed "
            "next_page total_records total_pages page_size quarantine_count",
        )
        if (
            run["managed"] is not True
            or run["status"] != "complete"
            or not isinstance(run["query"], dict)
        ):
            raise CpvAcceptanceError("acceptance_contract")
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
        raise CpvAcceptanceError("acceptance_contract")
    record_ids = [_text(r.source_id) for r in result.records]
    if (
        len(record_ids) != len(set(record_ids))
        or result.ambiguous_source_ids != tuple(r.source_id for r in result.records if r.ambiguous)
        or any(type(r.ambiguous) is not bool for r in result.records)
    ):
        raise CpvAcceptanceError("acceptance_contract")
    selected = tuple(r for r in result.records if not r.ambiguous)
    coverage = result.coverage
    for value in asdict(coverage).values():
        _number(value)
    classes = ("classified", "unclassified_no_reported_code", "unclassified_metadata_unavailable")
    dates = ("parsed", "absent", "unparseable")
    if (
        coverage.selected_records != len(selected)
        or tuple(sum(r.classification == c for r in selected) for c in classes)
        != (
            coverage.classified,
            coverage.unclassified_no_reported_code,
            coverage.unclassified_metadata_unavailable,
        )
        or tuple(sum(r.date_outcome == d for r in selected) for d in dates)
        != (coverage.period_parsed, coverage.period_absent, coverage.period_unparseable)
        or sum(getattr(coverage, c) for c in classes) != len(selected)
        or coverage.period_parsed + coverage.period_absent + coverage.period_unparseable
        != len(selected)
        or any(r.cancelled is not None and type(r.cancelled) is not bool for r in selected)
    ):
        raise CpvAcceptanceError("acceptance_contract")
    counts = (
        policy.Count("observations", "observation", len(prepared.observations)),
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
            "unknown_dates", "source_record", coverage.period_absent + coverage.period_unparseable
        ),
        policy.Count(
            "unclassified_cpv",
            "source_record",
            coverage.unclassified_no_reported_code + coverage.unclassified_metadata_unavailable,
        ),
        policy.Count(
            "unknown_cancellations", "source_record", sum(r.cancelled is None for r in selected)
        ),
        policy.Count(
            "cancelled_records", "source_record", sum(r.cancelled is True for r in selected)
        ),
    )
    checks = tuple(
        policy.CheckResult(c, "not_applicable", "not_required_for_use")
        if c == "comparability"
        else policy.CheckResult(c, "passed", "ok")
        for c in _CHECKS
    )
    facts = policy.DatasetFacts(
        policy.DatasetBinding(
            "U2",
            request.request_sha256,
            body["cohort_sha256"],
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
    request: CpvRequest, prepared: PreparedCpvReadout, subject: str
) -> PreparedCpvAcceptance:
    try:
        metadata = policy.definition()
        if hashlib.sha256(encode(metadata)).hexdigest() != POLICY_SHA256:
            raise CpvAcceptanceError("acceptance_contract")
        facts, definition = _facts(request, prepared)
        assessment = policy.evaluate(facts)
        if (
            not isinstance(assessment, policy.Assessment)
            or assessment.policy_sha256 != POLICY_SHA256
            or assessment.policy_id != metadata["id"]
            or assessment.policy_version != metadata["version"]
            or assessment.use != "U2"
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
            != tuple(cast(dict[str, list[str]], metadata["required_checks"])["U2"])
            or tuple(c.check_id for c in assessment.checks) != _CHECKS
        ):
            raise CpvAcceptanceError("acceptance_contract")
        failures = cast(dict[str, tuple[str, ...]], metadata["failure_reasons"])
        for check in assessment.checks:
            reasons = {
                "passed": (metadata["successful_check_reason"],),
                "failed": failures[check.check_id],
                "not_assessed": cast(tuple[str, ...], metadata["unassessed_reasons"]),
                "not_applicable": (metadata["not_applicable_reason"],),
            }
            if check.status not in reasons or check.reason not in reasons[check.status]:
                raise CpvAcceptanceError("acceptance_contract")
        allowed = set(cast(dict[str, tuple[str, ...]], metadata["limiting_counts"])["U2"])
        if (
            not isinstance(assessment.limitations, tuple)
            or set(assessment.limitations) - allowed
            or assessment.limitations != tuple(sorted(set(assessment.limitations)))
            or (assessment.status != "limited" and assessment.limitations)
        ):
            raise CpvAcceptanceError("acceptance_contract")
        output = {
            "version": FORMAT,
            "subject": {
                "version": "nima-cpv-period-v1",
                "artifact_sha256": subject,
                "request_sha256": request.request_sha256,
                "cohort_sha256": facts.binding.cohort_sha256,
                "observation_cutoff": request.observation_cutoff.isoformat(),
                "run_profiles": [asdict(r) for r in facts.binding.runs],
                "evidence_scope": "all_admitted_pages",
                "diagnostic_scope": "selected_unambiguous_before_cpv_period_filters",
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
                "Data fitness for captured CPV/month contract-publication records only; "
                "no metric certification.",
                "CPV describes reported procurement objects, not company sectors; "
                "taxonomy is unchecked.",
                "Diagnostics precede CPV/month filters; "
                "overlapping cells are not distinct-record denominators.",
                "Provider status remains authoritative; "
                "no national coverage, source-current or market-absence claim.",
            ],
        }
        return PreparedCpvAcceptance(
            encode(output, limit=MAX_ACCEPTANCE_BYTES), assessment, subject
        )
    except CpvAcceptanceError:
        raise
    except AssessmentError:
        raise CpvAcceptanceError("acceptance_limit") from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
        raise CpvAcceptanceError("acceptance_contract") from None


def prepare_cpv_acceptance(dsn: str, request: CpvRequest, report: Path) -> PreparedCpvAcceptance:
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not valid_path(report)
        or report.suffix != ".json"
        or not valid_digest(report.stem)
    ):
        raise CpvAcceptanceError("acceptance_input")
    try:
        if (
            not isinstance(request, CpvRequest)
            or decode_cpv_request(
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
            raise CpvAcceptanceError("acceptance_input")
    except RequestError as error:
        raise CpvAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    except (ValueError, TypeError, AttributeError):
        raise CpvAcceptanceError("acceptance_input") from None
    try:
        original = read_subject(report, limit=MAX_RESULT_BYTES)
        fresh = prepare_cpv_result(dsn, request)
    except AcceptanceError as error:
        raise CpvAcceptanceError(str(error)) from None
    except ReadoutError as error:
        raise CpvAcceptanceError(_ERRORS.get(error.reason, "acceptance_contract")) from None
    except psycopg.Error:
        raise CpvAcceptanceError("acceptance_database") from None
    if not isinstance(fresh, PreparedCpvReadout) or not isinstance(fresh.body, bytes):
        raise CpvAcceptanceError("acceptance_contract")
    if len(fresh.body) > MAX_RESULT_BYTES:
        raise CpvAcceptanceError("acceptance_limit")
    if original != fresh.body:
        raise CpvAcceptanceError("acceptance_evidence")
    return _compose(request, fresh, report.stem)


def export_cpv_acceptance(
    dsn: str, request_file: Path, report: Path, output_directory: Path
) -> CpvAcceptanceExport:
    if not valid_path(request_file) or not valid_path(output_directory):
        raise CpvAcceptanceError("acceptance_input")
    try:
        request = read_cpv_request(request_file)
    except RequestError as error:
        raise CpvAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    prepared = prepare_cpv_acceptance(dsn, request, report)
    try:
        digest = publish(output_directory, prepared.body)
    except (OSError, AssessmentError):
        raise CpvAcceptanceError("acceptance_output") from None
    return CpvAcceptanceExport(
        digest, prepared.subject_sha256, prepared.assessment.status, POLICY_SHA256
    )
