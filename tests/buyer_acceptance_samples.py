"""Controlled U3 producer frames for mapping tests, never evidence verification."""

import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from nima.analytics.buyer_readout import PreparedBuyerReadout
from nima.analytics.buyer_request import BuyerRequest
from nima.analytics.metric_readout import cohort_hash, definition_hash, selection_label
from nima.analytics.reconcile import VerifiedPage
from nima.identity.artifacts import encode
from nima.semantics import buyer_concentration as model
from nima.semantics.participation import Observation
from tests.participation_acceptance_samples import observation as observation
from tests.participation_acceptance_samples import producer as participation_frame


def request_file(request: BuyerRequest, path: Path) -> Path:
    path.write_bytes(
        encode(
            {
                **request.semantic_payload(),
                "archive_bindings": [
                    {"run_id": str(b.run_id), "root": str(b.root)} for b in request.archive_bindings
                ],
            }
        )
    )
    path.chmod(0o600)
    return path


def producer(
    rows: tuple[Observation, ...], *, definition: dict[str, object] | None = None, buyer: str = "B"
) -> tuple[BuyerRequest, PreparedBuyerReadout]:
    selection, frame = participation_frame(rows)
    request = BuyerRequest(
        selection.run_ids, selection.observation_cutoff, buyer, selection.archive_bindings
    )
    document = json.loads(frame.snapshot.document_json)
    result = model.evaluate(rows, buyer=buyer, cutoff=request.observation_cutoff)
    decisions = {r.source_id: r for r in result.records}
    records = {r["observation_id"]: r for r in document["records"]}
    evidence = []
    for row in rows:
        decision = decisions.get(row.source_id)
        if decision is None and row.source_id not in result.ambiguous_source_ids:
            continue
        record = records[row.observation_id]
        evidence.append(
            {
                **{
                    k: record[k]
                    for k in (
                        "observation_id",
                        "source_id",
                        "normalizer_version",
                        "content_sha256",
                        "run_id",
                        "page_number",
                    )
                },
                "json_pointer": "/content/0",
                "observed_at": row.observed_at.isoformat(),
                "reported_buyer_key": row.buyer_key,
                "cancelled": row.cancelled,
                "reported_suppliers": None
                if row.suppliers is None
                else [asdict(s) for s in row.suppliers],
                "resolution": None if decision is None else decision.resolution,
                "selection": "ambiguous_source"
                if decision is None
                else selection_label(row.observation_id, (decision.observation_ids, False)),
            }
        )
    meta = model.definition() if definition is None else definition
    pages = tuple(
        VerifiedPage(
            UUID(p["run_id"]),
            p["page_number"],
            p["raw_sha256"],
            p["byte_length"],
            p["observed_at"],
            p["record_count"],
        )
        for p in document["pages"]
    )
    body = {
        "version": "nima-buyer-concentration-v1",
        "source": "kimdis.contract",
        "metric": {
            "definition": meta,
            "definition_sha256": definition_hash(meta),
            "result": result.payload(),
        },
        "request": request.semantic_payload(),
        "request_sha256": request.request_sha256,
        "cohort_sha256": cohort_hash(document),
        "quality": {
            "raw_bytes": "verified_against_archived_bytes",
            "projection": "reconciled_against_archived_records",
            "identity": "reported_identifier_only",
            "coverage": "selected_complete_runs_only",
            "source_current": "not_established",
            "lineage": "record_to_original_not_field_level",
        },
        "interpretation_limits": ["Synthetic producer frame; no evidence verification."],
        "verified_pages": document["pages"],
        "evidence": evidence,
    }
    return request, PreparedBuyerReadout(
        encode(body), result, encode(document).decode(), rows, pages
    )
