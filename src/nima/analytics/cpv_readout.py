"""Read, verify against originals, evaluate and privately publish one CPV-by-period readout."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from psycopg.types.json import Jsonb

from nima.analytics.cpv_request import CpvRequest, read_cpv_request
from nima.analytics.reconcile import ReconciliationError, VerifiedPage, verify_pages
from nima.analytics.request import RequestError
from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.analytics.snapshot import SnapshotError, connected, read_cohort
from nima.graph.pilot_archive import PilotArchiveError
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.metadata.extract import MetadataError, kimdis_metadata
from nima.semantics.cpv_period import (
    CpvAssertion,
    MetricResult,
    Observation,
    SemanticError,
    definition,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.storage.connection import Connection


@dataclass(frozen=True)
class CpvExport:
    artifact_sha256: str
    record_count: int
    cell_count: int
    outcome: str


def _observations(
    document: dict[str, object], bodies: dict[tuple[str, int], bytes]
) -> tuple[tuple[Observation, ...], dict[int, list[dict[str, object]]]]:
    """Re-extract each record's CPV assertions from its verified original page bytes."""
    pages = {
        (cast(str, page["run_id"]), cast(int, page["page_number"])): page
        for page in cast(list[dict[str, object]], document["pages"])
    }
    metadata = {key: kimdis_metadata(body) for key, body in bodies.items()}
    rows: list[Observation] = []
    cited: dict[int, list[dict[str, object]]] = {}
    for record in cast(list[dict[str, object]], document["records"]):
        page_key = (cast(str, record["run_id"]), cast(int, record["page_number"]))
        entry = metadata[page_key][cast(int, record["record_index"])]
        if (
            entry["record_status"] != "normalized"
            or entry["source_id"] != record["source_id"]
            or entry["content_sha256"] != record["content_sha256"]
        ):
            raise ReconciliationError("analytics_evidence")
        assertions = [a for a in entry["assertions"] if a["dimension"] == "procurement_cpv"]
        normalized = cast(dict[str, object], record["normalized"])
        observation_id = cast(int, record["observation_id"])
        rows.append(
            Observation(
                observation_id,
                cast(str, record["source_id"]),
                cast(str, record["normalizer_version"]),
                record["content_sha256"],
                datetime.fromisoformat(cast(str, pages[page_key]["observed_at"])),
                cast(bool | None, normalized["cancelled"]),
                cast(str | None, normalized["source_submitted_at"]),
                tuple(
                    CpvAssertion(a["status"], a["code"] if a["status"] == "reported" else None)
                    for a in assertions
                ),
            )
        )
        cited[observation_id] = [
            {"status": a["status"], "code": a["code"], "json_pointer": a["expected_pointer"]}
            for a in assertions
        ]
    return tuple(rows), cited


def _selection(observation: Observation, result: MetricResult) -> str:
    decision = {row.source_id: row for row in result.records}.get(observation.source_id)
    if decision is None:
        return "after_cutoff"
    if observation.observation_id not in decision.observation_ids:
        return "earlier_observation"
    return "ambiguous_revision" if decision.ambiguous else "selected"


def _body(
    request: CpvRequest,
    document: dict[str, object],
    observations: tuple[Observation, ...],
    cited: dict[int, list[dict[str, object]]],
    result: MetricResult,
    pages: tuple[VerifiedPage, ...],
) -> bytes:
    policy = definition()
    policy_hash = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    records = {
        cast(int, row["observation_id"]): row
        for row in cast(list[dict[str, object]], document["records"])
    }
    evidence = []
    for observation in observations:
        record = records[observation.observation_id]
        evidence.append(
            {
                "observation_id": observation.observation_id,
                "source_id": observation.source_id,
                "normalizer_version": observation.normalizer_version,
                "content_sha256": observation.content_sha256,
                "run_id": record["run_id"],
                "page_number": record["page_number"],
                "json_pointer": f"/content/{record['record_index']}",
                "observed_at": observation.observed_at.isoformat(),
                "reported_submission_text": observation.submitted_text,
                "cancelled": observation.cancelled,
                "cpv_assertions": cited[observation.observation_id],
                "selection": _selection(observation, result),
            }
        )
    document_json = json.dumps(
        document, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
    )
    body = {
        "version": "nima-cpv-period-v1",
        "source": "kimdis.contract",
        "metric": {
            "definition": policy,
            "definition_sha256": policy_hash,
            "result": result.payload(),
        },
        "request": request.semantic_payload(),
        "request_sha256": request.request_sha256,
        "cohort_sha256": hashlib.sha256(document_json.encode()).hexdigest(),
        "quality": {
            "raw_bytes": "verified_against_archived_bytes",
            "cpv": "re_extracted_from_archived_bytes_not_checked_against_taxonomy",
            "coverage": "selected_complete_runs_only",
            "source_current": "not_established",
            "lineage": "record_to_original_not_field_level",
        },
        "interpretation_limits": [
            "Counts distinct captured contract-publication records, not awards or payments.",
            "A reported CPV code is as published and is not checked against the CPV taxonomy.",
            "The period is the month of the reported submission date, not an effective date.",
            "Selected complete runs do not establish national or market completeness.",
            "Latest observed revisions are not verified source-current revisions.",
        ],
        "verified_pages": [{**asdict(page), "run_id": str(page.run_id)} for page in pages],
        "evidence": evidence,
    }
    try:
        encoded = encode(body)
    except AssessmentError:
        raise ReadoutError("analytics_limit") from None
    if len(encoded) > MAX_RESULT_BYTES:
        raise ReadoutError("analytics_limit")
    return encoded


def prepare_cpv_readout(dsn: str, request: CpvRequest) -> tuple[bytes, MetricResult]:
    """Reconstruct and validate without publishing or writing SQL/source evidence."""
    try:
        cohort = read_cohort(dsn, request.run_ids)
        pages, bodies = verify_pages(cohort.document, request.archive_bindings)
        observations, cited = _observations(cohort.document, bodies)
        result = evaluate(
            observations,
            cutoff=request.observation_cutoff,
            cpv_base_code=request.cpv_base_code,
            period_from=request.period_from,
            period_to=request.period_to,
        )
        parameters = (
            Jsonb(sql_rows(observations)),
            request.observation_cutoff,
            request.cpv_base_code,
            request.period_from,
            request.period_to,
        )

        def calculated(connection: Connection) -> object:
            row = connection.execute(reference_sql(), parameters).fetchone()
            return None if row is None else row[0]

        if connected(dsn, calculated) != result.payload():
            raise ReadoutError("analytics_metric")
        return _body(request, cohort.document, observations, cited, result, pages), result
    except ReadoutError:
        raise
    except (SnapshotError, ReconciliationError, RequestError) as error:
        raise ReadoutError(error.reason) from None
    except PilotArchiveError:
        raise ReadoutError("analytics_archive") from None
    except SemanticError:
        raise ReadoutError("analytics_input") from None
    except (MetadataError, KeyError, TypeError, ValueError, IndexError):
        raise ReadoutError("analytics_evidence") from None
    except OSError:
        raise ReadoutError("analytics_output") from None


def export_cpv_readout(dsn: str, request_file: Path, output_directory: Path) -> CpvExport:
    """No network, SQL writes or original repair; validate fully before publication."""
    try:
        request = read_cpv_request(request_file)
        body, result = prepare_cpv_readout(dsn, request)
        digest = publish(output_directory, body)
        return CpvExport(digest, result.coverage.selected_records, len(result.cells), result.status)
    except RequestError as error:
        raise ReadoutError(error.reason) from None
    except AssessmentError as error:
        raise ReadoutError(
            "analytics_limit" if error.reason == "assessment_limit" else "analytics_output"
        ) from None
    except OSError:
        raise ReadoutError("analytics_output") from None
