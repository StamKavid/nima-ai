"""U3 fitness over one fresh buyer preparation; no source requests or journal writes."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

import psycopg

from nima.analytics.buyer_readout import PreparedBuyerReadout, prepare_buyer_result
from nima.analytics.buyer_request import BuyerRequest, decode_buyer_request, read_buyer_request
from nima.analytics.metric_readout import cohort_hash, definition_hash, selection_label
from nima.analytics.request import RequestError, constant_hook, pairs_hook
from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.analytics.snapshot import MAX_INPUT_BYTES
from nima.contracts import acceptance as policy
from nima.contracts.history import valid_digest
from nima.dataops.acceptance_files import AcceptanceError, read_subject, valid_path
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.semantics.buyer_concentration import MetricResult, RecordDecision, Share, SupplierCount
from nima.semantics.parties import buyer_key
from nima.semantics.selection import select_latest

FORMAT = "nima-buyer-acceptance-v1"
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


class BuyerAcceptanceError(AcceptanceError):
    """Closed reasons without source values, selections or paths."""


@dataclass(frozen=True)
class PreparedBuyerAcceptance:
    body: bytes = field(repr=False)
    assessment: policy.Assessment
    subject_sha256: str


@dataclass(frozen=True)
class BuyerAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str


def _object(value: object, fields: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise BuyerAcceptanceError("acceptance_contract")
    return cast(dict[str, object], value)


def _load(body: bytes | str) -> object:
    return json.loads(body, object_pairs_hook=pairs_hook, parse_constant=constant_hook)


def _number(value: object) -> int:
    if type(value) is not int or value < 0:
        raise BuyerAcceptanceError("acceptance_contract")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise BuyerAcceptanceError("acceptance_contract")
    return value


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise BuyerAcceptanceError("acceptance_contract")
    return cast(list[dict[str, object]], value)


def _share(value: Share | None, numerator: int | None, denominator: int) -> None:
    if numerator is None:
        if value is not None:
            raise BuyerAcceptanceError("acceptance_contract")
    elif not isinstance(value, Share) or (_number(value.numerator), _number(value.denominator)) != (
        numerator,
        denominator,
    ):
        raise BuyerAcceptanceError("acceptance_contract")


def _metric_counts(
    request: BuyerRequest, prepared: PreparedBuyerReadout
) -> tuple[policy.Count, ...]:
    result = prepared.metric
    selections = select_latest(prepared.observations, request.observation_cutoff)
    current = {s.source_id: s for s in selections if not s.ambiguous}
    wanted = buyer_key(request.buyer)
    if (
        not isinstance(result.records, tuple)
        or result.buyer_key != wanted
        or result.ambiguous_source_ids != tuple(s.source_id for s in selections if s.ambiguous)
        or tuple(r.source_id for r in result.records)
        != tuple(k for k, s in current.items() if buyer_key(s.chosen.buyer_key) == wanted)
    ):
        raise BuyerAcceptanceError("acceptance_contract")
    by_supplier: dict[str, list[RecordDecision]] = {}
    for record in result.records:
        selected = current[record.source_id]
        if (
            record.version_hashes != tuple(sorted(selected.versions))
            or record.observation_ids != tuple(sorted(o.observation_id for o in selected.current))
            or record.cancelled is not selected.chosen.cancelled
            or (record.cancelled is not None and type(record.cancelled) is not bool)
            or record.resolution
            not in {"resolved", "unknown_suppliers", "empty_suppliers", "no_eligible_supplier"}
            or not isinstance(record.supplier_keys, tuple)
            or record.supplier_keys != tuple(sorted(set(record.supplier_keys)))
            or bool(record.supplier_keys) != (record.resolution == "resolved")
        ):
            raise BuyerAcceptanceError("acceptance_contract")
        _number(record.ineligible_occurrences)
        for key in record.supplier_keys:
            _text(key)
            by_supplier.setdefault(key, []).append(record)
    resolved = tuple(r for r in result.records if r.resolution == "resolved")
    for value in (
        result.buyer_records,
        result.resolved_records,
        result.unresolved_records,
        result.distinct_suppliers,
        result.participation_total,
        result.joint_records,
    ):
        _number(value)
    if (
        result.buyer_records != len(result.records)
        or result.resolved_records != len(resolved)
        or result.unresolved_records != len(result.records) - len(resolved)
        or result.partial_source_ids
        != tuple(r.source_id for r in resolved if r.ineligible_occurrences > 0)
        or result.joint_records != sum(len(r.supplier_keys) >= 2 for r in resolved)
        or result.participation_total != sum(len(r.supplier_keys) for r in resolved)
        or result.distinct_suppliers != len(by_supplier)
        or not isinstance(result.suppliers, tuple)
    ):
        raise BuyerAcceptanceError("acceptance_contract")
    expected_suppliers = tuple(
        SupplierCount(
            key,
            len(rows),
            tuple(r.source_id for r in rows),
            sum(r.cancelled is True for r in rows),
            sum(r.cancelled is None for r in rows),
        )
        for key, rows in sorted(by_supplier.items(), key=lambda item: (-len(item[1]), item[0]))
    )
    for supplier in result.suppliers:
        for value in (
            supplier.record_count,
            supplier.cancelled_count,
            supplier.unknown_cancellation_count,
        ):
            _number(value)
    if result.suppliers != expected_suppliers:
        raise BuyerAcceptanceError("acceptance_contract")
    top = result.suppliers[0].record_count if result.suppliers else None
    if result.top_record_count is not None:
        _number(result.top_record_count)
    if result.top_record_count != top or result.top_supplier_keys != tuple(
        s.supplier_key for s in result.suppliers if s.record_count == top
    ):
        raise BuyerAcceptanceError("acceptance_contract")
    _share(result.top_share, top, len(resolved))
    _share(
        result.unresolved_share,
        result.unresolved_records if result.records else None,
        len(result.records),
    )
    return (
        policy.Count("selected_records", "source_record", len(current)),
        policy.Count("ambiguous_records", "source_record", len(result.ambiguous_source_ids)),
        policy.Count("buyer_records", "source_record", result.buyer_records),
        policy.Count("resolved_records", "source_record", result.resolved_records),
        policy.Count("unresolved_suppliers", "source_record", result.unresolved_records),
        policy.Count("partial_suppliers", "source_record", len(result.partial_source_ids)),
        policy.Count("joint_records", "source_record", result.joint_records),
        policy.Count("supplier_participations", "participation", result.participation_total),
        policy.Count(
            "unknown_cancellations",
            "source_record",
            sum(r.cancelled is None for r in result.records),
        ),
        policy.Count(
            "cancelled_records", "source_record", sum(r.cancelled is True for r in result.records)
        ),
    )


def _facts(
    request: BuyerRequest, prepared: PreparedBuyerReadout
) -> tuple[policy.DatasetFacts, dict[str, object]]:
    if not isinstance(prepared.cohort_json, str) or not isinstance(prepared.metric, MetricResult):
        raise BuyerAcceptanceError("acceptance_contract")
    if len(prepared.cohort_json.encode()) > MAX_INPUT_BYTES:
        raise BuyerAcceptanceError("acceptance_limit")
    cohort = _object(_load(prepared.cohort_json), "runs pages records")
    body = _object(
        _load(prepared.body),
        "version source metric request request_sha256 cohort_sha256 quality "
        "interpretation_limits verified_pages evidence",
    )
    metric = _object(body["metric"], "definition definition_sha256 result")
    definition = _object(
        metric["definition"],
        "metric status source normalizer buyer supplier measure denominator unresolved "
        "ties revision cancellation identity sql_sha256",
    )
    for value in definition.values():
        _text(value)
    runs, pages, records = (_rows(cohort[k]) for k in ("runs", "pages", "records"))
    evidence = _rows(body["evidence"])
    result = prepared.metric
    if (
        body["version"] != "nima-buyer-concentration-v1"
        or body["source"] != "kimdis.contract"
        or body["request"] != request.semantic_payload()
        or body["request_sha256"] != request.request_sha256
        or body["cohort_sha256"] != cohort_hash(cohort)
        or definition["metric"] != "buyer_supplier_record_concentration.v1"
        or definition["source"] != "kimdis.contract"
        or definition["status"] not in {"draft", "reviewed", "certified"}
        or not valid_digest(definition["sql_sha256"])
        or definition_hash(definition) != metric["definition_sha256"]
        or encode(metric["result"]) != encode(result.payload())
        or result.status
        not in {
            "empty_capture",
            "no_observations_before_cutoff",
            "observed_concentration",
            "buyer_records_unresolved",
            "selection_unresolved",
            "no_observed_buyer_records",
        }
        or not isinstance(prepared.observations, tuple)
        or not isinstance(prepared.pages, tuple)
    ):
        raise BuyerAcceptanceError("acceptance_contract")
    quality = {
        "raw_bytes": "verified_against_archived_bytes",
        "projection": "reconciled_against_archived_records",
        "identity": "reported_identifier_only",
        "coverage": "selected_complete_runs_only",
        "source_current": "not_established",
        "lineage": "record_to_original_not_field_level",
    }
    if body["quality"] != quality or not isinstance(body["interpretation_limits"], list):
        raise BuyerAcceptanceError("acceptance_contract")
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
        raise BuyerAcceptanceError("acceptance_contract")
    ids = tuple(_number(o.observation_id) for o in prepared.observations)
    if (
        not all(ids)
        or len(ids) != len(set(ids))
        or tuple(_number(r["observation_id"]) for r in records) != ids
    ):
        raise BuyerAcceptanceError("acceptance_contract")
    for observation, record in zip(prepared.observations, records, strict=True):
        if (record["source_id"], record["normalizer_version"], record["content_sha256"]) != (
            observation.source_id,
            observation.normalizer_version,
            observation.content_sha256,
        ):
            raise BuyerAcceptanceError("acceptance_contract")
    counts = _metric_counts(request, prepared)
    decisions = {r.source_id: r for r in result.records}
    cited_sources = set(decisions) | set(result.ambiguous_source_ids)
    selected_evidence = tuple(o for o in prepared.observations if o.source_id in cited_sources)
    if tuple(_number(r["observation_id"]) for r in evidence) != tuple(
        o.observation_id for o in selected_evidence
    ):
        raise BuyerAcceptanceError("acceptance_contract")
    record_by_id = {r["observation_id"]: r for r in records}
    page_keys = {(p["run_id"], p["page_number"]) for p in pages}
    for observation, cited in zip(selected_evidence, evidence, strict=True):
        record = record_by_id[observation.observation_id]
        decision = decisions.get(observation.source_id)
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
            or cited["json_pointer"] != f"/content/{_number(record['record_index'])}"
            or cited["observed_at"] != observation.observed_at.isoformat()
            or cited["reported_buyer_key"] != observation.buyer_key
            or cited["cancelled"] is not observation.cancelled
            or encode(cited["reported_suppliers"])
            != encode(
                None
                if observation.suppliers is None
                else [asdict(s) for s in observation.suppliers]
            )
            or cited["resolution"] != (None if decision is None else decision.resolution)
            or cited["selection"]
            != (
                "ambiguous_source"
                if decision is None
                else selection_label(observation.observation_id, (decision.observation_ids, False))
            )
        ):
            raise BuyerAcceptanceError("acceptance_contract")
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
            raise BuyerAcceptanceError("acceptance_contract")
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
        raise BuyerAcceptanceError("acceptance_contract")
    all_counts = (
        policy.Count("observations", "observation", len(prepared.observations)),
        policy.Count("pages", "page", len(pages)),
        policy.Count(
            "page_records", "reported_record", sum(_number(p["record_count"]) for p in pages)
        ),
        policy.Count(
            "quarantined", "quarantined_record", sum(_number(r["quarantine_count"]) for r in runs)
        ),
        *counts,
    )
    checks = tuple(
        policy.CheckResult(c, "not_applicable", "not_required_for_use")
        if c == "comparability"
        else policy.CheckResult(c, "passed", "ok")
        for c in _CHECKS
    )
    facts = policy.DatasetFacts(
        policy.DatasetBinding(
            "U3",
            request.request_sha256,
            body["cohort_sha256"],
            request.observation_cutoff,
            tuple(bindings),
            metric["definition_sha256"],
            cast(str, definition["sql_sha256"]),
        ),
        result.status,
        checks,
        all_counts,
    )
    return facts, definition


def _compose(
    request: BuyerRequest, prepared: PreparedBuyerReadout, subject: str
) -> PreparedBuyerAcceptance:
    try:
        metadata = policy.definition()
        if hashlib.sha256(encode(metadata)).hexdigest() != POLICY_SHA256:
            raise BuyerAcceptanceError("acceptance_contract")
        facts, definition = _facts(request, prepared)
        assessment = policy.evaluate(facts)
        if (
            not isinstance(assessment, policy.Assessment)
            or assessment.policy_sha256 != POLICY_SHA256
            or assessment.policy_id != metadata["id"]
            or assessment.policy_version != metadata["version"]
            or assessment.use != "U3"
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
            != tuple(cast(dict[str, list[str]], metadata["required_checks"])["U3"])
            or tuple(c.check_id for c in assessment.checks) != _CHECKS
        ):
            raise BuyerAcceptanceError("acceptance_contract")
        failures = cast(dict[str, tuple[str, ...]], metadata["failure_reasons"])
        for check in assessment.checks:
            reasons = {
                "passed": (metadata["successful_check_reason"],),
                "failed": failures[check.check_id],
                "not_assessed": cast(tuple[str, ...], metadata["unassessed_reasons"]),
                "not_applicable": (metadata["not_applicable_reason"],),
            }
            if check.status not in reasons or check.reason not in reasons[check.status]:
                raise BuyerAcceptanceError("acceptance_contract")
        allowed = set(cast(dict[str, tuple[str, ...]], metadata["limiting_counts"])["U3"])
        if (
            not isinstance(assessment.limitations, tuple)
            or set(assessment.limitations) - allowed
            or assessment.limitations != tuple(sorted(set(assessment.limitations)))
            or (assessment.status != "limited" and assessment.limitations)
        ):
            raise BuyerAcceptanceError("acceptance_contract")
        output = {
            "version": FORMAT,
            "subject": {
                "version": "nima-buyer-concentration-v1",
                "artifact_sha256": subject,
                "request_sha256": request.request_sha256,
                "cohort_sha256": facts.binding.cohort_sha256,
                "observation_cutoff": request.observation_cutoff.isoformat(),
                "run_profiles": [asdict(r) for r in facts.binding.runs],
                "evidence_scope": "all_admitted_pages",
                "diagnostic_scope": {
                    "cohort": "latest_selection_before_buyer_filter",
                    "buyer": "unambiguous_selected_buyer_records",
                },
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
                "Data fitness for captured buyer-supplier record participation only; "
                "no metric certification.",
                "Cohort coverage precedes buyer filtering; supplier participations overlap.",
                "Reported identifiers establish no legal identity, spending or market share.",
                "Provider status remains authoritative; no source-current or market-absence claim.",
            ],
        }
        return PreparedBuyerAcceptance(
            encode(output, limit=MAX_ACCEPTANCE_BYTES), assessment, subject
        )
    except BuyerAcceptanceError:
        raise
    except AssessmentError:
        raise BuyerAcceptanceError("acceptance_limit") from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
        raise BuyerAcceptanceError("acceptance_contract") from None


def prepare_buyer_acceptance(
    dsn: str, request: BuyerRequest, report: Path
) -> PreparedBuyerAcceptance:
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not valid_path(report)
        or report.suffix != ".json"
        or not valid_digest(report.stem)
    ):
        raise BuyerAcceptanceError("acceptance_input")
    try:
        if (
            not isinstance(request, BuyerRequest)
            or decode_buyer_request(
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
            raise BuyerAcceptanceError("acceptance_input")
    except RequestError as error:
        raise BuyerAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    except (ValueError, TypeError, AttributeError):
        raise BuyerAcceptanceError("acceptance_input") from None
    try:
        original = read_subject(report, limit=MAX_RESULT_BYTES)
        fresh = prepare_buyer_result(dsn, request)
    except AcceptanceError as error:
        raise BuyerAcceptanceError(str(error)) from None
    except ReadoutError as error:
        raise BuyerAcceptanceError(_ERRORS.get(error.reason, "acceptance_contract")) from None
    except psycopg.Error:
        raise BuyerAcceptanceError("acceptance_database") from None
    if not isinstance(fresh, PreparedBuyerReadout) or not isinstance(fresh.body, bytes):
        raise BuyerAcceptanceError("acceptance_contract")
    if len(fresh.body) > MAX_RESULT_BYTES:
        raise BuyerAcceptanceError("acceptance_limit")
    if original != fresh.body:
        raise BuyerAcceptanceError("acceptance_evidence")
    return _compose(request, fresh, report.stem)


def export_buyer_acceptance(
    dsn: str, request_file: Path, report: Path, output_directory: Path
) -> BuyerAcceptanceExport:
    if not valid_path(request_file) or not valid_path(output_directory):
        raise BuyerAcceptanceError("acceptance_input")
    try:
        request = read_buyer_request(request_file)
    except RequestError as error:
        raise BuyerAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    prepared = prepare_buyer_acceptance(dsn, request, report)
    try:
        digest = publish(output_directory, prepared.body)
    except (OSError, AssessmentError):
        raise BuyerAcceptanceError("acceptance_output") from None
    return BuyerAcceptanceExport(
        digest, prepared.subject_sha256, prepared.assessment.status, POLICY_SHA256
    )
