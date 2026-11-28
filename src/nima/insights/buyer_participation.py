"""One captured buyer's supplier participation; no source access or metric promotion."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from nima.analytics.buyer_request import BuyerRequest
from nima.analytics.metric_readout import definition_hash
from nima.analytics.request import constant_hook, pairs_hook
from nima.analytics.result import MAX_RESULT_BYTES
from nima.dataops.buyer_acceptance import PreparedBuyerAcceptance
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.semantics.parties import buyer_key

FORMAT = "nima-buyer-participation-insight-v1"
Status = Literal["answered", "review_required", "insufficient_evidence"]
_TEMPLATE = (
    "Largest captured participation is {numerator} of {denominator} resolved buyer records; "
    "{groups} groups tie. There are {unresolved} unresolved records of {records}; "
    "{joint} joint records create overlapping participation."
)


class InsightError(ValueError):
    """Closed, private-safe operation reasons."""

    def __init__(self, reason: str) -> None:
        codes = {
            f"insight_{kind}"
            for kind in (
                "input",
                "limit",
                "evidence",
                "database",
                "contract",
                "output",
                "interrupted",
            )
        }
        super().__init__(reason if reason in codes else "insight_contract")


@dataclass(frozen=True)
class PreparedBuyerInsight:
    body: bytes = field(repr=False)
    status: Status
    subject_sha256: str


@dataclass(frozen=True)
class InsightExport:
    artifact_sha256: str
    status: Status
    subject_sha256: str


def definition() -> dict[str, object]:
    return {
        "id": "captured_buyer_participation_summary.v1",
        "version": "1",
        "template": _TEMPLATE,
        "rules": [
            "certified_metric_and_ready_data",
            "all_ties",
            "overlapping_record_participation",
        ],
    }


def _bound(
    request: BuyerRequest, parent: bytes, fresh: PreparedBuyerAcceptance
) -> tuple[dict[str, Any], dict[str, Any]]:
    report = json.loads(parent.decode(), object_pairs_hook=pairs_hook, parse_constant=constant_hook)
    sidecar = json.loads(
        fresh.body.decode(), object_pairs_hook=pairs_hook, parse_constant=constant_hook
    )
    metric, assessment = report["metric"], fresh.assessment
    expected_subject = {
        "artifact_sha256": hashlib.sha256(parent).hexdigest(),
        "request_sha256": request.request_sha256,
        "cohort_sha256": report["cohort_sha256"],
        "observation_cutoff": request.observation_cutoff.isoformat(),
    }
    metadata = sidecar["policy"]["definition"]
    expected_metric = {
        "id": metric["definition"]["metric"],
        "status": metric["definition"]["status"],
        "definition_sha256": definition_hash(metric["definition"]),
        "sql_sha256": metric["definition"]["sql_sha256"],
    }
    profile = metadata["uses"]["U3"]
    if (
        report["version"] != "nima-buyer-concentration-v1"
        or report["source"] != "kimdis.contract"
        or sidecar["version"] != "nima-buyer-acceptance-v1"
        or sidecar["subject"]["version"] != report["version"]
        or any(sidecar["subject"][k] != v for k, v in expected_subject.items())
        or fresh.subject_sha256 != expected_subject["artifact_sha256"]
        or report["request"] != request.semantic_payload()
        or report["request_sha256"] != request.request_sha256
        or sidecar["subject"]["metric"] != expected_metric
        or metric["definition_sha256"] != assessment.definition_sha256
        or assessment.definition_sha256 != expected_metric["definition_sha256"]
        or assessment.sql_sha256 != expected_metric["sql_sha256"]
        or assessment.request_sha256 != request.request_sha256
        or assessment.cohort_sha256 != report["cohort_sha256"]
        or assessment.use != "U3"
        or assessment.provider_status != metric["result"]["status"]
        or assessment.status not in {"ready", "limited", "blocked", "not_assessed"}
        or expected_metric["status"] not in {"draft", "reviewed", "certified"}
        or profile["metric_id"] != expected_metric["id"]
        or profile["definition_sha256"] != expected_metric["definition_sha256"]
        or profile["sql_sha256"] != expected_metric["sql_sha256"]
        or sidecar["policy"]["definition_sha256"] != assessment.policy_sha256
        or assessment.policy_sha256 != hashlib.sha256(encode(metadata)).hexdigest()
        or assessment.policy_id != metadata["id"]
        or assessment.policy_version != metadata["version"]
        or encode(sidecar["assessment"]) != encode(asdict(assessment))
        or encode(sidecar) != fresh.body
    ):
        raise InsightError("insight_contract")
    return report, sidecar


def _compose(
    request: BuyerRequest, parent: bytes, fresh: PreparedBuyerAcceptance
) -> PreparedBuyerInsight:
    try:
        report, sidecar = _bound(request, parent, fresh)
        return _render(request, report, sidecar, fresh)
    except InsightError:
        raise
    except AssessmentError:
        raise InsightError("insight_limit") from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
        raise InsightError("insight_contract") from None


def _render(
    request: BuyerRequest,
    report: dict[str, Any],
    sidecar: dict[str, Any],
    fresh: PreparedBuyerAcceptance,
) -> PreparedBuyerInsight:
    metric = report["metric"]
    result = metric["result"]
    assessment = fresh.assessment
    reasons = set(assessment.limitations)
    reasons.update(c.reason for c in assessment.checks if c.status in {"failed", "not_assessed"})
    if metric["definition"]["status"] != "certified":
        reasons.add("metric_not_certified")
    if assessment.status != "ready":
        reasons.add(f"data_{assessment.status}")
    if result["status"] != "observed_concentration":
        reasons.add(f"provider_{result['status']}")
    if not result["resolved_records"]:
        reasons.add("no_resolved_denominator")
    status: Status = (
        "insufficient_evidence"
        if reasons - {"metric_not_certified"}
        else "review_required"
        if reasons
        else "answered"
    )
    output = {
        "version": FORMAT,
        "definition": {
            "metadata": definition(),
            "definition_sha256": hashlib.sha256(encode(definition())).hexdigest(),
        },
        "subject": {
            "readout_sha256": fresh.subject_sha256,
            "request_sha256": request.request_sha256,
            "cohort_sha256": assessment.cohort_sha256,
            "metric_definition_sha256": assessment.definition_sha256,
            "metric_sql_sha256": assessment.sql_sha256,
            "policy_sha256": assessment.policy_sha256,
            "data_fitness_sha256": hashlib.sha256(fresh.body).hexdigest(),
            "observation_cutoff": request.observation_cutoff.isoformat(),
        },
        "data_fitness": sidecar,
        "status": status,
        "reason_codes": sorted(reasons),
        "scope": {
            "source": "kimdis.contract",
            "stage": "contract_publication",
            "buyer_ref": "/metric/result/buyer_key",
            "run_selection_ref": "/request/run_ids",
            "records_ref": "/metric/result/records",
            "comparison": "not_applicable",
            "observation_cutoff": request.observation_cutoff.isoformat(),
        },
        "answer": _answer(request, report) if status == "answered" else None,
        "interpretation_limits": list(
            dict.fromkeys(report["interpretation_limits"] + sidecar["interpretation_limits"])
        ),
    }
    return PreparedBuyerInsight(
        encode(output, limit=MAX_RESULT_BYTES), status, fresh.subject_sha256
    )


def _answer(request: BuyerRequest, report: dict[str, Any]) -> dict[str, object]:
    result = report["metric"]["result"]
    evidence, pages = report["evidence"], report["verified_pages"]
    by_id = {e["observation_id"]: i for i, e in enumerate(evidence)}
    by_page = {(p["run_id"], p["page_number"]): i for i, p in enumerate(pages)}
    if len(by_id) != len(evidence) or len(by_page) != len(pages):
        raise InsightError("insight_contract")
    witnesses, selected = [], set()
    for i, record in enumerate(result["records"]):
        if record["resolution"] != "resolved":
            continue
        indices = [by_id[oid] for oid in record["observation_ids"]]
        if not indices:
            raise InsightError("insight_contract")
        page_indices = set()
        for index in indices:
            row = evidence[index]
            if (
                row["source_id"] != record["source_id"]
                or row["content_sha256"] not in record["version_hashes"]
                or row["selection"] != "selected"
                or buyer_key(row["reported_buyer_key"]) != result["buyer_key"]
                or row["normalizer_version"] != report["metric"]["definition"]["normalizer"]
                or datetime.fromisoformat(row["observed_at"]) > request.observation_cutoff
            ):
                raise InsightError("insight_contract")
            page_indices.add(by_page[(row["run_id"], row["page_number"])])
        selected.update(indices)
        witnesses.append(
            {
                "record_ref": f"/metric/result/records/{i}",
                "evidence_refs": [f"/evidence/{j}" for j in indices],
                "page_refs": [f"/verified_pages/{j}" for j in sorted(page_indices)],
            }
        )
    groups = []
    for i, supplier in enumerate(result["suppliers"]):
        if supplier["supplier_key"] not in result["top_supplier_keys"]:
            continue
        refs = [
            f"/metric/result/records/{j}"
            for j, row in enumerate(result["records"])
            if supplier["supplier_key"] in row["supplier_keys"]
        ]
        if (
            len(refs) != supplier["record_count"]
            or supplier["record_count"] != result["top_record_count"]
        ):
            raise InsightError("insight_contract")
        groups.append({"supplier_ref": f"/metric/result/suppliers/{i}", "record_refs": refs})
    if (
        not groups
        or len(groups) != len(result["top_supplier_keys"])
        or len(witnesses) != result["resolved_records"]
    ):
        raise InsightError("insight_contract")
    return {
        "statement": _TEMPLATE.format(
            numerator=result["top_share"]["numerator"],
            denominator=result["top_share"]["denominator"],
            groups=len(groups),
            unresolved=result["unresolved_records"],
            records=result["buyer_records"],
            joint=result["joint_records"],
        ),
        "share": result["top_share"],
        "unresolved_share": result["unresolved_share"],
        "joint_records": result["joint_records"],
        "participation_total": result["participation_total"],
        "top_groups": groups,
        "denominator_record_refs": [w["record_ref"] for w in witnesses],
        "denominator_witnesses": witnesses,
        "evidence_refs": [f"/evidence/{j}" for j in sorted(selected)],
    }
