"""Reproducible private reports of reported-identifier agreement, never identities."""

from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import NotRequired, TypedDict
from uuid import UUID

from nima.identity import (
    MAX_COMPARISON_MENTIONS,
    POLICY_VERSION,
    AssessmentError,
)
from nima.identity.artifacts import encode, publish
from nima.identity.registry_cohort import ComparisonCohort, read_comparison_cohort
from nima.identity.registry_policy import SearchQuery, compare


class Report(TypedDict):
    report_format: str
    policy_version: str
    procurement_assessment_policy_version: str
    run_id: str
    projection_version: str
    coverage: dict[str, object]
    archive_integrity: str
    automatic_identity_links: int
    registry_imports: list[dict[str, object]]
    registry_observations: list[dict[str, object]]
    occurrences: list[dict[str, object]]
    # Present only when an imported AFM search was selected (report format v2).
    search_imports: NotRequired[list[dict[str, object]]]
    search_queries: NotRequired[list[dict[str, object]]]


def build_report(cohort: ComparisonCohort) -> Report:
    parties = sorted(
        cohort.parties,
        key=lambda row: (
            row.source_id,
            row.normalizer_version,
            row.content_sha256,
            row.observation_id,
            row.role,
            row.ordinal,
        ),
    )
    registry = sorted(
        cohort.registry,
        key=lambda row: (
            row.claim.import_id.int,
            row.claim.registry_number,
            row.claim.queried_afm or "",
        ),
    )
    searches = sorted(cohort.search_queries, key=lambda row: (row.import_id.int, row.afm))
    result = compare(
        tuple(row.claim() for row in parties),
        tuple(row.claim for row in registry),
        tuple(SearchQuery(q.import_id, q.afm, q.outcome, q.truncated) for q in searches),
    )
    catalog: list[dict[str, object]] = []
    for row, assessed in zip(registry, result.registry, strict=True):
        searched: dict[str, object] = (
            {"queried_afm": row.claim.queried_afm, "afm_matches": row.claim.afm_matches}
            if row.claim.queried_afm is not None
            else {}
        )
        catalog.append(
            {
                **searched,
                "import_id": str(row.claim.import_id),
                "registry_number": row.claim.registry_number,
                "outcome": row.claim.outcome,
                "attempt": row.attempt,
                "status": row.status,
                "raw_sha256": row.raw_sha256,
                "observed_at": row.observed_at,
                "source_id": row.source_id,
                "normalizer_version": row.normalizer_version,
                "fields": {name: asdict(assertion) for name, assertion in row.fields.items()},
                "identifier_assessment": {
                    "comparison_afm": assessed.comparison_afm,
                    "identifier_status": assessed.identifier_status,
                    "issues": assessed.issues,
                    "checksum_status": "not_checked",
                    "authority_status": "not_checked",
                    "issuer_country": None,
                    "identity_status": "unresolved",
                },
            }
        )
    occurrences: list[dict[str, object]] = []
    for party, comparison in zip(parties, result.comparisons, strict=True):
        occurrences.append(
            {
                **asdict(party),
                "assessment": asdict(comparison.assessment),
                "comparison": {
                    "outcome": comparison.outcome,
                    "registry_observation_refs": comparison.registry_observation_refs,
                    "issues": comparison.issues,
                },
            }
        )
    report: Report = {
        "report_format": "nima-registry-comparison-report-v1",
        "policy_version": result.policy_version,
        "procurement_assessment_policy_version": POLICY_VERSION,
        "run_id": str(cohort.run_id),
        "projection_version": cohort.projection_version,
        "coverage": dict(cohort.coverage),
        "archive_integrity": "not_checked",
        "automatic_identity_links": result.automatic_identity_links,
        "registry_imports": [
            {**asdict(row), "import_id": str(row.import_id)}
            for row in sorted(cohort.imports, key=lambda row: row.import_id.int)
        ],
        "registry_observations": catalog,
        "occurrences": occurrences,
    }
    if cohort.search_imports:
        report["report_format"] = "nima-registry-comparison-report-v2"
        report["search_imports"] = [
            {**asdict(row), "import_id": str(row.import_id)}
            for row in sorted(cohort.search_imports, key=lambda row: row.import_id.int)
        ]
        report["search_queries"] = [{**asdict(q), "import_id": str(q.import_id)} for q in searches]
    return report


def compare_run(
    dsn: str,
    run: UUID,
    gemi_imports: Sequence[UUID],
    version: str,
    output: Path,
    *,
    max_mentions: int = MAX_COMPARISON_MENTIONS,
) -> dict[str, object]:
    cohort = read_comparison_cohort(dsn, run, gemi_imports, version, max_mentions=max_mentions)
    report = build_report(cohort)
    body = encode(report)
    try:
        digest = publish(output, body)
    except OSError:
        raise AssessmentError("output_io") from None
    summary: dict[str, object] = {
        "status": "complete",
        "run_id": str(run),
        "gemi_import_ids": [
            str(row.import_id) for row in sorted(cohort.imports, key=lambda row: row.import_id.int)
        ],
        "policy_version": report["policy_version"],
        "report_sha256": digest,
        "mention_count": len(cohort.parties),
        "registry_observation_count": len(cohort.registry),
        "automatic_identity_links": 0,
    }
    if cohort.search_imports:
        summary["search_import_ids"] = [
            str(row.import_id)
            for row in sorted(cohort.search_imports, key=lambda row: row.import_id.int)
        ]
        summary["searched_afm_count"] = len(cohort.search_queries)
    return summary
