"""Read, freeze, verify and privately publish one bounded supplier/buyer readout."""

from dataclasses import dataclass
from pathlib import Path

from nima.analytics.reconcile import ReconciliationError, reconcile
from nima.analytics.request import RequestError, read_request
from nima.analytics.result import ReadoutError, build_result
from nima.analytics.snapshot import SnapshotError, read_snapshot
from nima.identity import AssessmentError
from nima.identity.artifacts import publish


@dataclass(frozen=True)
class ReadoutExport:
    artifact_sha256: str
    record_count: int
    buyer_count: int
    outcome: str


def export_readout(dsn: str, request_file: Path, output_directory: Path) -> ReadoutExport:
    """No network, SQL writes or original repair; validate fully before publication."""
    try:
        request = read_request(request_file)
        snapshot = read_snapshot(
            dsn, request.run_ids, tax_id=request.supplier_tax_id, cutoff=request.observation_cutoff
        )
        verified = reconcile(snapshot, request)
        body = build_result(verified)
        digest = publish(output_directory, body)
        return ReadoutExport(
            digest, snapshot.metric.total, len(snapshot.metric.buyers), snapshot.metric.status
        )
    except (RequestError, SnapshotError, ReconciliationError) as error:
        raise ReadoutError(error.reason) from None
    except AssessmentError as error:
        raise ReadoutError(
            "analytics_limit" if error.reason == "assessment_limit" else "analytics_output"
        ) from None
    except OSError:
        raise ReadoutError("analytics_output") from None
