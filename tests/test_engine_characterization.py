"""Pins what the acquisition engine writes today, so moving it onto the adapter protocol cannot
change a stored or archived byte.

Three real collections run through the real engine (mock transport, no network): clean pages, a
quarantined record, and a joint-supplier record with exact money. For each, every deterministic
output is fingerprinted: database rows, the archive sidecar files, and the replay artifact. Run
IDs, timestamps and paths are excluded. The expected hashes were recorded from the engine before
slice S3 and must not change; if one changes, stored evidence changed.
"""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import httpx
import psycopg
import pytest

from nima.dataops.replay import prepare_replay
from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from nima.storage.postgres import NORMALIZER_VERSION, migrate
from tests.test_collection import QUERY, Clock, body
from tests.test_kimdis_pages import page_body
from tests.test_participation import joint_record

SCENARIOS: dict[str, list[bytes]] = {
    "clean-three-pages": [body(page=n, total=3) for n in range(3)],
    "quarantined-record": [body(total=1, title=42)],
    "joint-supplier-money": [page_body(joint_record())],
}

# Recorded from the engine on main bb99485, before the engine used the adapter protocol.
EXPECTED = {
    "clean-three-pages": "4f738aa3efcec128dcd081127b8b8f4ffd534b86e084454dd51823927bb2c010",
    "quarantined-record": "f46da2f34d24ee765141b5b5a4857de0250f005e9168fe98921ff06ca2862512",
    "joint-supplier-money": "f9c72a7db7b3cfe145ab9cf76b7b7c80d97e66c10faaa6c9f32c66a4e51c2663",
}


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def fingerprint(dsn: str, root: Path, raw_pages: list[bytes]) -> dict[str, object]:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=raw_pages[int(request.url.params["page"])])
    )
    with httpx.Client(transport=transport) as client:
        summary = collect(
            QUERY, Limits(), Archive(root), client=client, clock=Clock(), database_dsn=dsn
        )
    run = UUID(summary.run_id)
    with psycopg.connect(dsn) as c:
        rows = {
            "ingest_run": c.execute(
                "SELECT connector_version, normalizer_version, query, next_page, total_records, "
                "total_pages, page_size, status FROM nima.ingest_runs WHERE run_id=%s",
                (run,),
            ).fetchall(),
            "raw_objects": c.execute(
                "SELECT sha256, byte_length FROM nima.raw_objects ORDER BY sha256"
            ).fetchall(),
            "run_pages": c.execute(
                "SELECT page_number, raw_sha256, record_count, quarantined_count, source_ids "
                "FROM nima.run_pages WHERE run_id=%s ORDER BY page_number",
                (run,),
            ).fetchall(),
            "source_records": c.execute(
                "SELECT source_id FROM nima.source_records ORDER BY source_id"
            ).fetchall(),
            "record_versions": c.execute(
                "SELECT source_id, normalizer_version, content_sha256, normalized "
                "FROM nima.record_versions ORDER BY source_id, content_sha256"
            ).fetchall(),
            "observations": c.execute(
                "SELECT page_number, record_index, source_id, normalizer_version, content_sha256 "
                "FROM nima.observations WHERE run_id=%s ORDER BY page_number, record_index",
                (run,),
            ).fetchall(),
            "outbox": c.execute("SELECT count(*), count(delivered_at) FROM nima.outbox").fetchall(),
            "quarantine": c.execute(
                "SELECT page_number, record_index, reason FROM nima.quarantine "
                "WHERE run_id=%s ORDER BY page_number, record_index",
                (run,),
            ).fetchall(),
        }
    sidecars = {
        name: hashlib.sha256((root / "runs" / summary.run_id / name).read_bytes()).hexdigest()
        for name in ("normalized.jsonl", "quarantine.jsonl")
        if (root / "runs" / summary.run_id / name).exists()
    }
    artifact, replay = prepare_replay(dsn, run, root, NORMALIZER_VERSION)
    document = json.loads(artifact)
    del document["source_run"]["run_id"]  # random per run
    for page in document["pages"]:
        del page["observed_at"]  # wall-clock time of the observation
    summary_value = {k: v for k, v in vars(summary).items() if k not in {"run_id", "attempts"}}
    return {
        "summary": summary_value,
        "rows": rows,
        "sidecars": sidecars,
        "replay_artifact": document,
        "replay_counts": {k: v for k, v in vars(replay).items() if k != "artifact_sha256"},
    }


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_engine_output_is_byte_identical_to_the_recorded_pin(
    pg_dsn: str, tmp_path: Path, scenario: str
) -> None:
    migrate(pg_dsn)
    value = fingerprint(pg_dsn, tmp_path / "raw", SCENARIOS[scenario])
    assert digest(value) == EXPECTED[scenario], canonical(value)


def test_the_pin_covers_sidecars_replay_and_every_table(pg_dsn: str, tmp_path: Path) -> None:
    """Guards the pin against passing vacuously: the fingerprint must actually contain them."""
    migrate(pg_dsn)
    value = fingerprint(pg_dsn, tmp_path / "raw", SCENARIOS["joint-supplier-money"])
    sidecars = value["sidecars"]
    assert isinstance(sidecars, dict)
    assert set(sidecars) == {"normalized.jsonl", "quarantine.jsonl"}
    rows = value["rows"]
    assert isinstance(rows, dict)
    populated = {name for name, content in rows.items() if content}
    assert populated == set(rows) - {"quarantine"}
    document = value["replay_artifact"]
    assert isinstance(document, dict) and document["pages"][0]["records"]
    assert digest(value) == EXPECTED["joint-supplier-money"]


def test_the_quarantine_scenario_covers_the_quarantine_table(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    value = fingerprint(pg_dsn, tmp_path / "raw", SCENARIOS["quarantined-record"])
    rows = value["rows"]
    assert isinstance(rows, dict) and rows["quarantine"]
    counts = value["replay_counts"]
    assert isinstance(counts, dict) and counts["quarantined_count"] == 1


def test_distinct_scenarios_have_distinct_pins() -> None:
    assert len(set(EXPECTED.values())) == len(EXPECTED)
