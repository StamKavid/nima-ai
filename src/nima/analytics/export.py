"""Read, freeze, verify and privately publish one bounded supplier/buyer readout."""

from dataclasses import dataclass, field
from pathlib import Path

from nima.analytics.reconcile import ReconciliationError, reconcile
from nima.analytics.request import ReadoutRequest, RequestError, read_request
from nima.analytics.result import ReadoutError, build_result
from nima.analytics.snapshot import ReadoutSnapshot, SnapshotError, read_snapshot
from nima.contracts import ContractError, validate_output
from nima.identity import AssessmentError
from nima.identity.artifacts import publish


@dataclass(frozen=True)
class ReadoutExport:
    artifact_sha256: str
    record_count: int
    buyer_count: int
    outcome: str


@dataclass(frozen=True)
class PreparedReadout:
    body: bytes = field(repr=False)
    snapshot: ReadoutSnapshot = field(repr=False)


def prepare_readout(dsn: str, request: ReadoutRequest) -> PreparedReadout:
    """Reconstruct and validate without publishing or writing SQL/source evidence."""
    try:
        snapshot = read_snapshot(
            dsn, request.run_ids, tax_id=request.supplier_tax_id, cutoff=request.observation_cutoff
        )
        verified = reconcile(snapshot, request)
        body = build_result(verified)
        validate_output(
            body, metric=snapshot.metric.payload(), observation_count=len(snapshot.observations)
        )
        return PreparedReadout(body, snapshot)
    except (SnapshotError, ReconciliationError) as error:
        raise ReadoutError(error.reason) from None
    except ContractError:
        raise ReadoutError("analytics_contract") from None
    except AssessmentError as error:
        raise ReadoutError(
            "analytics_limit" if error.reason == "assessment_limit" else "analytics_output"
        ) from None
    except OSError:
        raise ReadoutError("analytics_output") from None


def export_readout(dsn: str, request_file: Path, output_directory: Path) -> ReadoutExport:
    """No network, SQL writes or original repair; validate fully before publication."""
    try:
        prepared = prepare_readout(dsn, read_request(request_file))
        digest = publish(output_directory, prepared.body)
        metric = prepared.snapshot.metric
        return ReadoutExport(digest, metric.total, len(metric.buyers), metric.status)
    except RequestError as error:
        raise ReadoutError(error.reason) from None
    except AssessmentError as error:
        raise ReadoutError(
            "analytics_limit" if error.reason == "assessment_limit" else "analytics_output"
        ) from None
    except OSError:
        raise ReadoutError("analytics_output") from None
