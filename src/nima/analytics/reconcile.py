"""Verify every selected original against frozen SQL, never repair or fetch it."""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import cast
from uuid import UUID

from nima.analytics.request import ReadoutRequest, RequestError, decode_request
from nima.analytics.snapshot import ReadoutSnapshot, SnapshotError, validate_snapshot
from nima.graph.pilot_archive import PilotArchiveError, RawReference, recover
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.projections.contracts import project_contract
from nima.semantics.participation import definition
from nima.sources.kimdis import normalize_page


class ReconciliationError(ValueError):
    """Fixed reason only; archive paths, source values and driver details are private."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class VerifiedPage:
    run_id: UUID
    page_number: int
    raw_sha256: str
    byte_length: int
    observed_at: str
    record_count: int


@dataclass(frozen=True)
class ReconciledReadout:
    snapshot: ReadoutSnapshot
    request_json: str
    request_sha256: str
    definition_json: str
    definition_sha256: str
    pages: tuple[VerifiedPage, ...]


def _request(request: ReadoutRequest) -> None:
    if not isinstance(request, ReadoutRequest):
        raise ReconciliationError("analytics_input")
    body = encode(
        {
            **request.semantic_payload(),
            "archive_bindings": [
                {"run_id": str(binding.run_id), "root": str(binding.root)}
                for binding in request.archive_bindings
            ],
        }
    )
    if decode_request(body) != request:
        raise ReconciliationError("analytics_input")


def _page(
    body: bytes,
    stored: dict[str, object],
    run: dict[str, object],
    records: list[dict[str, object]],
) -> VerifiedPage:
    page = normalize_page(body)
    actual_shape = (
        len(body),
        page.number,
        page.record_count,
        page.source_ids,
        page.total_records,
        page.total_pages,
        page.size,
    )
    stored_shape = (
        stored["byte_length"],
        stored["page_number"],
        stored["record_count"],
        stored["source_ids"],
        run["total_records"],
        run["total_pages"],
        run["page_size"],
    )
    if page.issues or encode(actual_shape) != encode(stored_shape):
        raise ReconciliationError("analytics_evidence")
    members = {
        record["record_index"]: record
        for record in records
        if (record["run_id"], record["page_number"]) == (stored["run_id"], stored["page_number"])
    }
    if len(members) != page.record_count:
        raise ReconciliationError("analytics_evidence")
    for contract in page.contracts:
        index = int(contract.evidence.json_pointer.rsplit("/", 1)[1])
        record = members[index]
        normalized = asdict(contract)
        del normalized["evidence"]
        for field in ("net_amount", "gross_amount"):
            if normalized[field] is not None:
                normalized[field] = str(normalized[field])
        if (
            type(record["record_index"]) is not int
            or type(record["page_number"]) is not int
            or contract.source_id != record["source_id"]
            or page.record_hashes[index] != record["content_sha256"]
            or contract.evidence.response_sha256 != stored["raw_sha256"]
            or contract.evidence.json_pointer != f"/content/{index}"
            or encode(normalized) != encode(record["normalized"])
        ):
            raise ReconciliationError("analytics_evidence")
        projection = project_contract(json.loads(encode(normalized)))
        if (
            projection.digest()
            != cast(dict[str, object], record["projection"])["projection_sha256"]
        ):
            raise ReconciliationError("analytics_evidence")
    return VerifiedPage(
        UUID(cast(str, stored["run_id"])),
        page.number,
        cast(str, stored["raw_sha256"]),
        len(body),
        cast(str, stored["observed_at"]),
        page.record_count,
    )


def reconcile(snapshot: ReadoutSnapshot, request: ReadoutRequest) -> ReconciledReadout:
    """Verify originals at read time; this establishes no publisher/legal truth."""
    try:
        _request(request)
        policy = definition()
        policy_hash = hashlib.sha256(
            json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        document = validate_snapshot(
            snapshot,
            request.run_ids,
            tax_id=request.supplier_tax_id,
            cutoff=request.observation_cutoff,
            expected_definition_sha256=policy_hash,
        )
        pages = cast(list[dict[str, object]], document["pages"])
        records = cast(list[dict[str, object]], document["records"])
        runs = {run["run_id"]: run for run in cast(list[dict[str, object]], document["runs"])}
        references = tuple(
            RawReference("kimdis", UUID(cast(str, page["run_id"])), cast(str, page["raw_sha256"]))
            for page in pages
        )
        recovered = recover(references, request.archive_bindings)
        bodies = {
            (str(ref.run_id), ref.raw_sha256): obj.body
            for obj in recovered.objects
            for ref in obj.references
        }
        verified = tuple(
            _page(
                bodies[cast(str, page["run_id"]), cast(str, page["raw_sha256"])],
                page,
                runs[page["run_id"]],
                records,
            )
            for page in pages
        )
        return ReconciledReadout(
            snapshot,
            encode(request.semantic_payload()).decode(),
            request.request_sha256,
            encode(policy).decode(),
            policy_hash,
            verified,
        )
    except PilotArchiveError as error:
        raise ReconciliationError(
            "analytics_limit" if error.reason == "pilot_limit" else "analytics_archive"
        ) from None
    except (RequestError, SnapshotError) as error:
        raise ReconciliationError(error.reason) from None
    except AssessmentError:
        raise ReconciliationError("analytics_limit") from None
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        if isinstance(error, ReconciliationError):
            raise
        raise ReconciliationError("analytics_evidence") from None
