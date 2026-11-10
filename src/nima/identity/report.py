"""Evidence-linked review reports; candidate groups never become entity links."""

import hashlib
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict
from uuid import UUID

from nima.identity import POLICY_VERSION, AssessmentError
from nima.identity.artifacts import encode, publish
from nima.identity.cohort import read_cohort
from nima.identity.policy import Occurrence, evaluate


class AssessedOccurrence(Occurrence):
    assessment: dict[str, object]


class CandidateGroup(TypedDict):
    candidate_id: str
    namespace: str
    comparison_key: tuple[str, ...]
    members: list[int]
    issues: list[str]


class Report(TypedDict):
    report_format: str
    policy_version: str
    run_id: str
    projection_version: str
    coverage: dict[str, object]
    archive_integrity: str
    automatic_identity_links: int
    occurrences: list[AssessedOccurrence]
    groups: list[CandidateGroup]


def build_report(
    run: UUID, version: str, coverage: dict[str, object], members: list[Occurrence]
) -> Report:
    buckets: dict[tuple[str, ...], list[int]] = defaultdict(list)
    assessed: list[AssessedOccurrence] = []
    for index, member in enumerate(members):
        assessment = evaluate(member)
        assessed.append({**member, "assessment": asdict(assessment)})
        for key in assessment.keys:
            buckets[key].append(index)
    groups: list[CandidateGroup] = []
    for key, indexes in sorted(buckets.items()):
        names = {members[i]["name"] for i in indexes if members[i]["name"] is not None}
        taxes = {
            assessed[i]["assessment"]["comparison_tax_id"]
            for i in indexes
            if assessed[i]["assessment"]["comparison_tax_id"] is not None
        }
        issues = ["name_variation"] if len(names) > 1 else []
        if key[0] == "kimdis.buyer-key" and len(taxes) > 1:
            issues.append("tax_number_variation")
        groups.append(
            {
                "candidate_id": hashlib.sha256(encode([POLICY_VERSION, key])).hexdigest(),
                "namespace": key[0],
                "comparison_key": key[1:],
                "members": indexes,
                "issues": issues,
            }
        )
    return {
        "report_format": "nima-identity-report-v1",
        "policy_version": POLICY_VERSION,
        "run_id": str(run),
        "projection_version": version,
        "coverage": coverage,
        "archive_integrity": "not_checked",
        "automatic_identity_links": 0,
        "occurrences": assessed,
        "groups": groups,
    }


def assess_run(
    dsn: str, run: UUID, version: str, output: Path, *, max_mentions: int = 10000
) -> dict[str, object]:
    coverage, members = read_cohort(dsn, run, version, max_mentions)
    report = build_report(run, version, coverage, members)
    body = encode(report)
    try:
        digest = publish(output, body)
    except OSError:
        raise AssessmentError("output_io") from None
    return {
        "status": "complete",
        "policy_version": POLICY_VERSION,
        "report_sha256": digest,
        "mention_count": len(members),
        "candidate_group_count": len(report["groups"]),
        "automatic_identity_links": 0,
    }
