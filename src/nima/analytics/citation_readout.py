"""Read-only two-source evidence reconciliation, model/SQL parity and private publication."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from psycopg.types.json import Jsonb

from nima.analytics.citation_cohort import read_verified_citation_cohort
from nima.analytics.citation_request import (
    CitationRequest,
    read_citation_request,
    validate_citation_request,
)
from nima.analytics.metric_readout import definition_hash
from nima.analytics.request import RequestError
from nima.analytics.result import ReadoutError
from nima.analytics.snapshot import SnapshotError, connected
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.semantics.citations import (
    MAX_OUTPUT_BYTES,
    CitationError,
    CitationResult,
    Observation,
    definition,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.semantics.selection import select_latest
from nima.storage.connection import Connection


@dataclass(frozen=True)
class CitationExport:
    artifact_sha256: str
    record_count: int
    edge_count: int
    outcome: str
    coverage: str


def _calculate(connection: Connection, request: CitationRequest) -> tuple[bytes, CitationResult]:
    try:
        cohort = read_verified_citation_cohort(connection, request)
        result = evaluate(cohort.contracts, cohort.decisions, cutoff=request.observation_cutoff)
        policy, query = definition(), reference_sql()
        if hashlib.sha256(query.encode()).hexdigest() != policy["sql_sha256"]:
            raise SnapshotError("citation_contract")
        calculated = connection.execute(
            query, (Jsonb(sql_rows(cohort.contracts, cohort.decisions)), request.observation_cutoff)
        ).fetchall()[0][0]
        if calculated != result.payload():
            raise SnapshotError("citation_contract")
        rows: tuple[Observation, ...] = (*cohort.contracts, *cohort.decisions)
        selections = {s.source_id: s for s in select_latest(rows, request.observation_cutoff)}
        evidence = []
        for entry in cohort.evidence:
            source = selections.get(cast(str, entry["source_id"]))
            if datetime.fromisoformat(cast(str, entry["observed_at"])) > request.observation_cutoff:
                label = "after_cutoff"
            elif source is not None and entry["content_sha256"] in source.versions:
                label = (
                    "ambiguous_candidate" if source.ambiguous else "selected_content_observation"
                )
            else:
                label = "earlier_content"
            evidence.append({**entry, "selection": label})
        complete = all(
            c["collection_complete"] and c["normalization_complete"] and c["quarantined_count"] == 0
            for c in cohort.captures
        )
        body = {
            "version": "nima-source-citations-v1",
            "model": {
                "definition": policy,
                "definition_sha256": definition_hash(policy),
                "result": result.payload(),
            },
            "request": request.semantic_payload(),
            "request_sha256": request.request_sha256,
            "cohort_sha256": cohort.cohort_sha256,
            "quality": {
                "raw_bytes": "verified_against_archived_bytes"
                if cohort.pages
                else "no_admitted_pages",
                "normalized_records": "reconciled_with_sql_and_installed_source_adapter",
                "coverage": "selected_complete_captures" if complete else "partial_capture",
                "metric_eligibility": "not_assessed_v1_08",
                "assertion": "reported_citation_only",
                "source_current": "not_established",
                "legal_identity": "not_established",
            },
            "captures": cohort.captures,
            "verified_pages": cohort.pages,
            "evidence": evidence,
            "interpretation_limits": [
                "A reported citation establishes neither legal identity nor economic equivalence.",
                "Unresolved means absent from this selected cohort, not absent from the source.",
                "Commitments, awards, contracts and payments remain distinct stages.",
                "No national coverage, legal validity, payment or market-share claim follows.",
                "Partial captures cannot establish absence or a complete match rate.",
                "This model remains draft; dataset/metric acceptance is a separate review.",
            ],
        }
        return encode(body, limit=MAX_OUTPUT_BYTES), result
    except CitationError as error:
        raise SnapshotError(
            "citation_limit" if str(error) == "citation_limit" else "citation_contract"
        ) from None
    except AssessmentError:
        raise SnapshotError("citation_limit") from None


def prepare_citation_readout(dsn: str, request: CitationRequest) -> tuple[bytes, CitationResult]:
    """One SELECT-only snapshot; publication and source acquisition are never fallbacks."""
    try:
        validate_citation_request(request)
        return connected(dsn, lambda connection: _calculate(connection, request))
    except RequestError as error:
        raise ReadoutError(error.reason) from None
    except SnapshotError as error:
        reasons = {
            "analytics_input": "citation_input",
            "analytics_limit": "citation_limit",
            "analytics_database": "citation_database",
            "analytics_schema": "citation_database",
            "analytics_role": "citation_database",
            "analytics_evidence": "citation_evidence",
        }
        allowed = {
            "citation_input",
            "citation_limit",
            "citation_contract",
            "citation_evidence",
            "citation_database",
            "citation_output",
        }
        reason = (
            error.reason
            if error.reason in allowed
            else reasons.get(error.reason, "citation_contract")
        )
        raise ReadoutError(reason) from None
    except (OSError, IndexError, AttributeError, RecursionError):
        raise ReadoutError("citation_evidence") from None


def export_citation_readout(dsn: str, request_file: Path, output_directory: Path) -> CitationExport:
    try:
        request = read_citation_request(request_file)
        body, result = prepare_citation_readout(dsn, request)
        # The coverage label is fixed by _calculate, not recomputed by an exporter.
        coverage = cast(str, json.loads(body)["quality"]["coverage"])
        digest = publish(output_directory, body)
        return CitationExport(digest, result.records, len(result.edges), result.status, coverage)
    except RequestError as error:
        raise ReadoutError(error.reason) from None
    except AssessmentError as error:
        raise ReadoutError(
            "citation_limit" if error.reason == "assessment_limit" else "citation_output"
        ) from None
    except OSError:
        raise ReadoutError("citation_output") from None
