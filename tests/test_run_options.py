"""Saved run options are read back as plain data; no source's query type is rebuilt.

``load_run_options`` returns what a run was created with: the query payload, the connector version
that identifies its adapter, the limits and the archive root. The engine decides what to do with
the payload (rebuild an adapter through the registry); storage never builds a ``Query``.
"""

from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits
from nima.sources.base import QueryPayload
from nima.storage.postgres import CheckpointError, PageStore, migrate
from nima.storage.runs import RunStore, load_run_options
from tests.synthetic_sources import LedgerAdapter
from tests.test_collection import QUERY

LIMITS = Limits(max_pages=7, max_attempts=3, max_bytes=4096, requests_per_minute=12.5)


def create(dsn: str, root: Path, adapter_query: object | None = None) -> RunStore:
    run = uuid4()
    store = RunStore(dsn, Archive(root), run, LIMITS, LedgerAdapter() if adapter_query else None)
    with store.lease():
        store.begin(QueryPayload(LedgerAdapter().query_payload()) if adapter_query else QUERY)
    return store


def test_a_kimdis_run_reads_back_its_payload_identity_limits_and_archive(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    store = create(pg_dsn, tmp_path / "raw")
    options = load_run_options(pg_dsn, store.run_id)
    assert options.payload == QUERY.payload()
    assert options.connector_version == "kimdis-contract-v1"
    assert options.limits == LIMITS
    assert options.archive_root == tmp_path / "raw"


def test_a_run_of_another_source_reads_back_with_that_sources_identity(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    store = create(pg_dsn, tmp_path / "raw", adapter_query=True)
    options = load_run_options(pg_dsn, store.run_id)
    assert options.payload == LedgerAdapter().query_payload()
    assert options.connector_version == LedgerAdapter.connector_version
    assert options.archive_root == tmp_path / "raw"


def test_an_unknown_run_is_unavailable(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with pytest.raises(CheckpointError, match="Managed run not found"):
        load_run_options(pg_dsn, uuid4())


def insert(dsn: str, settings: object, query: object = None) -> UUID:
    run = uuid4()
    with psycopg.connect(dsn) as c:
        c.execute(
            "INSERT INTO nima.ingest_runs (run_id, query, connector_version, normalizer_version, "
            "archive_root, owner, settings, status) VALUES (%s, %s, 'x-v1', 'y-v1', '/a', %s, %s, "
            "'running')",
            (run, Jsonb(query if query is not None else {"k": 1}), uuid4(), Jsonb(settings)),
        )
    return run


GOOD = {
    "max_pages": 1,
    "max_attempts": 1,
    "max_bytes": 1,
    "requests_per_minute": 1.0,
    "request_timeout": 1.0,
    "run_timeout": 1.0,
    "max_retry_delay": 1.0,
}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"max_pages": "7"}, "Invalid saved integer limit"),
        ({"max_attempts": True}, "Invalid saved integer limit"),
        ({"max_bytes": 1.5}, "Invalid saved integer limit"),
        ({"requests_per_minute": "12"}, "Invalid saved numeric limit"),
        ({"run_timeout": None}, "Invalid saved numeric limit"),
        ({"max_retry_delay": True}, "Invalid saved numeric limit"),
    ],
)
def test_malformed_saved_limits_are_refused(
    pg_dsn: str, change: dict[str, object], message: str
) -> None:
    migrate(pg_dsn)
    run = insert(pg_dsn, {**GOOD, **change})
    with pytest.raises(CheckpointError, match=message):
        load_run_options(pg_dsn, run)


def test_a_run_that_was_never_managed_has_no_saved_options(pg_dsn: str, tmp_path: Path) -> None:
    """A run started through the page store alone has no saved limits, so it cannot be resumed."""
    migrate(pg_dsn)
    run = uuid4()
    PageStore(pg_dsn, Archive(tmp_path / "raw")).start_run(run, QUERY)
    with pytest.raises(CheckpointError, match="Managed run not found"):
        load_run_options(pg_dsn, run)
