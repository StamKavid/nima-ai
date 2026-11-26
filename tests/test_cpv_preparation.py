"""Public frozen CPV facts without a second source read or changed report API."""

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from nima.analytics import cpv_readout, snapshot
from nima.analytics.metric_readout import cohort_hash
from nima.storage.connection import connect
from tests.test_analytics_snapshot import reader, state
from tests.test_cpv_readout import request_for, seed
from tests.test_graph_pilot_archive import state as archive_state


def test_frozen_preparation_exposes_measured_facts_and_preserves_the_tuple_api(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "originals"
    request = request_for(seed(pg_dsn, root), root)
    before, files = state(pg_dsn), archive_state(tmp_path)
    with reader(pg_dsn) as (dsn, _):
        old_body, old_metric = cpv_readout.prepare_cpv_readout(dsn, request)
        calls: list[Any] = []

        def counted(value: str) -> Any:
            connection = connect(value)
            calls.append(connection)
            return connection

        monkeypatch.setattr(snapshot, "connect", counted)
        prepared = cpv_readout.prepare_cpv_result(dsn, request)
        assert len(calls) == 2
        assert all(c.closed for c in calls)
        assert prepared.body == old_body
        assert prepared.metric == old_metric
        cohort = json.loads(prepared.cohort_json)
        assert cohort_hash(cohort) == json.loads(old_body)["cohort_sha256"]
        assert [r["quarantine_count"] for r in cohort["runs"]] == [0]
        assert [r["connector_version"] for r in cohort["runs"]] == ["kimdis-contract-v1"]
        assert len(prepared.observations) == 3
        assert len(prepared.pages) == 1
        assert prepared.pages[0].record_count == 3
        with pytest.raises(FrozenInstanceError):
            prepared.body = b"changed"  # type: ignore[misc]  # Exercise runtime immutability.
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == files
