"""Synthetic producer frames for mapping tests; actual verification has native SQL tests."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from nima.analytics.citation_request import CitationRequest
from nima.analytics.metric_readout import definition_hash
from nima.graph.pilot_archive import ArchiveBinding
from nima.semantics import citations


def producer(
    contracts: tuple[citations.ContractObservation, ...],
    targets: tuple[citations.DecisionObservation, ...],
    *,
    partial: bool = False,
    quarantined: int = 0,
) -> tuple[CitationRequest, dict[str, object], citations.CitationResult]:
    request = CitationRequest(
        (UUID(int=1),),
        (UUID(int=2),),
        datetime(2026, 1, 10, tzinfo=UTC),
        (
            ArchiveBinding("kimdis", UUID(int=1), Path("/unused/kimdis")),
            ArchiveBinding("diavgeia", UUID(int=2), Path("/unused/diavgeia")),
        ),
    )
    result = citations.evaluate(contracts, targets, cutoff=request.observation_cutoff)
    captures = []
    pages = []
    evidence = []
    groups: tuple[
        tuple[
            str,
            UUID,
            tuple[citations.ContractObservation | citations.DecisionObservation, ...],
            str,
            str,
            int,
        ],
        ...,
    ] = (
        ("kimdis", UUID(int=1), contracts, "kimdis-contract-v1", "kimdis-normalized-v1", 0),
        (
            "diavgeia",
            UUID(int=2),
            targets,
            "diavgeia-commitment-search-v1",
            "diavgeia-commitment-v1",
            quarantined,
        ),
    )
    for source, run, rows, connector, normalizer, issues in groups:
        count = len(rows) + issues
        captures.append(
            {
                "source": source,
                "run_id": str(run),
                "connector_version": connector,
                "normalizer_version": normalizer,
                "collection_complete": not partial and not issues,
                "normalization_complete": not partial,
                "quarantined_count": issues,
                "committed_page_count": 1,
                "normalized_observations": len(rows),
                "query": {},
                "query_sha256": "d" * 64,
                "reported_page_size": max(count, 1),
                "reported_total_pages": 2 if partial else int(count > 0),
                "reported_total_records": count + int(partial),
                "status": "interrupted" if partial else "complete",
                "observed_from": "2026-01-01T00:00:00+00:00",
                "observed_to": "2026-01-01T00:00:00+00:00",
                "source_attribution": {
                    "documentation_url": "https://example.invalid",
                    "license": "CC BY 4.0",
                    "statements": [],
                },
            }
        )
        pages.append(
            {
                "source": source,
                "run_id": str(run),
                "page_number": 0,
                "record_count": count,
                "quarantined_count": issues,
                "byte_length": 1,
                "raw_sha256": "a" * 64,
                "observed_at": "2026-01-01T00:00:00+00:00",
                "source_ids": [r.source_id for r in rows],
            }
        )
        for index, row in enumerate(rows):
            evidence.append(
                {
                    "source": source,
                    "run_id": str(run),
                    "source_id": row.source_id,
                    "observation_id": row.observation_id,
                    "content_sha256": row.content_sha256,
                    "normalizer_version": normalizer,
                    "observed_at": row.observed_at.isoformat(),
                    "page_number": 0,
                    "record_index": index,
                    "raw_sha256": "a" * 64,
                    "json_pointer": f"/content/{index}"
                    if source == "kimdis"
                    else f"/decisions/{index}",
                    "field_locations": {},
                    "selection": "selected_content_observation",
                }
            )
    definition = citations.definition()
    data: dict[str, object] = {
        "version": "nima-source-citations-v1",
        "request": request.semantic_payload(),
        "request_sha256": request.request_sha256,
        "cohort_sha256": "c" * 64,
        "captures": captures,
        "verified_pages": pages,
        "evidence": evidence,
        "model": {
            "definition": definition,
            "definition_sha256": definition_hash(definition),
            "result": result.payload(),
        },
        "quality": {
            "assertion": "reported_citation_only",
            "legal_identity": "not_established",
            "source_current": "not_established",
            "metric_eligibility": "not_assessed_v1_08",
            "normalized_records": "reconciled_with_sql_and_installed_source_adapter",
            "raw_bytes": "verified_against_archived_bytes",
            "coverage": "partial_capture"
            if partial or quarantined
            else "selected_complete_captures",
        },
        "interpretation_limits": [],
    }
    return request, data, result
