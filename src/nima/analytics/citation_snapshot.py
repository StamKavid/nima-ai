"""Bounded ingestion-ledger facts on the caller's SELECT-only repeatable-read session."""

from typing import cast

from nima.analytics.citation_request import CitationRequest
from nima.analytics.snapshot import MAX_INPUT_BYTES, SnapshotError
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.sources.base import SourceAdapter
from nima.sources.registry import adapter_from_run
from nima.storage.connection import Connection

# Supported processing identities are explicit, independently of future registry additions.
PROFILES = {
    "kimdis-contract-v1": ("kimdis", "kimdis-normalized-v1"),
    "diavgeia-search-v1": ("diavgeia", "diavgeia-decision-v1"),
    "diavgeia-commitment-search-v1": ("diavgeia", "diavgeia-commitment-v1"),
}


def read_citation_snapshot(
    connection: Connection, request: CitationRequest
) -> tuple[dict[str, object], dict[str, SourceAdapter]]:
    """Read no projections; reject oversized normalized facts before JSON aggregation/fetch."""
    parameters = {"runs": list(request.run_ids)}
    counts = connection.execute(
        """SELECT
        (SELECT count(*) FROM nima.observations WHERE run_id=ANY(%(runs)s)),
        (SELECT count(*) FROM nima.run_pages WHERE run_id=ANY(%(runs)s)),
        (SELECT count(*) FROM nima.quarantine WHERE run_id=ANY(%(runs)s))""",
        parameters,
    ).fetchall()[0]
    if cast(int, counts[0]) > 5000 or cast(int, counts[1]) > 500 or cast(int, counts[2]) > 5000:
        raise SnapshotError("citation_limit")
    size = connection.execute(
        """SELECT coalesce(sum(octet_length(to_jsonb(o)::text) +
            coalesce(octet_length(v.normalized::text),0) + 20),0)
         FROM nima.observations o LEFT JOIN nima.record_versions v
            USING(source_id,normalizer_version,content_sha256)
         WHERE o.run_id=ANY(%(runs)s)""",
        parameters,
    ).fetchall()[0]
    if cast(int, size[0]) > MAX_INPUT_BYTES:
        raise SnapshotError("citation_limit")
    runs = connection.execute(
        """SELECT jsonb_build_object(
            'run_id',run_id,'query',query,'connector_version',connector_version,
            'normalizer_version',normalizer_version,'status',status,'next_page',next_page,
            'total_records',total_records,'total_pages',total_pages,'page_size',page_size)
        FROM nima.ingest_runs WHERE run_id=ANY(%(runs)s) ORDER BY run_id""",
        parameters,
    ).fetchall()
    pages = connection.execute(
        """SELECT to_jsonb(p) || jsonb_build_object('byte_length',b.byte_length)
        FROM nima.run_pages p LEFT JOIN nima.raw_objects b ON b.sha256=p.raw_sha256
        WHERE p.run_id=ANY(%(runs)s) ORDER BY p.run_id,p.page_number""",
        parameters,
    ).fetchall()
    records = connection.execute(
        """SELECT to_jsonb(o) || jsonb_build_object('normalized',v.normalized)
        FROM nima.observations o LEFT JOIN nima.record_versions v
            USING(source_id,normalizer_version,content_sha256)
        WHERE o.run_id=ANY(%(runs)s) ORDER BY o.observation_id""",
        parameters,
    ).fetchall()
    quarantines = connection.execute(
        """SELECT to_jsonb(q) FROM nima.quarantine q WHERE run_id=ANY(%(runs)s)
        ORDER BY q.run_id,q.page_number,q.record_index""",
        parameters,
    ).fetchall()
    document: dict[str, object] = {
        "runs": [r[0] for r in runs],
        "pages": [p[0] for p in pages],
        "records": [r[0] for r in records],
        "quarantine": [q[0] for q in quarantines],
    }
    try:
        encode(document, limit=MAX_INPUT_BYTES)
    except AssessmentError:
        raise SnapshotError("citation_limit") from None
    if [r["run_id"] for r in cast(list[dict[str, object]], document["runs"])] != [
        str(run) for run in request.run_ids
    ]:
        raise SnapshotError("citation_contract")
    adapters = {}
    for run in cast(list[dict[str, object]], document["runs"]):
        expected = (
            "kimdis" if run["run_id"] in {str(r) for r in request.kimdis_run_ids} else "diavgeia"
        )
        connector = cast(str, run["connector_version"])
        if PROFILES.get(connector) != (expected, run["normalizer_version"]):
            raise SnapshotError("citation_contract")
        try:
            adapter = adapter_from_run(connector, cast(dict[str, object], run["query"]))
        except (ValueError, TypeError):
            raise SnapshotError("citation_contract") from None
        if adapter.name != expected or adapter.normalizer_version != run["normalizer_version"]:
            raise SnapshotError("citation_contract")
        adapters[cast(str, run["run_id"])] = adapter
    return document, adapters
