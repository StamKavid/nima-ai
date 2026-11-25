"""Pure per-use policy over internal check results, not a source-evidence verifier.

Only callers that ran the existing reconcilers may supply successful evidence checks.
No artifact decoder, SQL/file access, metric calculation or certification happens here.
"""

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from uuid import UUID

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
# Closed reviewed profiles: installing a new provider must not silently admit it.
_USES = {
    "U1": (
        "captured_contract_record_count.v1",
        "7d8b5f8ecf6ae366482f4b06cd245f16d23408b489ad9bcb44af493282ac043f",
        "85134c5d800350adfedf7dce6d995a36c48b194d919912695992f83369e11d5f",
    ),
    "U2": (
        "captured_record_count_by_cpv_period.v1",
        "577d91161d92e5a954d773427762fc4d7060b537a0300f4f54ecdac0002f132d",
        "7d9e7cb716e4184daf3601df7bd75a8064a8fe9a984880f73126cc5a714218e0",
    ),
    "U3": (
        "buyer_supplier_record_concentration.v1",
        "756f73916ccc0bcb03e2975d5c7419e137fb9004fda72a9ed0eba717c0530e11",
        "dcc0586db13667925d2d080fbaa4bb7a9defa1282009697ccb38c9938272118c",
    ),
    "U4": (
        "observed_change_between_captures.v1",
        "5ef663ebc1c297e9db184a5cfbf87afd2ea4c1231e1b2feb378cd082157cd2de",
        "76cf61bd7285eea0c4834cb1439cd5a42c62903f80c7cff9e3f8017d481f259d",
    ),
    "citations": (
        "explicit_procurement_citations.v1",
        "c4f293b425c21fc14019a4780588f67542273cadd8ea7bbe1eef0224dd77f749",
        "b01ac58501d4335cf073bff37b5ecf771c07f9d6d03e0190c8a7023b4c47b366",
    ),
}
_PROFILES = (
    ("kimdis", "kimdis-contract-v1", "kimdis-normalized-v1"),
    ("diavgeia", "diavgeia-search-v1", "diavgeia-decision-v1"),
    ("diavgeia", "diavgeia-commitment-search-v1", "diavgeia-commitment-v1"),
)
_STATUSES = {
    "U1": (
        "empty_capture",
        "no_observations_before_cutoff",
        "observed_participation",
        "selection_unresolved",
        "no_observed_participation",
    ),
    "U2": (
        "empty_capture",
        "no_observations_before_cutoff",
        "observed_activity",
        "selection_unresolved",
        "no_observed_activity",
    ),
    "U3": (
        "empty_capture",
        "no_observations_before_cutoff",
        "observed_concentration",
        "buyer_records_unresolved",
        "selection_unresolved",
        "no_observed_buyer_records",
    ),
    "U4": ("incomparable", "observed_changes", "no_observed_change"),
    "citations": (
        "empty_capture",
        "no_observations_before_cutoff",
        "observed_citations",
        "no_observed_citations",
    ),
}
_COUNTS = {
    "observations": "observation",
    "pages": "page",
    "page_records": "reported_record",
    "quarantined": "quarantined_record",
    "selected_records": "source_record",
    "ambiguous_records": "source_record",
    "excluded_records": "source_record",
    "unknown_dates": "source_record",
    "unclassified_cpv": "source_record",
    "unknown_suppliers": "source_record",
    "unassigned_buyers": "source_record",
    "invalid_supplier_occurrences": "supplier_occurrence",
    "buyer_records": "source_record",
    "resolved_records": "source_record",
    "unresolved_suppliers": "source_record",
    "partial_suppliers": "source_record",
    "joint_records": "source_record",
    "supplier_participations": "participation",
    "cpv_cells": "cell",
    "unresolved_citations": "citation",
    "ambiguous_targets": "citation",
    "unknown_target_types": "citation",
    "mismatched_target_types": "citation",
    "unknown_reference_lists": "source_record",
    "unknown_cancellations": "source_record",
    "cancelled_records": "source_record",
    "revoked_targets": "citation",
}
_CORE_COUNTS = frozenset(
    {
        "observations",
        "pages",
        "page_records",
        "quarantined",
        "selected_records",
        "ambiguous_records",
    }
)
_LIMITATIONS = {
    "U1": (
        "ambiguous_records",
        "unknown_suppliers",
        "unassigned_buyers",
        "invalid_supplier_occurrences",
        "unknown_cancellations",
        "cancelled_records",
    ),
    "U2": (
        "ambiguous_records",
        "unknown_dates",
        "unclassified_cpv",
        "unknown_cancellations",
        "cancelled_records",
    ),
    "U3": (
        "ambiguous_records",
        "unresolved_suppliers",
        "partial_suppliers",
        "unknown_cancellations",
        "cancelled_records",
    ),
    "U4": ("ambiguous_records",),
    "citations": (
        "ambiguous_records",
        "unresolved_citations",
        "ambiguous_targets",
        "unknown_target_types",
        "mismatched_target_types",
        "unknown_reference_lists",
        "unknown_cancellations",
        "cancelled_records",
        "revoked_targets",
    ),
}
_FAILURES = {c: (f"{c}_disagreement",) for c in _CHECKS} | {
    "keys": ("duplicate_identity", "inconsistent_version"),
    "capture_completeness": ("incomplete_capture", "quarantined_records"),
    "comparability": (
        "comparability_disagreement",
        "no_runs",
        "not_later",
        "quarantined_records",
        "query_mismatch",
        "run_incomplete",
    ),
}
_UNASSESSED = (
    "not_checked",
    "proof_unavailable",
    "unsupported_version",
    "unsupported_definition",
    "unsupported_provider_status",
    "unsupported_use",
)


class AcceptanceError(ValueError):
    """Malformed internal input, with a fixed code and no source values."""


@dataclass(frozen=True)
class RunBinding:
    source: str
    run_id: str
    connector_version: str
    normalizer_version: str


@dataclass(frozen=True)
class DatasetBinding:
    use: str
    request_sha256: str
    cohort_sha256: str | None
    cutoff: datetime
    runs: tuple[RunBinding, ...]
    definition_sha256: str
    sql_sha256: str


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str
    reason: str


@dataclass(frozen=True)
class Count:
    name: str
    grain: str
    value: int


@dataclass(frozen=True)
class DatasetFacts:
    binding: DatasetBinding
    provider_status: str
    checks: tuple[CheckResult, ...]
    counts: tuple[Count, ...]


@dataclass(frozen=True)
class Assessment:
    policy_sha256: str
    facts_sha256: str
    request_sha256: str
    cohort_sha256: str | None
    use: str
    provider_status: str
    status: str
    checks: tuple[CheckResult, ...]
    required_checks: tuple[str, ...]
    counts: tuple[Count, ...]
    limitations: tuple[str, ...]
    definition_sha256: str
    sql_sha256: str
    policy_id: str = "nima.dataset-acceptance"
    policy_version: str = "1.0.0"
    amount_eligibility: str = "not_applicable"


def _required(use: str) -> tuple[str, ...]:
    return tuple(
        c
        for c in _CHECKS
        if (c != "comparability" or use == "U4")
        and (c != "capture_completeness" or use != "citations")
    )


def _required_counts(use: str) -> frozenset[str]:
    names = _CORE_COUNTS | set(_LIMITATIONS.get(use, ()))
    if use == "U3":
        names |= {"buyer_records", "resolved_records", "joint_records", "supplier_participations"}
    return frozenset(names)


def definition() -> dict[str, object]:
    return deepcopy(
        {
            "id": "nima.dataset-acceptance",
            "version": "1.0.0",
            "uses": {
                u: {"metric_id": v[0], "definition_sha256": v[1], "sql_sha256": v[2]}
                for u, v in _USES.items()
            },
            "profiles": _PROFILES,
            "provider_statuses": _STATUSES,
            "required_checks": {u: _required(u) for u in _USES},
            "required_counts": {u: sorted(_required_counts(u)) for u in _USES},
            "failure_reasons": _FAILURES,
            "unassessed_reasons": _UNASSESSED,
            "successful_check_reason": "ok",
            "not_applicable_reason": "not_required_for_use",
            "count_grains": _COUNTS,
            "core_counts": sorted(_CORE_COUNTS),
            "limiting_counts": _LIMITATIONS,
            "precedence": ["blocked", "not_assessed", "limited", "ready"],
            "amount_eligibility": "not_applicable",
            "certification": "not_established",
            "accounting": [
                "page_records_equals_observations_plus_quarantined",
                "selected_plus_ambiguous_at_most_observations",
                "source_record_diagnostics_at_most_selected_excluding_ambiguous_and_excluded",
                "buyer_records_equals_resolved_plus_unresolved_when_all_available",
                "zero_pages_never_complete_empty",
                "positive_quarantine_blocks_numeric_captures",
                "incomparable_provider_status_cannot_pass_comparability",
                "overlapping_cpv_cells_and_supplier_participations_are_not_partitions",
                "applicable_diagnostic_counters_must_be_explicit_even_when_zero",
                "joint_and_partial_records_at_most_resolved_buyer_records",
                "supplier_participations_at_least_resolved_plus_joint_records",
            ],
            "limits": {
                "runs": 10,
                "checks": len(_CHECKS),
                "counts": len(_COUNTS),
                "counter": 2**63 - 1,
            },
        }
    )


def _digest(value: object) -> str:
    body = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    return hashlib.sha256(body.encode()).hexdigest()


def definition_sha256() -> str:
    return _digest(definition())


def _label(value: object) -> bool:
    return (
        isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,95}", value) is not None
    )


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validate(facts: DatasetFacts) -> None:
    if not isinstance(facts, DatasetFacts) or not isinstance(facts.binding, DatasetBinding):
        raise AcceptanceError("acceptance_input")
    b = facts.binding
    if (
        not _label(b.use)
        or not _label(facts.provider_status)
        or not all(_sha(v) for v in (b.request_sha256, b.definition_sha256, b.sql_sha256))
        or (b.cohort_sha256 is not None and not _sha(b.cohort_sha256))
        or not isinstance(b.cutoff, datetime)
        or b.cutoff.utcoffset() != timedelta(0)
        or not isinstance(b.runs, tuple)
        or len(b.runs) > 10
        or not isinstance(facts.checks, tuple)
        or len(facts.checks) > len(_CHECKS)
        or not isinstance(facts.counts, tuple)
        or len(facts.counts) > len(_COUNTS)
    ):
        raise AcceptanceError("acceptance_input")
    ids = set()
    for r in b.runs:
        if (
            not isinstance(r, RunBinding)
            or not all(_label(v) for v in (r.source, r.connector_version, r.normalizer_version))
            or not isinstance(r.run_id, str)
        ):
            raise AcceptanceError("acceptance_input")
        try:
            valid = str(UUID(r.run_id)) == r.run_id and r.run_id not in ids
        except ValueError:
            valid = False
        if not valid:
            raise AcceptanceError("acceptance_input")
        ids.add(r.run_id)
    names = set()
    for c in facts.checks:
        if (
            not isinstance(c, CheckResult)
            or not all(isinstance(v, str) for v in (c.check_id, c.status, c.reason))
            or c.check_id not in _CHECKS
            or c.check_id in names
            or not (
                (c.status == "passed" and c.reason == "ok")
                or (c.status == "failed" and c.reason in _FAILURES[c.check_id])
                or (c.status == "not_assessed" and c.reason in _UNASSESSED)
                or (c.status == "not_applicable" and c.reason == "not_required_for_use")
            )
        ):
            raise AcceptanceError("acceptance_input")
        names.add(c.check_id)
    names = set()
    for n in facts.counts:
        if (
            not isinstance(n, Count)
            or not isinstance(n.name, str)
            or n.name not in _COUNTS
            or n.grain != _COUNTS[n.name]
            or n.name in names
            or type(n.value) is not int
            or not 0 <= n.value <= 2**63 - 1
        ):
            raise AcceptanceError("acceptance_input")
        names.add(n.name)


def evaluate(facts: DatasetFacts) -> Assessment:
    """Evaluate internal verification outcomes; this function never performs their checks."""
    _validate(facts)
    b = facts.binding
    counts = {n.name: n.value for n in facts.counts}
    checks = {c.check_id: c for c in facts.checks}
    for c in _CHECKS:
        checks.setdefault(c, CheckResult(c, "not_assessed", "not_checked"))

    def mark(check: str, status: str, reason: str) -> None:
        if status == "failed" or checks[check].status != "failed":
            checks[check] = CheckResult(check, status, reason)

    supported = b.use in _USES
    if not supported:
        mark("bindings", "not_assessed", "unsupported_use")
    elif (b.definition_sha256, b.sql_sha256) != _USES[b.use][1:]:
        mark("bindings", "not_assessed", "unsupported_definition")
    elif not b.runs or b.cohort_sha256 is None:
        mark("bindings", "not_assessed", "proof_unavailable")
    elif any(
        (r.source, r.connector_version, r.normalizer_version) not in _PROFILES for r in b.runs
    ) or {r.source for r in b.runs} != (
        {"kimdis", "diavgeia"} if b.use == "citations" else {"kimdis"}
    ):
        mark("bindings", "not_assessed", "unsupported_version")
    if supported and facts.provider_status not in _STATUSES[b.use]:
        mark("eligibility", "not_assessed", "unsupported_provider_status")
    if (
        b.use == "U4"
        and facts.provider_status == "incomparable"
        and checks["comparability"].status != "failed"
    ):
        mark("comparability", "failed", "comparability_disagreement")
    if not counts.keys() >= _required_counts(b.use):
        mark("eligibility", "not_assessed", "proof_unavailable")
    if counts.keys() >= _CORE_COUNTS:
        if counts["quarantined"] > 0:
            mark("capture_completeness", "failed", "quarantined_records")
        elif counts["pages"] == 0:
            mark("capture_completeness", "failed", "incomplete_capture")
        if counts["page_records"] != counts["observations"] + counts["quarantined"]:
            mark("page_accounting", "failed", "page_accounting_disagreement")
        if counts["pages"] == 0 and counts["page_records"] > 0:
            mark("membership", "failed", "membership_disagreement")
        if counts["selected_records"] + counts["ambiguous_records"] > counts["observations"]:
            mark("eligibility", "failed", "eligibility_disagreement")
        if any(
            n.value > counts["selected_records"]
            for n in facts.counts
            if n.grain == "source_record"
            and n.name not in {"selected_records", "ambiguous_records", "excluded_records"}
        ):
            mark("eligibility", "failed", "eligibility_disagreement")
    if (
        counts.keys() >= {"buyer_records", "resolved_records", "unresolved_suppliers"}
        and counts["resolved_records"] + counts["unresolved_suppliers"] != counts["buyer_records"]
    ):
        mark("eligibility", "failed", "eligibility_disagreement")
    if (
        b.use == "U3"
        and counts.keys() >= {"joint_records", "partial_suppliers", "resolved_records"}
        and max(counts["joint_records"], counts["partial_suppliers"]) > counts["resolved_records"]
    ):
        mark("eligibility", "failed", "eligibility_disagreement")
    if (
        b.use == "U3"
        and counts.keys() >= {"joint_records", "resolved_records", "supplier_participations"}
        and counts["supplier_participations"] < counts["resolved_records"] + counts["joint_records"]
    ):
        mark("eligibility", "failed", "eligibility_disagreement")

    required = _required(b.use) if supported else ("bindings",)
    for c in required:
        if checks[c].status == "not_applicable":
            checks[c] = CheckResult(c, "not_assessed", "not_checked")
    if b.use != "U4":
        checks["comparability"] = CheckResult(
            "comparability", "not_applicable", "not_required_for_use"
        )
    limitations = [n for n in _LIMITATIONS.get(b.use, ()) if n in counts and counts[n] > 0]
    if b.use == "citations" and checks["capture_completeness"].status != "passed":
        limitations.append(
            "partial_capture"
            if checks["capture_completeness"].status == "failed"
            else "capture_completeness_unknown"
        )
    if not supported:
        status = "not_assessed"
    elif any(checks[c].status == "failed" for c in required):
        status = "blocked"
    elif any(checks[c].status != "passed" for c in required):
        status = "not_assessed"
    else:
        status = "limited" if limitations else "ready"
    document = asdict(facts)
    document["binding"]["cutoff"] = b.cutoff.isoformat()
    document["binding"]["runs"] = sorted(document["binding"]["runs"], key=lambda r: r["run_id"])
    document["checks"] = sorted(document["checks"], key=lambda c: c["check_id"])
    document["counts"] = sorted(document["counts"], key=lambda n: n["name"])
    return Assessment(
        definition_sha256(),
        _digest(document),
        b.request_sha256,
        b.cohort_sha256,
        b.use if supported else "unsupported",
        facts.provider_status
        if supported and facts.provider_status in _STATUSES[b.use]
        else "not_assessed",
        status,
        tuple(checks[c] for c in _CHECKS),
        required,
        tuple(sorted(facts.counts, key=lambda n: n.name)),
        tuple(sorted(limitations)) if status == "limited" else (),
        b.definition_sha256,
        b.sql_sha256,
    )
