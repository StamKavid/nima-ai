"""Read, verify against originals, evaluate and privately publish a buyer-concentration readout."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import cast

from nima.analytics.buyer_request import BuyerRequest, read_buyer_request
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
from nima.identity.artifacts import encode, publish
from nima.semantics.buyer_concentration import (
    MetricResult,
    definition,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.semantics.participation import Observation, SemanticError


@dataclass(frozen=True)
class BuyerExport:
    artifact_sha256: str
    buyer_record_count: int
    supplier_count: int
    outcome: str


@dataclass(frozen=True)
class PreparedBuyerReadout:
    """Verified report and immutable facts from its existing single cohort read."""

    body: bytes = field(repr=False)
    metric: MetricResult
    cohort_json: str = field(repr=False)
    observations: tuple[Observation, ...] = field(repr=False)
    pages: tuple[VerifiedPage, ...]


def _evidence(
    document: dict[str, object], observations: tuple[Observation, ...], result: MetricResult
) -> list[dict[str, object]]:
    """Cite every stored observation of the buyer's records and of the ambiguous ones."""
    records = {
        cast(int, row["observation_id"]): row
        for row in cast(list[dict[str, object]], document["records"])
    }
    decisions = {row.source_id: row for row in result.records}
    evidence: list[dict[str, object]] = []
    for observation in observations:
        decision = decisions.get(observation.source_id)
        ambiguous = observation.source_id in result.ambiguous_source_ids
        if decision is None and not ambiguous:
            continue
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
                "reported_buyer_key": observation.buyer_key,
                "cancelled": observation.cancelled,
                "reported_suppliers": None
                if observation.suppliers is None
                else [asdict(supplier) for supplier in observation.suppliers],
                "resolution": None if decision is None else decision.resolution,
                "selection": "ambiguous_source"
                if decision is None
                else selection_label(observation.observation_id, (decision.observation_ids, False)),
            }
        )
    return evidence


def _body(
    request: BuyerRequest,
    document: dict[str, object],
    observations: tuple[Observation, ...],
    result: MetricResult,
    pages: tuple[VerifiedPage, ...],
) -> bytes:
    policy = definition()
    return encode_artifact(
        {
            "version": "nima-buyer-concentration-v1",
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
                "projection": "reconciled_against_archived_records",
                "identity": "reported_identifier_only",
                "coverage": "selected_complete_runs_only",
                "source_current": "not_established",
                "lineage": "record_to_original_not_field_level",
            },
            "interpretation_limits": [
                "Counts distinct captured contract-publication records, not awards or payments.",
                "A record with several suppliers counts once for each, so counts overlap.",
                "Shares are of captured records, never of money or of the market.",
                "Reported identifiers do not establish legal company identity.",
                "Selected complete runs do not establish national or market completeness.",
                "Latest observed revisions are not verified source-current revisions.",
            ],
            "verified_pages": [{**asdict(page), "run_id": str(page.run_id)} for page in pages],
            "evidence": _evidence(document, observations, result),
        }
    )


def prepare_buyer_result(dsn: str, request: BuyerRequest) -> PreparedBuyerReadout:
    """Reconstruct and validate without publishing or writing SQL/source evidence."""
    try:
        cohort = read_cohort(dsn, request.run_ids)
        pages, _ = verify_pages(cohort.document, request.archive_bindings)
        result = evaluate(
            cohort.observations, buyer=request.buyer, cutoff=request.observation_cutoff
        )
        require_sql_parity(
            dsn,
            reference_sql(),
            sql_rows(cohort.observations),
            (request.observation_cutoff, request.buyer),
            result.payload(),
        )
        return PreparedBuyerReadout(
            _body(request, cohort.document, cohort.observations, result, pages),
            result,
            encode(cohort.document).decode("utf-8"),
            cohort.observations,
            pages,
        )
    except ReadoutError:
        raise
    except (SnapshotError, ReconciliationError, RequestError) as error:
        raise ReadoutError(error.reason) from None
    except PilotArchiveError:
        raise ReadoutError("analytics_archive") from None
    except SemanticError:
        raise ReadoutError("analytics_input") from None
    except (KeyError, TypeError, ValueError, IndexError):
        raise ReadoutError("analytics_evidence") from None
    except OSError:
        raise ReadoutError("analytics_output") from None


def prepare_buyer_readout(dsn: str, request: BuyerRequest) -> tuple[bytes, MetricResult]:
    """Preserve the original tuple API and report bytes."""
    prepared = prepare_buyer_result(dsn, request)
    return prepared.body, prepared.metric


def export_buyer_readout(dsn: str, request_file: Path, output_directory: Path) -> BuyerExport:
    """No network, SQL writes or original repair; validate fully before publication."""
    try:
        request = read_buyer_request(request_file)
        body, result = prepare_buyer_readout(dsn, request)
        digest = publish(output_directory, body)
        return BuyerExport(digest, result.buyer_records, result.distinct_suppliers, result.status)
    except RequestError as error:
        raise ReadoutError(error.reason) from None
    except AssessmentError as error:
        raise ReadoutError(
            "analytics_limit" if error.reason == "assessment_limit" else "analytics_output"
        ) from None
    except OSError:
        raise ReadoutError("analytics_output") from None
