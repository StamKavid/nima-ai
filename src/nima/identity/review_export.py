"""Deterministic private reviewed-resolution artifacts; publication follows SQL close."""

from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict

from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.identity.registry_report import build_report
from nima.identity.review_snapshot import ResolutionSnapshot, read_snapshot
from nima.identity.review_types import REVIEW_POLICY_VERSION, ReviewError, ReviewReport


class Resolution(TypedDict):
    report_format: str
    review_policy_version: str
    comparison_report_sha256: str
    comparison_report: dict[str, object]
    coverage_assurance: str
    attribution_assurance: str
    archive_integrity: str
    automatic_identity_links: int
    reviewed_accepted_links: int
    handle_ambiguity_scope: str
    occurrences: list[dict[str, object]]
    events: list[dict[str, object]]
    entities: list[dict[str, object]]
    selected_handle_ambiguities: list[dict[str, object]]


def build_resolution(snapshot: ResolutionSnapshot) -> Resolution:
    histories: dict[object, list[str]] = defaultdict(list)
    active: dict[object, int] = defaultdict(int)
    events = []
    for recorded in snapshot.events:
        event = recorded.event
        histories[event.request.subject].append(str(event.event_id))
        events.append(
            {
                "event_id": str(event.event_id),
                "subject_revision": event.subject_revision,
                "review_policy_version": event.policy_version,
                "request": event.request.payload(),
                "request_sha256": event.request.digest,
                "issues": event.issues,
                "database_principal": recorded.principal,
                "recorded_at": recorded.recorded_at,
                "attribution_assurance": "database_principal_only",
                "candidate_evidence": dict(recorded.candidate_provenance),
            }
        )
    occurrences = []
    for head in snapshot.heads:
        accepted_entity = head.accepted_entity_id
        if accepted_entity is not None:
            active[accepted_entity] += 1
        occurrences.append(
            {
                "subject": head.subject.payload(),
                "subject_revision": head.revision,
                "latest_event_id": histories[head.subject][-1] if histories[head.subject] else None,
                "review_status": "accepted" if accepted_entity is not None else "unresolved",
                "pairs": [
                    {
                        "candidate": pair.candidate.payload(),
                        "state": pair.state,
                        "event_id": str(pair.event_id) if pair.event_id else None,
                        "entity_id": str(pair.entity_id) if pair.entity_id else None,
                        "issues": pair.issues,
                    }
                    for pair in head.pairs
                ],
                "history_event_ids": histories[head.subject],
            }
        )
    entities = []
    by_number: dict[str, list[str]] = defaultdict(list)
    for entity in snapshot.entities:
        row = entity.evidence
        by_number[row.claim.registry_number].append(str(entity.entity_id))
        entities.append(
            {
                "entity_id": str(entity.entity_id),
                "kind": "unclassified",
                "creating_event_id": str(entity.creating_event_id),
                "active_accepted_occurrence_count": active[entity.entity_id],
                "anchor": {
                    "import_id": str(row.claim.import_id),
                    "registry_number": row.claim.registry_number,
                    "outcome": row.claim.outcome,
                    "attempt": row.attempt,
                    "status": row.status,
                    "raw_sha256": row.raw_sha256,
                    "observed_at": row.observed_at,
                    "source_id": row.source_id,
                    "normalizer_version": row.normalizer_version,
                    "fields": {key: asdict(value) for key, value in row.fields.items()},
                },
            }
        )
    return {
        "report_format": "nima-reviewed-resolution-v1",
        "review_policy_version": REVIEW_POLICY_VERSION,
        "comparison_report_sha256": snapshot.report.sha256,
        "comparison_report": dict(build_report(snapshot.report.cohort)),
        "coverage_assurance": "unverified_report_context",
        "archive_integrity": "not_checked",
        "attribution_assurance": "database_principal_only",
        "automatic_identity_links": 0,
        "reviewed_accepted_links": sum(active.values()),
        "occurrences": occurrences,
        "events": events,
        "entities": entities,
        "handle_ambiguity_scope": "selected_history_handles",
        "selected_handle_ambiguities": [
            {"registry_number": number, "entity_ids": sorted(ids)}
            for number, ids in sorted(by_number.items())
            if len(ids) > 1
        ],
    }


def export_resolution(
    dsn: str, report: ReviewReport, output: Path, *, max_events: int = 10000
) -> dict[str, object]:
    snapshot = read_snapshot(dsn, report, max_events=max_events)
    try:
        data = build_resolution(snapshot)
        body = encode(data)
    except AssessmentError:
        raise ReviewError("review_limit") from None
    try:
        digest = publish(output, body)
    except (AssessmentError, OSError, ValueError):
        raise ReviewError("review_output") from None
    return {
        "status": "complete",
        "run_id": str(report.cohort.run_id),
        "report_sha256": digest,
        "comparison_report_sha256": report.sha256,
        "occurrence_count": len(snapshot.heads),
        "event_count": len(snapshot.events),
        "entity_count": len(snapshot.entities),
        "automatic_identity_links": 0,
        "reviewed_accepted_links": data["reviewed_accepted_links"],
    }
