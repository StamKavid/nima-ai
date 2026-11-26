"""Controlled producer frames for pure mapping tests, not a verification bypass."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from nima.analytics.export import PreparedReadout
from nima.analytics.metric_readout import cohort_hash, definition_hash
from nima.analytics.reconcile import ReconciledReadout, VerifiedPage
from nima.analytics.request import ReadoutRequest
from nima.analytics.result import build_result
from nima.analytics.snapshot import ReadoutSnapshot
from nima.graph.pilot_archive import ArchiveBinding
from nima.identity.artifacts import encode
from nima.semantics import participation as model
from tests.test_semantics import TAX

CUTOFF = datetime(2026, 1, 10, tzinfo=UTC)


def observation(number: int = 1) -> model.Observation:
    return model.Observation(
        number,
        "kimdis:S",
        "kimdis-normalized-v1",
        "a" * 64,
        datetime(2026, 1, 1, tzinfo=UTC),
        "B",
        False,
        (model.Supplier(0, TAX, "GR"),),
    )


def producer(
    rows: tuple[model.Observation, ...], *, definition: dict[str, object] | None = None
) -> tuple[ReadoutRequest, PreparedReadout]:
    ids = tuple(UUID(int=i + 1) for i in range(max(1, len(rows))))
    request = ReadoutRequest(
        ids, CUTOFF, TAX, tuple(ArchiveBinding("kimdis", r, Path("/unused") / str(r)) for r in ids)
    )
    runs = []
    pages = []
    records = []
    verified = []
    for index, run in enumerate(ids):
        row = rows[index] if rows else None
        count = int(row is not None)
        runs.append(
            {
                "run_id": str(run),
                "query": {},
                "connector_version": "kimdis-contract-v1",
                "normalizer_version": "kimdis-normalized-v1",
                "status": "complete",
                "managed": True,
                "next_page": 1,
                "total_records": count,
                "total_pages": count,
                "page_size": 1,
                "quarantine_count": 0,
            }
        )
        observed = (row.observed_at if row is not None else CUTOFF).isoformat()
        pages.append(
            {
                "run_id": str(run),
                "page_number": 0,
                "raw_sha256": "b" * 64,
                "byte_length": 1,
                "observed_at": observed,
                "record_count": count,
            }
        )
        verified.append(VerifiedPage(run, 0, "b" * 64, 1, observed, count))
        if row is not None:
            records.append(
                {
                    "observation_id": row.observation_id,
                    "source_id": row.source_id,
                    "normalizer_version": row.normalizer_version,
                    "content_sha256": row.content_sha256,
                    "run_id": str(run),
                    "page_number": 0,
                    "record_index": 0,
                    "normalized": {"private_name": "DO_NOT_EXPORT", "private_tax": TAX},
                    "projection": {
                        "projection_version": "kimdis-participation-v1",
                        "projection_sha256": "d" * 64,
                    },
                }
            )
    meta = model.definition() if definition is None else definition
    document = {"runs": runs, "pages": pages, "records": records}
    identity: dict[str, object] = {
        "document": document,
        "run_ids": [str(r) for r in ids],
        "tax_id": TAX,
        "country": "GR",
        "cutoff": CUTOFF.isoformat(),
        "definition_sha256": definition_hash(meta),
    }
    snapshot = ReadoutSnapshot(
        encode(document).decode(),
        rows,
        model.evaluate(rows, tax_id=TAX, cutoff=CUTOFF),
        cohort_hash(identity),
    )
    reconciled = ReconciledReadout(
        snapshot,
        encode(request.semantic_payload()).decode(),
        request.request_sha256,
        encode(meta).decode(),
        definition_hash(meta),
        tuple(verified),
    )
    return request, PreparedReadout(build_result(reconciled), snapshot)
