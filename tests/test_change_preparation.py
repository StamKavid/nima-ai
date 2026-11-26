"""Expose existing frozen capture facts without changing old reports or SQL reads."""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from nima.analytics import change_readout, snapshot
from nima.storage.connection import connect
from tests.test_analytics_snapshot import reader, state
from tests.test_change_readout import admin, two_captures


@pytest.mark.parametrize("incomparable", [False, True])
def test_public_preparation_preserves_both_paths_and_closed_connections(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, incomparable: bool
) -> None:
    request = two_captures(pg_dsn, tmp_path)
    if incomparable:
        admin(
            pg_dsn,
            "UPDATE nima.ingest_runs SET status='failed' WHERE run_id=%s",
            request.later_run_ids[0],
        )
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        old = change_readout.prepare_change_readout(dsn, request)
        calls: list[Any] = []

        def counted(value: str) -> Any:
            connection = connect(value)
            calls.append(connection)
            return connection

        monkeypatch.setattr(snapshot, "connect", counted)
        prepared = change_readout.prepare_change_result(dsn, request)
        assert len(calls) == 2 and all(c.closed for c in calls)
        assert (prepared.body, prepared.metric) == old
        assert len(prepared.earlier.runs) == len(prepared.later.runs) == 1
        assert (prepared.cohort_json is None) is incomparable
        assert len(prepared.pages) == (0 if incomparable else 2)
        assert len(prepared.earlier.versions) == (0 if incomparable else 3)
        assert len(prepared.later.versions) == (0 if incomparable else 4)
        if not incomparable:
            assert prepared.cohort_json is not None
            assert len(json.loads(prepared.cohort_json)["records"]) == 7
        with pytest.raises(FrozenInstanceError):
            prepared.body = b"changed"  # type: ignore[misc]  # Runtime immutability.
    assert state(pg_dsn) == before
