"""Deterministic private manifest over the programmatic reconciler's frozen value."""

import json
from dataclasses import asdict
from datetime import datetime
from typing import cast

from nima.analytics.reconcile import ReconciledReadout
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.semantics.participation import Observation, RecordDecision

MAX_RESULT_BYTES = 1024 * 1024


class ReadoutError(ValueError):
    """Fixed reason only; identifiers, labels, paths and driver context stay private."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _selection(observation: Observation, decision: RecordDecision | None) -> str:
    if decision is None:
        return "after_cutoff"
    if observation.observation_id not in decision.observation_ids:
        return "earlier_observation"
    if decision.ambiguous:
        return "ambiguous_revision"
    if decision.matching_ordinals:
        return "contributing"
    if decision.unassessed or decision.unknown_suppliers:
        return "unassessed_selection"
    return "no_eligible_reported_match"


def build_result(readout: ReconciledReadout) -> bytes:
    """Compose a manifest; call reconcile before this internal serialization step."""
    document = json.loads(readout.snapshot.document_json)
    records = cast(list[dict[str, object]], document["records"])
    pages = {(str(page.run_id), page.page_number): page for page in readout.pages}
    decisions = {row.source_id: row for row in readout.snapshot.metric.records}
    observations = {row.observation_id: row for row in readout.snapshot.observations}
    evidence = []
    for record in records:
        observation = observations[cast(int, record["observation_id"])]
        page = pages[cast(str, record["run_id"]), cast(int, record["page_number"])]
        projection = cast(dict[str, object], record["projection"])
        evidence.append(
            {
                **{
                    name: record[name]
                    for name in (
                        "observation_id",
                        "source_id",
                        "normalizer_version",
                        "content_sha256",
                        "run_id",
                        "page_number",
                        "record_index",
                        "normalized",
                    )
                },
                "source": "kimdis.contract",
                "observed_at": observation.observed_at.isoformat(),
                "raw_sha256": page.raw_sha256,
                "json_pointer": f"/content/{record['record_index']}",
                "projection_version": projection["projection_version"],
                "projection_sha256": projection["projection_sha256"],
                "selection": _selection(observation, decisions.get(observation.source_id)),
            }
        )
    originals = {page.raw_sha256: page.byte_length for page in readout.pages}
    times = sorted(datetime.fromisoformat(page.observed_at) for page in readout.pages)
    result = {
        "version": "nima-supplier-buyers-v1",
        "source": "kimdis.contract",
        "metric": {
            "definition": json.loads(readout.definition_json),
            "definition_sha256": readout.definition_sha256,
            "result": readout.snapshot.metric.payload(),
        },
        "request": json.loads(readout.request_json),
        "request_sha256": readout.request_sha256,
        "snapshot_sha256": readout.snapshot.input_sha256,
        "quality": {
            "raw_bytes": "verified_against_archived_bytes",
            "projection": "reconciled_against_archived_records",
            "identity": "reported_identifier_only",
            "coverage": "selected_complete_runs_only",
            "source_current": "not_established",
            "legal_identity": "not_verified",
            "lineage": "record_to_original_not_field_level",
        },
        "interpretation_limits": [
            "Counts distinct captured contract-publication records, not awards or payments.",
            "Reported identifiers do not establish legal company identity.",
            "Selected complete runs do not establish national or market completeness.",
            "Latest observed revisions are not verified source-current revisions.",
            "Zero participation does not establish absence from the actual market.",
        ],
        "coverage": {
            "runs": document["runs"],
            "pages": [{**asdict(page), "run_id": str(page.run_id)} for page in readout.pages],
            "observation_count": len(records),
            "source_record_count": len({row["source_id"] for row in records}),
            "version_count": len(
                {
                    (row["source_id"], row["normalizer_version"], row["content_sha256"])
                    for row in records
                }
            ),
            "raw_object_count": len(originals),
            "verified_raw_bytes": sum(originals.values()),
            "first_page_observed_at": times[0].isoformat(),
            "last_page_observed_at": times[-1].isoformat(),
        },
        "evidence": evidence,
    }
    try:
        body = encode(result)
    except AssessmentError:
        raise ReadoutError("analytics_limit") from None
    if len(body) > MAX_RESULT_BYTES:
        raise ReadoutError("analytics_limit")
    return body
