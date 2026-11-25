"""Reconcile the entire declared two-source cohort against immutable original bytes."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from nima.analytics.citation_request import CitationRequest
from nima.analytics.citation_snapshot import read_citation_snapshot
from nima.analytics.metric_readout import cohort_hash
from nima.analytics.run_facts import read_run_facts
from nima.analytics.snapshot import SnapshotError
from nima.graph.pilot_archive import PilotArchiveError, RawReference, recover
from nima.identity.artifacts import encode
from nima.semantics.citations import ContractObservation, DecisionObservation, validate_observations
from nima.semantics.lifecycle import Reference
from nima.sources.base import NormalizedPage, SourcePageError
from nima.storage.connection import Connection


@dataclass(frozen=True)
class CitationCohort:
    contracts: tuple[ContractObservation, ...]
    decisions: tuple[DecisionObservation, ...]
    captures: tuple[dict[str, object], ...]
    pages: tuple[dict[str, object], ...]
    evidence: tuple[dict[str, object], ...]
    cohort_sha256: str


def _page(
    page: NormalizedPage,
    body: bytes,
    stored: dict[str, object],
    run: dict[str, object],
    records: list[dict[str, object]],
    issues: list[dict[str, object]],
) -> None:
    actual = (
        page.number,
        len(body),
        page.response_sha256,
        page.record_count,
        len(page.issues),
        list(page.source_ids),
        page.total_records,
        page.total_pages,
        page.size,
    )
    expected = (
        stored["page_number"],
        stored["byte_length"],
        stored["raw_sha256"],
        stored["record_count"],
        stored["quarantined_count"],
        stored["source_ids"],
        run["total_records"],
        run["total_pages"],
        run["page_size"],
    )
    normalized = [
        (
            r["record_index"],
            r["source_id"],
            r["normalizer_version"],
            r["content_sha256"],
            r["normalized"],
        )
        for r in records
    ]
    recomputed = [
        (r.index, r.source_id, run["normalizer_version"], r.content_sha256, dict(r.normalized))
        for r in page.records
    ]
    quarantined = [(q["record_index"], q["reason"]) for q in issues]
    expected_issues = [(q.index, q.reason) for q in page.issues]
    if (
        encode(actual) != encode(expected)
        or encode(normalized) != encode(recomputed)
        or encode(quarantined) != encode(expected_issues)
    ):
        raise SnapshotError("citation_evidence")


def read_verified_citation_cohort(
    connection: Connection, request: CitationRequest
) -> CitationCohort:
    """Caller owns the restricted read snapshot; verify every page before selecting citations."""
    document, adapters = read_citation_snapshot(connection, request)
    runs = cast(list[dict[str, object]], document["runs"])
    pages = cast(list[dict[str, object]], document["pages"])
    records = cast(list[dict[str, object]], document["records"])
    issues = cast(list[dict[str, object]], document["quarantine"])
    runs_by_id = {cast(str, r["run_id"]): r for r in runs}
    for run in runs:
        numbers = [p["page_number"] for p in pages if p["run_id"] == run["run_id"]]
        if numbers != list(range(cast(int, run["next_page"]))):
            raise SnapshotError("citation_evidence")
    bindings = {str(b.run_id): b for b in request.archive_bindings}
    references = tuple(
        RawReference(
            bindings[cast(str, p["run_id"])].source,
            UUID(cast(str, p["run_id"])),
            cast(str, p["raw_sha256"]),
        )
        for p in pages
    )
    bodies: dict[tuple[str, str], bytes] = {}
    if references:
        used = {r.run_id for r in references}
        try:
            recovery = recover(
                references, tuple(b for b in request.archive_bindings if b.run_id in used)
            )
        except PilotArchiveError as error:
            raise SnapshotError(
                "citation_limit" if error.reason == "pilot_limit" else "citation_evidence"
            ) from None
        bodies = {
            (str(r.run_id), r.raw_sha256): obj.body
            for obj in recovery.objects
            for r in obj.references
        }
    contracts: list[ContractObservation] = []
    decisions: list[DecisionObservation] = []
    evidence: list[dict[str, object]] = []
    verified: list[dict[str, object]] = []
    verified_records = verified_issues = 0
    for stored in pages:
        run_id = cast(str, stored["run_id"])
        adapter, run = adapters[run_id], runs_by_id[run_id]
        body = bodies[run_id, cast(str, stored["raw_sha256"])]
        try:
            page = adapter.normalize_page(body)
        except SourcePageError:
            raise SnapshotError("citation_evidence") from None
        members = sorted(
            (
                r
                for r in records
                if (r["run_id"], r["page_number"]) == (run_id, stored["page_number"])
            ),
            key=lambda r: cast(int, r["record_index"]),
        )
        quarantines = [
            q for q in issues if (q["run_id"], q["page_number"]) == (run_id, stored["page_number"])
        ]
        _page(page, body, stored, run, members, quarantines)
        verified_records += len(members)
        verified_issues += len(quarantines)
        verified.append({**stored, "source": adapter.name})
        prefix = "/content/" if adapter.name == "kimdis" else "/decisions/"
        observed = datetime.fromisoformat(cast(str, stored["observed_at"]))
        for parsed, member in zip(page.records, members, strict=True):
            if parsed.evidence_pointer != prefix + str(parsed.index):
                raise SnapshotError("citation_evidence")
            observation_id = cast(int, member["observation_id"])
            normalizer = cast(str, run["normalizer_version"])
            identity = (
                observation_id,
                parsed.source_id,
                normalizer,
                parsed.content_sha256,
                observed,
            )
            normalized = parsed.normalized
            if adapter.name == "kimdis":
                refs = cast(list[dict[str, str]], normalized["references"])
                contracts.append(
                    ContractObservation(
                        *identity,
                        tuple(
                            Reference(r["relation"], r["target_id"], r["source_field"])
                            for r in refs
                        ),
                        cast(bool | None, normalized["cancelled"]),
                    )
                )
                fields = {
                    "diavgeiaADA": {
                        "json_pointer": parsed.evidence_pointer + "/diavgeiaADA",
                        "value_status": "reported"
                        if any(r["relation"] == "commitment_decision" for r in refs)
                        else "not_reported",
                    }
                }
            else:
                decisions.append(
                    DecisionObservation(
                        *identity,
                        cast(str, normalized["ada"]),
                        cast(str | None, normalized["decision_type"]),
                        cast(str, normalized["status"]),
                    )
                )
                fields = {
                    name: {
                        "json_pointer": parsed.evidence_pointer + "/" + name,
                        "value_status": "unknown"
                        if name == "decisionTypeId" and normalized["decision_type"] is None
                        else "reported",
                    }
                    for name in ("ada", "decisionTypeId", "status")
                }
            evidence.append(
                {
                    "observation_id": observation_id,
                    "source": adapter.name,
                    "source_id": parsed.source_id,
                    "normalizer_version": normalizer,
                    "content_sha256": parsed.content_sha256,
                    "observed_at": observed.isoformat(),
                    "run_id": run_id,
                    "page_number": stored["page_number"],
                    "record_index": parsed.index,
                    "raw_sha256": stored["raw_sha256"],
                    "json_pointer": parsed.evidence_pointer,
                    "field_locations": fields,
                }
            )
    if verified_records != len(records) or verified_issues != len(issues):
        raise SnapshotError("citation_evidence")
    validate_observations(tuple(contracts), tuple(decisions))
    facts = read_run_facts(connection, request.run_ids)
    captures = []
    for run in runs:
        run_id = cast(str, run["run_id"])
        fact, adapter = facts[UUID(run_id)], adapters[run_id]
        has_pages = any(p["run_id"] == run_id for p in pages)
        days = sorted(
            {
                datetime.fromisoformat(cast(str, p["observed_at"])).date().isoformat()
                for p in pages
                if p["run_id"] == run_id
            }
        )
        publisher = "Diavgeia (diavgeia.gov.gr)" if adapter.name == "diavgeia" else "KIMDIS"
        statements = [f"Source: {publisher}, CC BY 4.0; data retrieved on {day}" for day in days]
        captures.append(
            {
                "run_id": run_id,
                "source": adapter.name,
                "connector_version": adapter.connector_version,
                "normalizer_version": adapter.normalizer_version,
                "query": run["query"],
                "query_sha256": fact.query_sha256,
                "reported_total_records": run["total_records"],
                "reported_total_pages": run["total_pages"],
                "reported_page_size": run["page_size"],
                "committed_page_count": sum(p["run_id"] == run_id for p in pages),
                "normalized_observations": sum(r["run_id"] == run_id for r in records),
                "status": run["status"],
                "collection_complete": fact.collection_complete,
                "normalization_complete": fact.normalization_complete,
                "quarantined_count": fact.quarantined,
                "observed_from": fact.observed_from.isoformat() if has_pages else None,
                "observed_to": fact.observed_to.isoformat() if has_pages else None,
                "source_attribution": {
                    "documentation_url": adapter.provenance.documentation_url,
                    "license": adapter.provenance.license,
                    "statements": statements,
                },
            }
        )
    return CitationCohort(
        tuple(contracts),
        tuple(decisions),
        tuple(captures),
        tuple(verified),
        tuple(sorted(evidence, key=lambda e: cast(int, e["observation_id"]))),
        cohort_hash(document),
    )
