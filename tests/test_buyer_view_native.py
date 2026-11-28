"""Real archive and restricted SQL proof for the offline evidence view."""

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import buyer_view as view
from nima.analytics import snapshot
from nima.analytics.buyer_readout import prepare_buyer_result
from nima.analytics.buyer_view_request import BuyerViewEntry, ViewError
from nima.insights.buyer_participation import prepare_buyer_insight
from nima.storage.connection import connect
from tests.buyer_acceptance_samples import request_file
from tests.test_analytics_snapshot import reader, state
from tests.test_buyer_readout import record, request_for
from tests.test_citation_acceptance import subject
from tests.test_cpv_readout import seed
from tests.test_graph_pilot_archive import state as file_state


def selection(pg_dsn: str, directory: Path, *, unknown: bool = False) -> BuyerViewEntry:
    directory.mkdir(mode=0o700)
    root = directory / "raw"
    rows = [
        record("A", "B1", ["111111111"]),
        record("B", "B1", ["222222222"]),
        record("C", "B1", ["111111111", "222222222"]),
    ]
    if unknown:
        rows.append(record("D", "B1", None))
    rows = [{**row, "cancelled": False} for row in rows]
    request = request_for(seed(pg_dsn, root, rows), root)
    with reader(pg_dsn) as (dsn, _):
        parent = prepare_buyer_result(dsn, request)
    return BuyerViewEntry(
        "Limited" if unknown else "Primary",
        request_file(request, directory / "request.json"),
        subject(directory / "reports", parent.body),
    )


def test_each_entry_uses_one_fresh_provider_and_two_readonly_connections(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries = (
        selection(pg_dsn, tmp_path / "one"),
        selection(pg_dsn, tmp_path / "two", unknown=True),
    )
    before = state(pg_dsn), file_state(tmp_path)
    calls: list[Any] = []
    consumers = []
    original = prepare_buyer_insight

    def counted(dsn: str) -> Any:
        connection = connect(dsn)
        calls.append(connection)
        return connection

    def consumed(*args: Any) -> Any:
        consumers.append(args)
        return original(*args)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("View attempted source HTTP")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(snapshot, "connect", counted)
    monkeypatch.setattr(view, "prepare_buyer_insight", consumed)
    with reader(pg_dsn) as (dsn, _):
        prepared = view.prepare_buyer_evidence_view(dsn, entries)
    assert [entry.status for entry in prepared.entries] == [
        "review_required",
        "insufficient_evidence",
    ]
    assert len(consumers) == 2 and len(calls) == 4 and all(c.closed for c in calls)
    for entry, configured in zip(prepared.entries, entries, strict=True):
        assert entry.report_body == configured.report_path.read_bytes()
        insight = json.loads(entry.insight_body)
        assert insight["answer"] is None
        assert (
            hashlib.sha256(entry.assessment_body).hexdigest()
            == insight["subject"]["data_fitness_sha256"]
        )
    assert all(hashlib.sha256(body).hexdigest() == digest for digest, body in prepared.originals)
    assert (state(pg_dsn), file_state(tmp_path)) == before


def test_missing_original_fails_without_reusing_a_previous_result(
    pg_dsn: str, tmp_path: Path
) -> None:
    entry = selection(pg_dsn, tmp_path / "one")
    with reader(pg_dsn) as (dsn, _):
        view.prepare_buyer_evidence_view(dsn, (entry,))
        next((tmp_path / "one/raw").rglob("*.body")).unlink()
        with pytest.raises(ViewError, match="^view_evidence$"):
            view.prepare_buyer_evidence_view(dsn, (entry,))
