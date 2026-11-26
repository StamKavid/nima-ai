"""Controlled U2 producer frames for mapping tests; these do not verify evidence."""

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from nima.analytics.cpv_readout import PreparedCpvReadout
from nima.analytics.cpv_request import CpvRequest
from nima.analytics.metric_readout import cohort_hash, definition_hash, selection_label
from nima.analytics.reconcile import VerifiedPage
from nima.graph.pilot_archive import ArchiveBinding
from nima.identity.artifacts import encode
from nima.semantics import cpv_period as model

CUTOFF = datetime(2026, 6, 1, tzinfo=UTC)


def request_file(request: CpvRequest, path: Path) -> Path:
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


def observation(number: int = 1) -> model.Observation:
    return model.Observation(
        number,
        "kimdis:PRIVATE_ID",
        "kimdis-normalized-v1",
        "a" * 64,
        datetime(2026, 1, 1, tzinfo=UTC),
        False,
        "2026-03-10T08:00:00.123",
        (model.CpvAssertion("reported", "45000000-7"),),
    )


def producer(
    rows: tuple[model.Observation, ...],
    *,
    definition: dict[str, object] | None = None,
    **selection: Any,
) -> tuple[CpvRequest, PreparedCpvReadout]:
    ids = tuple(UUID(int=i + 1) for i in range(max(1, len(rows))))
    request = CpvRequest(
        ids,
        CUTOFF,
        tuple(ArchiveBinding("kimdis", r, Path("/unused") / str(r)) for r in ids),
        **selection,
    )
    runs, pages, records, verified, evidence = [], [], [], [], []
    result = model.evaluate(rows, cutoff=CUTOFF, **selection)
    decisions = {r.source_id: r for r in result.records}
    for index, run in enumerate(ids):
        row = rows[index] if rows else None
        count = int(row is not None)
        observed = (row.observed_at if row else CUTOFF).isoformat()
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
        page = VerifiedPage(run, 0, "b" * 64, 1, observed, count)
        pages.append({**asdict(page), "run_id": str(run)})
        verified.append(page)
        if row is not None:
            key = {
                "observation_id": row.observation_id,
                "source_id": row.source_id,
                "normalizer_version": row.normalizer_version,
                "content_sha256": row.content_sha256,
                "run_id": str(run),
                "page_number": 0,
            }
            records.append(
                {
                    **key,
                    "record_index": 0,
                    "normalized": {
                        "private_name": "DO_NOT_EXPORT",
                        "private_tax": "012345678",
                    },
                }
            )
            decision = decisions.get(row.source_id)
            evidence.append(
                {
                    **key,
                    "json_pointer": "/content/0",
                    "observed_at": observed,
                    "reported_submission_text": row.submitted_text,
                    "cancelled": row.cancelled,
                    "cpv_assertions": [
                        {**asdict(a), "json_pointer": "/content/0/objectDetailsList"}
                        for a in row.cpv or ()
                    ],
                    "selection": selection_label(
                        row.observation_id,
                        None
                        if decision is None
                        else (decision.observation_ids, decision.ambiguous),
                    ),
                }
            )
    document: dict[str, object] = {"runs": runs, "pages": pages, "records": records}
    meta = model.definition() if definition is None else definition
    body = {
        "version": "nima-cpv-period-v1",
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
            "cpv": "re_extracted_from_archived_bytes_not_checked_against_taxonomy",
            "coverage": "selected_complete_runs_only",
            "source_current": "not_established",
            "lineage": "record_to_original_not_field_level",
        },
        "interpretation_limits": ["Synthetic producer frame; no original verification."],
        "verified_pages": pages,
        "evidence": evidence,
    }
    return request, PreparedCpvReadout(
        encode(body), result, encode(document).decode(), rows, tuple(verified)
    )
