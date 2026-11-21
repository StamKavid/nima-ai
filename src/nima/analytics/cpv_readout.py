"""Read, verify against originals, evaluate and privately publish one CPV-by-period readout."""

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from nima.analytics.cpv_request import CpvRequest, read_cpv_request
from nima.analytics.metric_readout import (
    cohort_hash,
    definition_hash,
    encode_artifact,
    require_sql_parity,
    selection_label,
)
from nima.analytics.reconcile import ReconciliationError, VerifiedPage, verify_pages
from nima.analytics.request import RequestError
from nima.analytics.result import ReadoutError
from nima.analytics.snapshot import SnapshotError, read_cohort
from nima.graph.pilot_archive import PilotArchiveError
from nima.identity import AssessmentError
from nima.identity.artifacts import publish
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
    return selection_label(
        observation.observation_id,
        None if decision is None else (decision.observation_ids, decision.ambiguous),
    )


def _body(
    request: CpvRequest,
    document: dict[str, object],
    observations: tuple[Observation, ...],
    cited: dict[int, list[dict[str, object]]],
    result: MetricResult,
    pages: tuple[VerifiedPage, ...],
) -> bytes:
    policy = definition()
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
    body = {
        "version": "nima-cpv-period-v1",
        "source": "kimdis.contract",
        "metric": {
            "definition": policy,
            "definition_sha256": definition_hash(policy),
            "result": result.payload(),
        },
        "request": request.semantic_payload(),
        "request_sha256": request.request_sha256,
        "cohort_sha256": cohort_hash(document),
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
    return encode_artifact(body)


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
        require_sql_parity(
            dsn,
            reference_sql(),
            sql_rows(observations),
            (
                request.observation_cutoff,
                request.cpv_base_code,
                request.period_from,
                request.period_to,
            ),
            result.payload(),
        )
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
