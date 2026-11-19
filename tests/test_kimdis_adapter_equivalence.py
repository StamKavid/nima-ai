"""The adapter must describe exactly what the current page store already writes.

Slice S3 will make the engine store the adapter's output. Until then this proves the two are
identical for real pages written through the real store, so the switch cannot change a byte.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from nima.sources.kimdis import KimdisAdapter
from nima.storage.postgres import migrate
from tests.test_collection import QUERY, body
from tests.test_kimdis_pages import page_body
from tests.test_page_store import store
from tests.test_participation import joint_record

PAGES = [
    pytest.param([page_body(joint_record())], id="joint-supplier-money"),
    pytest.param([body(page=0, total=2), body(page=1, total=2)], id="two-pages"),
    pytest.param([body(total=1, title=42)], id="quarantined-record"),
    pytest.param(
        [
            page_body(
                joint_record(),
                {"referenceNumber": "X", "title": 7},
                {**joint_record(), "referenceNumber": "26SYMV000000002"},
            )
        ],
        id="mixed-valid-and-bad",
    ),
]


@pytest.mark.parametrize("raw_pages", PAGES)
def test_adapter_output_equals_what_the_page_store_persists(
    pg_dsn: str, tmp_path: Path, raw_pages: list[bytes]
) -> None:
    migrate(pg_dsn)
    adapter = KimdisAdapter(QUERY)
    run = uuid4()
    database = store(pg_dsn, tmp_path / "raw")
    database.start_run(run, QUERY)
    for raw in raw_pages:
        database.commit_page(run, raw, observed_at=datetime.now(UTC))
    with psycopg.connect(pg_dsn) as c:
        for number, raw in enumerate(raw_pages):
            page = adapter.normalize_page(raw)
            assert c.execute(
                "SELECT record_count, quarantined_count, source_ids FROM nima.run_pages "
                "WHERE run_id=%s AND page_number=%s",
                (run, number),
            ).fetchone() == (page.record_count, len(page.issues), list(page.source_ids))
            observed = c.execute(
                "SELECT o.record_index, o.source_id, o.content_sha256, v.normalized "
                "FROM nima.observations o JOIN nima.record_versions v USING "
                "(source_id, normalizer_version, content_sha256) "
                "WHERE o.run_id=%s AND o.page_number=%s ORDER BY o.record_index",
                (run, number),
            ).fetchall()
            assert [
                (r.index, r.source_id, r.content_sha256, json.loads(json.dumps(r.normalized)))
                for r in page.records
            ] == [(i, sid, digest, value) for i, sid, digest, value in observed]
            assert c.execute(
                "SELECT record_index, reason FROM nima.quarantine "
                "WHERE run_id=%s AND page_number=%s ORDER BY record_index",
                (run, number),
            ).fetchall() == [(i.index, i.reason) for i in page.issues]
