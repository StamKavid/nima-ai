"""Private canonical graph artifacts; all SQL is closed before building/publication."""

from pathlib import Path
from uuid import UUID

from nima.graph import GraphError
from nima.graph.build import build_graph
from nima.graph.snapshot import read_snapshot
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.identity.review_state import MAX_REVIEW_EVENTS
from nima.identity.review_types import ReviewReport


def export_graph(
    dsn: str,
    report: ReviewReport,
    output: Path,
    *,
    entity_id: UUID | None = None,
    max_events: int = MAX_REVIEW_EVENTS,
) -> dict[str, object]:
    if entity_id is not None and not isinstance(entity_id, UUID):
        raise ValueError("graph_configuration")
    snapshot = read_snapshot(dsn, report, max_events=max_events)
    try:
        graph = build_graph(snapshot, entity_id=entity_id)
        body = encode(graph)
    except AssessmentError:
        raise GraphError("graph_limit") from None
    try:
        digest = publish(output, body)
    except (AssessmentError, OSError, ValueError):
        raise GraphError("graph_output") from None
    return {
        "status": "complete",
        "run_id": str(report.cohort.run_id),
        "graph_sha256": digest,
        "comparison_report_sha256": report.sha256,
        "reviewed_resolution_sha256": graph["reviewed_resolution_sha256"],
        "focus_entity_id": str(entity_id) if entity_id is not None else None,
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "occurrence_count": len(snapshot.review.heads),
        "contract_version_count": len(snapshot.contracts),
        "entity_count": len(snapshot.review.entities),
        "event_count": len(snapshot.review.events),
        "automatic_identity_links": 0,
        "reviewed_accepted_links": graph["reviewed_accepted_links"],
    }
