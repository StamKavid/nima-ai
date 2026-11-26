"""Controlled producer frames for U4 mapping, never original/SQL verification."""

from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from uuid import UUID

from nima.analytics.change_readout import PreparedChangeReadout
from nima.analytics.change_request import ChangeRequest
from nima.analytics.metric_readout import cohort_hash, definition_hash
from nima.analytics.reconcile import VerifiedPage
from nima.analytics.run_facts import query_sha256
from nima.graph.pilot_archive import ArchiveBinding
from nima.identity.artifacts import encode
from nima.semantics import observed_change as model
from tests.test_observed_change import example


def captures() -> tuple[model.Capture, model.Capture]:
    a, b = example()
    return (
        replace(
            a,
            runs=(
                replace(
                    a.runs[0],
                    run_id="00000000-0000-4000-8000-000000000001",
                    query_sha256=query_sha256({"fixture": "query"}),
                ),
            ),
        ),
        replace(
            b,
            runs=(
                replace(
                    b.runs[0],
                    run_id="00000000-0000-4000-8000-000000000002",
                    query_sha256=query_sha256({"fixture": "query"}),
                ),
            ),
        ),
    )


def request_file(request: ChangeRequest, path: Path) -> Path:
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


def producer(a: model.Capture, b: model.Capture) -> tuple[ChangeRequest, PreparedChangeReadout]:
    ids = tuple(UUID(r.run_id) for c in (a, b) for r in c.runs)
    request = ChangeRequest(
        tuple(UUID(r.run_id) for r in a.runs),
        tuple(UUID(r.run_id) for r in b.runs),
        tuple(ArchiveBinding("kimdis", i, Path("/private/fixture")) for i in sorted(ids)),
    )
    result = model.evaluate(a, b)
    incomparable = bool(result.reasons)
    rows: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}
    for label, c in (("earlier", a), ("later", b)):
        facts[label] = [
            {
                **asdict(r),
                "observed_from": r.observed_from.isoformat(),
                "observed_to": r.observed_to.isoformat(),
            }
            for r in c.runs
        ]
        for r in c.runs:
            runs.append(
                {
                    "run_id": r.run_id,
                    "query": {"fixture": "query"},
                    "next_page": max(1, len(c.versions)),
                    "total_records": len(c.versions),
                    "total_pages": len(c.versions),
                    "page_size": 1,
                    "connector_version": "kimdis-contract-v1",
                    "normalizer_version": "kimdis-normalized-v1",
                    "quarantine_count": r.quarantined,
                    "managed": True,
                    "status": "complete",
                }
            )
        if not c.versions and c.runs:
            r = c.runs[0]
            pages.append(
                {
                    "run_id": r.run_id,
                    "page_number": 0,
                    "raw_sha256": "f" * 64,
                    "byte_length": 100,
                    "record_count": 0,
                    "observed_at": r.observed_from.isoformat(),
                }
            )
        for index, v in enumerate(c.versions):
            page = {
                "run_id": c.runs[0].run_id,
                "page_number": index,
                "raw_sha256": "f" * 64,
                "byte_length": 100,
                "record_count": 1,
                "observed_at": v.observed_at.isoformat(),
            }
            pages.append(page)
            row = {
                "run_id": page["run_id"],
                "page_number": index,
                "record_index": 0,
                "observation_id": v.observation_id,
                "source_id": v.source_id,
                "content_sha256": v.content_sha256,
            }
            rows.append(row)
            evidence.append(
                {
                    "observation_id": v.observation_id,
                    "capture": label,
                    "source_id": v.source_id,
                    "content_sha256": v.content_sha256,
                    "run_id": page["run_id"],
                    "page_number": index,
                    "json_pointer": "/content/0",
                    "observed_at": v.observed_at.isoformat(),
                }
            )
    runs.sort(key=lambda r: r["run_id"])
    rows.sort(key=lambda r: r["observation_id"])
    evidence.sort(key=lambda r: r["observation_id"])
    cohort: dict[str, object] = {"runs": runs, "pages": pages, "records": rows}
    verified = (
        tuple(
            VerifiedPage(
                UUID(p["run_id"]),
                p["page_number"],
                p["raw_sha256"],
                p["byte_length"],
                p["observed_at"],
                p["record_count"],
            )
            for p in pages
        )
        if not incomparable
        else ()
    )
    if incomparable:
        a = replace(a, versions=())
        b = replace(b, versions=())
        result = model.evaluate(a, b)
    meta = model.definition()
    body = {
        "version": "nima-observed-change-v1",
        "source": "kimdis.contract",
        "metric": {
            "definition": meta,
            "definition_sha256": definition_hash(meta),
            "result": result.payload(),
        },
        "request": request.semantic_payload(),
        "request_sha256": request.request_sha256,
        "cohort_sha256": None if incomparable else cohort_hash(cohort),
        "run_facts": facts,
        "quality": {
            "completeness": "decided_from_stored_counters",
            "raw_bytes": "not_performed_incomparable"
            if incomparable
            else "verified_against_archived_bytes",
            "source_current": "not_established",
            "lineage": "record_to_original_not_field_level",
        },
        "interpretation_limits": ["Synthetic producer frame, no verification."],
        "verified_pages": [] if incomparable else pages,
        "evidence": [] if incomparable else evidence,
    }
    return request, PreparedChangeReadout(
        encode(body), result, None if incomparable else encode(cohort).decode(), a, b, verified
    )
