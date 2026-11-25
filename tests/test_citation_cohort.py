"""Two-source ledger/normalizer/original parity on disposable PostgreSQL and private files."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.analytics.citation_cohort import read_verified_citation_cohort
from nima.analytics.citation_request import CitationRequest, decode_citation_request
from nima.analytics.snapshot import SnapshotError, connected
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.sources.base import SourceAdapter
from nima.sources.diavgeia import DiavgeiaQuery
from nima.sources.diavgeia_commitments import CommitmentQuery
from nima.sources.registry import adapter_for
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.diavgeia_samples import commitment, decision, search_page
from tests.test_analytics_snapshot import reader, state
from tests.test_collection import QUERY

OBSERVED = datetime(2026, 1, 1, tzinfo=UTC)


def test_encoder_can_only_tighten_the_existing_canonical_bound() -> None:
    value = {"z": "ε", "a": 1}
    original = encode(value)
    assert original == '{"a":1,"z":"ε"}'.encode()
    assert encode(value, limit=len(original)) == original
    for limit in [len(original) - 1, 0, True, 33 * 1024 * 1024]:
        with pytest.raises(AssessmentError, match="^assessment_limit$"):
            encode(value, limit=limit)


def add_run(
    dsn: str,
    root: Path,
    source: str,
    *,
    empty: bool = False,
    partial: bool = False,
    quarantined: bool = False,
    no_pages: bool = False,
    cites: bool = True,
    kind: str | None = "Β.1.3",
    observed: datetime = OBSERVED,
) -> UUID:
    adapter: SourceAdapter = adapter_for(source)
    query = (
        QUERY
        if source == "kimdis"
        else (
            DiavgeiaQuery("99999", "2026-01-01", "2026-01-02")
            if source == "diavgeia"
            else CommitmentQuery("99999", "2026-01-01", "2026-01-02")
        )
    )
    if source == "kimdis":
        content = (
            []
            if empty
            else [
                {
                    "referenceNumber": "C",
                    "diavgeiaADA": "ADA-1",
                    "title": "DO_NOT_EXPORT",
                    "totalCostWithoutVAT": "123.45",
                    "cancelled": False,
                }
            ]
        )
        raw = json.dumps(
            {
                "content": content,
                "number": 0,
                "size": 1,
                "totalElements": len(content),
                "totalPages": 0 if empty else 1,
                "last": True,
            }
        ).encode()
        if not cites:
            value = json.loads(raw)
            del value["content"][0]["diavgeiaADA"]
            raw = json.dumps(value).encode()
    else:
        rows = (
            []
            if empty
            else [
                decision(
                    "ADA-1",
                    decisionTypeId=kind,
                    subject="SUBJECT_DO_NOT_EXPORT",
                    extraFieldValues=commitment("456.78"),
                )
            ]
        )
        if quarantined:
            rows.append(decision("BAD", status="UNKNOWN"))
        raw = search_page(0, 2 if partial else len(rows), 1 if partial else 100, rows)
    run = uuid4()
    store = RunStore(dsn, Archive(root), run, Limits(), adapter)
    with store.lease():
        store.begin(query)
        if not no_pages:
            store.commit_page(run, raw, observed_at=observed, owner=store.owner)
        status = (
            "failed"
            if no_pages
            else "interrupted"
            if partial
            else "quarantined"
            if quarantined
            else "complete"
        )
        store.finish(Summary(status=status))
    return run


def seed(
    dsn: str,
    root: Path,
    *,
    source_no_pages: bool = False,
    source_cites: bool = True,
    **options: Any,
) -> CitationRequest:
    migrate(dsn)
    k = add_run(dsn, root / "kimdis", "kimdis", no_pages=source_no_pages, cites=source_cites)
    d = add_run(dsn, root / "diavgeia", "diavgeia-commitment", **options)
    return decode_citation_request(
        json.dumps(
            {
                "version": "nima-source-citations-request-v1",
                "kimdis_run_ids": [str(k)],
                "diavgeia_run_ids": [str(d)],
                "observation_cutoff": "2026-01-10T00:00:00Z",
                "archive_bindings": [
                    {"source": "kimdis", "run_id": str(k), "root": str(root / "kimdis")},
                    {"source": "diavgeia", "run_id": str(d), "root": str(root / "diavgeia")},
                ],
            }
        ).encode()
    )


def load(dsn: str, request: CitationRequest) -> Any:
    with reader(dsn) as (limited, _):
        return connected(limited, lambda c: read_verified_citation_cohort(c, request))


def tamper(dsn: str, statement: str) -> None:
    with psycopg.connect(dsn) as c:
        c.execute("SET LOCAL session_replication_role = replica")
        c.execute(statement)


def test_complete_sources_are_verified_without_projections_or_writes(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = seed(pg_dsn, tmp_path)
    before = state(pg_dsn)
    cohort = load(pg_dsn, request)
    assert [o.source_id for o in cohort.contracts] == ["kimdis:C"]
    assert [o.source_id for o in cohort.decisions] == ["diavgeia:ADA-1"]
    assert len(cohort.pages) == len(cohort.evidence) == 2
    assert all(c["collection_complete"] and c["normalization_complete"] for c in cohort.captures)
    assert {e["json_pointer"] for e in cohort.evidence} == {"/content/0", "/decisions/0"}
    assert state(pg_dsn) == before


@pytest.mark.parametrize("option", ["empty", "partial", "quarantined", "no_pages"])
def test_partial_quarantined_and_empty_captures_are_accounted(
    pg_dsn: str, tmp_path: Path, option: str
) -> None:
    request = seed(pg_dsn, tmp_path, **{option: True})
    cohort = load(pg_dsn, request)
    capture = next(c for c in cohort.captures if c["source"] == "diavgeia")
    assert capture["quarantined_count"] == int(option == "quarantined")
    assert capture["collection_complete"] == (option == "empty")
    assert len(cohort.decisions) == int(option in {"partial", "quarantined"})
    assert len(cohort.pages) == (1 if option == "no_pages" else 2)
    if option == "no_pages":
        assert capture["observed_from"] is capture["observed_to"] is None


@pytest.mark.parametrize(
    "statement",
    [
        """UPDATE nima.record_versions SET normalized=jsonb_set(normalized,'{status}','"REVOKED"')
        WHERE source_id='diavgeia:ADA-1'""",
        "UPDATE nima.observations SET record_index=9 WHERE source_id='diavgeia:ADA-1'",
        """UPDATE nima.run_pages SET record_count=2 WHERE run_id IN (
        SELECT run_id FROM nima.observations WHERE source_id='diavgeia:ADA-1')""",
        "DELETE FROM nima.observations WHERE source_id='diavgeia:ADA-1'",
    ],
)
def test_sql_cannot_disagree_with_originals(pg_dsn: str, tmp_path: Path, statement: str) -> None:
    request = seed(pg_dsn, tmp_path)
    tamper(pg_dsn, statement)
    with pytest.raises(SnapshotError, match="^citation_evidence$"):
        load(pg_dsn, request)
