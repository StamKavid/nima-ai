"""U4 fitness over one fresh two-capture preparation; no source requests or journal writes."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

import psycopg

from nima.analytics.change_readout import PreparedChangeReadout, prepare_change_result
from nima.analytics.change_request import ChangeRequest, decode_change_request, read_change_request
from nima.analytics.metric_readout import cohort_hash, definition_hash
from nima.analytics.request import RequestError, constant_hook, pairs_hook
from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.analytics.run_facts import query_sha256
from nima.analytics.snapshot import MAX_INPUT_BYTES
from nima.contracts import acceptance as policy
from nima.contracts.history import valid_digest
from nima.dataops.acceptance_files import AcceptanceError, read_subject, valid_path
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.semantics.observed_change import CapturedVersion, MetricResult, sql_rows
from nima.semantics.selection import Selected, select_latest

FORMAT = "nima-change-acceptance-v1"
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


class ChangeAcceptanceError(AcceptanceError):
    """Closed reasons without source values, selections or paths."""


@dataclass(frozen=True)
class PreparedChangeAcceptance:
    body: bytes = field(repr=False)
    assessment: policy.Assessment
    subject_sha256: str


@dataclass(frozen=True)
class ChangeAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str


def _object(value: object, fields: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ChangeAcceptanceError("acceptance_contract")
    return cast(dict[str, object], value)


def _load(body: bytes | str) -> object:
    return json.loads(body, object_pairs_hook=pairs_hook, parse_constant=constant_hook)


def _number(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ChangeAcceptanceError("acceptance_contract")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ChangeAcceptanceError("acceptance_contract")
    return value


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ChangeAcceptanceError("acceptance_contract")
    return cast(list[dict[str, object]], value)


def _facts(
    request: ChangeRequest, prepared: PreparedChangeReadout
) -> tuple[policy.DatasetFacts, dict[str, object]]:
    result = prepared.metric
    if not isinstance(result, MetricResult) or not isinstance(prepared.pages, tuple):
        raise ChangeAcceptanceError("acceptance_contract")
    # Public validation of the typed capture vocabulary; no metric recomputation.
    sql_rows(prepared.earlier, prepared.later)
    body = _object(
        _load(prepared.body),
        "version source metric request request_sha256 cohort_sha256 run_facts quality "
        "interpretation_limits verified_pages evidence",
    )
    metric = _object(body["metric"], "definition definition_sha256 result")
    definition = _object(
        metric["definition"],
        "metric status source abstains reasons categories changed missing revision sql_sha256",
    )
    if (
        body["version"] != "nima-observed-change-v1"
        or body["source"] != "kimdis.contract"
        or body["request"] != request.semantic_payload()
        or body["request_sha256"] != request.request_sha256
        or definition["metric"] != "observed_change_between_captures.v1"
        or definition["source"] != "kimdis.contract"
        or definition["status"] not in {"draft", "reviewed", "certified"}
        or not valid_digest(definition["sql_sha256"])
        or definition_hash(definition) != metric["definition_sha256"]
        or encode(metric["result"]) != encode(result.payload())
        or result.status not in {"incomparable", "observed_changes", "no_observed_change"}
        or not isinstance(body["interpretation_limits"], list)
    ):
        raise ChangeAcceptanceError("acceptance_contract")
    for name in ("abstains", "changed", "missing", "revision"):
        _text(definition[name])
    for text in body["interpretation_limits"]:
        _text(text)
    allowed = {"no_runs", "not_later", "quarantined_records", "query_mismatch", "run_incomplete"}
    if (
        definition["reasons"] != sorted(allowed)
        or definition["categories"]
        != ["added", "changed", "missing_from_later_capture", "unchanged"]
        or result.reasons != tuple(sorted(set(result.reasons)))
        or set(result.reasons) - allowed
    ):
        raise ChangeAcceptanceError("acceptance_contract")
    captures = (prepared.earlier, prepared.later)
    expected_facts = {}
    for label, capture, ids in zip(
        ("earlier", "later"),
        captures,
        (request.earlier_run_ids, request.later_run_ids),
        strict=True,
    ):
        if tuple(r.run_id for r in capture.runs) != tuple(str(r) for r in ids):
            raise ChangeAcceptanceError("acceptance_contract")
        expected_facts[label] = [
            {
                **asdict(r),
                "observed_from": r.observed_from.isoformat(),
                "observed_to": r.observed_to.isoformat(),
            }
            for r in capture.runs
        ]
    if encode(body["run_facts"]) != encode(expected_facts):
        raise ChangeAcceptanceError("acceptance_contract")
    runs = (*prepared.earlier.runs, *prepared.later.runs)
    quarantine = sum(r.quarantined for r in runs)
    incomparable = prepared.cohort_json is None
    quality = {
        "completeness": "decided_from_stored_counters",
        "raw_bytes": "not_performed_incomparable"
        if incomparable
        else "verified_against_archived_bytes",
        "source_current": "not_established",
        "lineage": "record_to_original_not_field_level",
    }
    if (
        body["quality"] != quality
        or incomparable != bool(result.reasons)
        or incomparable != (result.status == "incomparable")
    ):
        raise ChangeAcceptanceError("acceptance_contract")
    if incomparable:
        if (
            body["cohort_sha256"] is not None
            or prepared.pages
            or body["verified_pages"] != []
            or body["evidence"] != []
            or any(c.versions for c in captures)
            or any(asdict(result.counts).values())
            or result.added
            or result.changed
            or result.missing_from_later_capture
            or result.unchanged
            or result.earlier.records != 0
            or result.later.records != 0
            or result.earlier.ambiguous_source_ids
            or result.later.ambiguous_source_ids
        ):
            raise ChangeAcceptanceError("acceptance_contract")
        bindings: tuple[policy.RunBinding, ...] = ()
        counts: tuple[policy.Count, ...] = (
            policy.Count("quarantined", "quarantined_record", quarantine),
        )
        complete = policy.CheckResult("capture_completeness", "passed", "ok")
        if quarantine:
            complete = policy.CheckResult("capture_completeness", "failed", "quarantined_records")
        elif "run_incomplete" in result.reasons or "no_runs" in result.reasons:
            complete = policy.CheckResult("capture_completeness", "failed", "incomplete_capture")
        checks = tuple(
            complete
            if c == "capture_completeness"
            else policy.CheckResult(c, "failed", result.reasons[0])
            if c == "comparability"
            else policy.CheckResult(c, "not_assessed", "proof_unavailable")
            for c in _CHECKS
        )
    else:
        bindings, counts = _coverage(request, prepared, body, quarantine)
        checks = tuple(policy.CheckResult(c, "passed", "ok") for c in _CHECKS)
    return policy.DatasetFacts(
        policy.DatasetBinding(
            "U4",
            request.request_sha256,
            cast(str | None, body["cohort_sha256"]),
            max(r.observed_to for r in runs),
            bindings,
            metric["definition_sha256"],
            cast(str, definition["sql_sha256"]),
        ),
        result.status,
        checks,
        counts,
    ), definition


def _coverage(
    request: ChangeRequest,
    prepared: PreparedChangeReadout,
    body: dict[str, object],
    quarantine: int,
) -> tuple[tuple[policy.RunBinding, ...], tuple[policy.Count, ...]]:
    if not isinstance(prepared.cohort_json, str):
        raise ChangeAcceptanceError("acceptance_contract")
    if len(prepared.cohort_json.encode()) > MAX_INPUT_BYTES:
        raise ChangeAcceptanceError("acceptance_limit")
    cohort = _object(_load(prepared.cohort_json), "runs pages records")
    runs, pages, records = (_rows(cohort[k]) for k in ("runs", "pages", "records"))
    facts = {r.run_id: r for c in (prepared.earlier, prepared.later) for r in c.runs}
    for row in runs:
        run = _object(
            row,
            "run_id query connector_version normalizer_version status managed next_page "
            "total_records total_pages page_size quarantine_count",
        )
        if (
            not isinstance(run["query"], dict)
            or query_sha256(run["query"]) != facts[_text(run["run_id"])].query_sha256
        ):
            raise ChangeAcceptanceError("acceptance_contract")
        for name in ("next_page", "total_records", "total_pages", "page_size", "quarantine_count"):
            _number(run[name])
    if body["cohort_sha256"] != cohort_hash(cohort):
        raise ChangeAcceptanceError("acceptance_contract")
    page_view = [
        {
            k: p[k]
            for k in (
                "run_id",
                "page_number",
                "raw_sha256",
                "byte_length",
                "observed_at",
                "record_count",
            )
        }
        for p in pages
    ]
    if encode(body["verified_pages"]) != encode(page_view) or encode(
        [{**asdict(p), "run_id": str(p.run_id)} for p in prepared.pages]
    ) != encode(page_view):
        raise ChangeAcceptanceError("acceptance_contract")
    bindings = tuple(
        policy.RunBinding(
            "kimdis",
            _text(r["run_id"]),
            _text(r["connector_version"]),
            _text(r["normalizer_version"]),
        )
        for r in runs
    )
    if (
        tuple(r.run_id for r in bindings) != tuple(str(r) for r in request.run_ids)
        or sum(_number(r["quarantine_count"]) for r in runs) != quarantine
        or any(r["status"] != "complete" or r["managed"] is not True for r in runs)
    ):
        raise ChangeAcceptanceError("acceptance_contract")
    evidence = _rows(body["evidence"])
    versions = {
        v.observation_id: (v, label)
        for label, c in (("earlier", prepared.earlier), ("later", prepared.later))
        for v in c.versions
    }
    ids = [_number(r["observation_id"]) for r in records]
    if (
        not all(ids)
        or len(set(ids)) != len(ids)
        or ids != sorted(versions)
        or [_number(r["observation_id"]) for r in evidence] != ids
    ):
        raise ChangeAcceptanceError("acceptance_contract")
    page_map = {(p["run_id"], p["page_number"]): p for p in pages}
    for record, cited in zip(records, evidence, strict=True):
        version, label = versions[cast(int, record["observation_id"])]
        page = page_map[record["run_id"], record["page_number"]]
        if (
            cited
            != {
                "observation_id": version.observation_id,
                "capture": label,
                "source_id": version.source_id,
                "content_sha256": version.content_sha256,
                "run_id": record["run_id"],
                "page_number": record["page_number"],
                "json_pointer": f"/content/{_number(record['record_index'])}",
                "observed_at": page["observed_at"],
            }
            or record["run_id"]
            not in {
                r.run_id for r in (prepared.earlier if label == "earlier" else prepared.later).runs
            }
            or record["source_id"] != version.source_id
            or record["content_sha256"] != version.content_sha256
            or page["observed_at"] != version.observed_at.isoformat()
        ):
            raise ChangeAcceptanceError("acceptance_contract")
    selected, ambiguous = _categories(prepared)
    counts = (
        policy.Count("observations", "observation", len(records)),
        policy.Count("pages", "page", len(pages)),
        policy.Count(
            "page_records", "reported_record", sum(_number(p["record_count"]) for p in pages)
        ),
        policy.Count("quarantined", "quarantined_record", quarantine),
        policy.Count("selected_records", "source_record", len(selected)),
        policy.Count("ambiguous_records", "source_record", len(ambiguous)),
    )
    return bindings, counts


def _categories(prepared: PreparedChangeReadout) -> tuple[set[str], set[str]]:
    """Check typed witnesses with the public selector, not a second U4 calculation."""
    result = prepared.metric
    maps = []
    for capture, summary in zip(
        (prepared.earlier, prepared.later), (result.earlier, result.later), strict=True
    ):
        selections = (
            select_latest(capture.versions, max(v.observed_at for v in capture.versions))
            if capture.versions
            else ()
        )
        current = {s.source_id: s for s in selections if not s.ambiguous}
        if (
            summary.run_ids != tuple(sorted(r.run_id for r in capture.runs))
            or summary.query_hashes != tuple(sorted({r.query_sha256 for r in capture.runs}))
            or _number(summary.records) != len(current)
            or summary.ambiguous_source_ids != tuple(s.source_id for s in selections if s.ambiguous)
        ):
            raise ChangeAcceptanceError("acceptance_contract")
        maps.append(current)
    before, after = maps

    def witness(
        side: dict[str, Selected[CapturedVersion]], sid: str, digest: str, ids: tuple[int, ...]
    ) -> None:
        item = side[sid]
        if set(item.versions) != {digest} or ids != tuple(
            sorted(v.observation_id for v in item.current)
        ):
            raise ChangeAcceptanceError("acceptance_contract")

    for added in result.added:
        if added.source_id in before:
            raise ChangeAcceptanceError("acceptance_contract")
        witness(after, added.source_id, added.later_version, added.later_observation_ids)
    for missing in result.missing_from_later_capture:
        if missing.source_id in after:
            raise ChangeAcceptanceError("acceptance_contract")
        witness(before, missing.source_id, missing.earlier_version, missing.earlier_observation_ids)
    for changed in result.changed:
        if changed.earlier_version == changed.later_version:
            raise ChangeAcceptanceError("acceptance_contract")
        witness(before, changed.source_id, changed.earlier_version, changed.earlier_observation_ids)
        witness(after, changed.source_id, changed.later_version, changed.later_observation_ids)
    for sid in result.unchanged:
        if set(before[sid].versions) != set(after[sid].versions):
            raise ChangeAcceptanceError("acceptance_contract")
    groups = (
        {r.source_id for r in result.added},
        {r.source_id for r in result.changed},
        {r.source_id for r in result.missing_from_later_capture},
        set(result.unchanged),
    )
    selected = set().union(*groups)
    ambiguous = set(result.earlier.ambiguous_source_ids) | set(result.later.ambiguous_source_ids)
    if (
        sum(map(len, groups)) != len(selected)
        or selected & ambiguous
        or tuple(_number(n) for n in asdict(result.counts).values()) != tuple(map(len, groups))
        or tuple(
            len(x)
            for x in (
                result.added,
                result.changed,
                result.missing_from_later_capture,
                result.unchanged,
            )
        )
        != tuple(map(len, groups))
        or selected != (set(before) | set(after)) - ambiguous
    ):
        raise ChangeAcceptanceError("acceptance_contract")
    return selected, ambiguous


def _compose(
    request: ChangeRequest, prepared: PreparedChangeReadout, subject: str
) -> PreparedChangeAcceptance:
    try:
        metadata = policy.definition()
        if hashlib.sha256(encode(metadata)).hexdigest() != POLICY_SHA256:
            raise ChangeAcceptanceError("acceptance_contract")
        facts, definition = _facts(request, prepared)
        assessment = policy.evaluate(facts)
        if (
            not isinstance(assessment, policy.Assessment)
            or assessment.policy_sha256 != POLICY_SHA256
            or assessment.policy_id != metadata["id"]
            or assessment.policy_version != metadata["version"]
            or assessment.use != "U4"
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
            != tuple(cast(dict[str, list[str]], metadata["required_checks"])["U4"])
            or tuple(c.check_id for c in assessment.checks) != _CHECKS
        ):
            raise ChangeAcceptanceError("acceptance_contract")
        failures = cast(dict[str, tuple[str, ...]], metadata["failure_reasons"])
        for check in assessment.checks:
            reasons = {
                "passed": (metadata["successful_check_reason"],),
                "failed": failures[check.check_id],
                "not_assessed": cast(tuple[str, ...], metadata["unassessed_reasons"]),
                "not_applicable": (metadata["not_applicable_reason"],),
            }
            if check.status not in reasons or check.reason not in reasons[check.status]:
                raise ChangeAcceptanceError("acceptance_contract")
        allowed = set(cast(dict[str, tuple[str, ...]], metadata["limiting_counts"])["U4"])
        if (
            not isinstance(assessment.limitations, tuple)
            or set(assessment.limitations) - allowed
            or assessment.limitations != tuple(sorted(set(assessment.limitations)))
            or (assessment.status != "limited" and assessment.limitations)
        ):
            raise ChangeAcceptanceError("acceptance_contract")
        output = {
            "version": FORMAT,
            "subject": {
                "version": "nima-observed-change-v1",
                "artifact_sha256": subject,
                "request_sha256": request.request_sha256,
                "cohort_sha256": facts.binding.cohort_sha256,
                "capture_end": facts.binding.cutoff.isoformat(),
                "time_basis": "stored_capture_end",
                "captures": request.semantic_payload(),
                "verification_scope": "sql_comparability_only"
                if prepared.cohort_json is None
                else "verified_two_capture_cohort",
                "raw_bytes": "not_performed_incomparable"
                if prepared.cohort_json is None
                else "verified_against_archived_bytes",
                "reasons": list(prepared.metric.reasons),
                "run_profiles": [asdict(r) for r in facts.binding.runs],
                "evidence_scope": "all_admitted_pages",
                "diagnostic_scope": "selected_unambiguous_before_observed_change_filters",
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
                "Data fitness for two captured publication sets; no metric certification.",
                "Missing from the later capture is not deletion or a legal event.",
                "SQL-only abstention does not establish original-byte integrity or archive health.",
                "Unavailable measurements are not zero; "
                "no source-current or national coverage claim.",
            ],
        }
        return PreparedChangeAcceptance(
            encode(output, limit=MAX_ACCEPTANCE_BYTES), assessment, subject
        )
    except ChangeAcceptanceError:
        raise
    except AssessmentError:
        raise ChangeAcceptanceError("acceptance_limit") from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
        raise ChangeAcceptanceError("acceptance_contract") from None


def prepare_change_acceptance(
    dsn: str, request: ChangeRequest, report: Path
) -> PreparedChangeAcceptance:
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not valid_path(report)
        or report.suffix != ".json"
        or not valid_digest(report.stem)
    ):
        raise ChangeAcceptanceError("acceptance_input")
    try:
        if (
            not isinstance(request, ChangeRequest)
            or decode_change_request(
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
            raise ChangeAcceptanceError("acceptance_input")
    except RequestError as error:
        raise ChangeAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    except (ValueError, TypeError, AttributeError):
        raise ChangeAcceptanceError("acceptance_input") from None
    try:
        original = read_subject(report, limit=MAX_RESULT_BYTES)
        fresh = prepare_change_result(dsn, request)
    except AcceptanceError as error:
        raise ChangeAcceptanceError(str(error)) from None
    except ReadoutError as error:
        raise ChangeAcceptanceError(_ERRORS.get(error.reason, "acceptance_contract")) from None
    except psycopg.Error:
        raise ChangeAcceptanceError("acceptance_database") from None
    if not isinstance(fresh, PreparedChangeReadout) or not isinstance(fresh.body, bytes):
        raise ChangeAcceptanceError("acceptance_contract")
    if len(fresh.body) > MAX_RESULT_BYTES:
        raise ChangeAcceptanceError("acceptance_limit")
    if original != fresh.body:
        raise ChangeAcceptanceError("acceptance_evidence")
    return _compose(request, fresh, report.stem)


def export_change_acceptance(
    dsn: str, request_file: Path, report: Path, output_directory: Path
) -> ChangeAcceptanceExport:
    if not valid_path(request_file) or not valid_path(output_directory):
        raise ChangeAcceptanceError("acceptance_input")
    try:
        request = read_change_request(request_file)
    except RequestError as error:
        raise ChangeAcceptanceError(_ERRORS.get(error.reason, "acceptance_input")) from None
    prepared = prepare_change_acceptance(dsn, request, report)
    try:
        digest = publish(output_directory, prepared.body)
    except (OSError, AssessmentError):
        raise ChangeAcceptanceError("acceptance_output") from None
    return ChangeAcceptanceExport(
        digest, prepared.subject_sha256, prepared.assessment.status, POLICY_SHA256
    )
