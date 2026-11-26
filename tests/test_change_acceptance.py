"""Actual originals/SQL establish fitness; abstention never invents verified coverage."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import change_readout, snapshot
from nima.storage.connection import connect
from tests.test_analytics_snapshot import reader, state
from tests.test_change_readout import admin, day, two_captures
from tests.test_citation_acceptance import subject
from tests.test_graph_pilot_archive import state as archive_state


@pytest.mark.parametrize("incomparable", [False, True])
def test_native_six_counters_or_sql_only_blocked_without_fabricated_proof(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, incomparable: bool
) -> None:
    from nima.dataops.change_acceptance import prepare_change_acceptance

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Acceptance must not request source data")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    request = two_captures(pg_dsn, tmp_path / "raw")
    if incomparable:
        admin(
            pg_dsn,
            "UPDATE nima.ingest_runs SET status='failed' WHERE run_id=%s",
            request.later_run_ids[0],
        )
        for path in (tmp_path / "raw").rglob("*.body"):
            path.unlink()
    with reader(pg_dsn) as (dsn, _):
        original = change_readout.prepare_change_result(dsn, request)
        report = subject(tmp_path / "reports", original.body)
        before, files = state(pg_dsn), archive_state(tmp_path)
        connections: list[Any] = []

        def counted(value: str) -> Any:
            connection = connect(value)
            connections.append(connection)
            return connection

        monkeypatch.setattr(snapshot, "connect", counted)
        result = prepare_change_acceptance(dsn, request, report)
        assert len(connections) == 2 and all(c.closed for c in connections)
        data = json.loads(result.body)
        assert data["version"] == "nima-change-acceptance-v1"
        assert data["subject"]["artifact_sha256"] == report.stem
        assert data["subject"]["capture_end"] == day(2).isoformat()
        assert data["subject"]["time_basis"] == "stored_capture_end"
        assert data["subject"]["metric"]["status"] == "draft"
        expected = {"quarantined": 0}
        if incomparable:
            assert result.assessment.status == "blocked"
            assert data["subject"]["verification_scope"] == "sql_comparability_only"
            assert data["subject"]["run_profiles"] == []
            assert result.assessment.cohort_sha256 is None
            assert data["subject"]["reasons"] == ["run_incomplete"]
            assert (
                next(c for c in result.assessment.checks if c.check_id == "evidence").status
                == "not_assessed"
            )
        else:
            assert result.assessment.status == "ready"
            assert data["subject"]["verification_scope"] == "verified_two_capture_cohort"
            assert len(data["subject"]["run_profiles"]) == 2
            expected.update(
                observations=7, pages=2, page_records=7, selected_records=5, ambiguous_records=0
            )
        assert {c.name: c.value for c in result.assessment.counts} == expected
        for value in ("kimdis:X", "Synthetic", "dateFrom", str(tmp_path)):
            assert value.encode() not in result.body
        assert prepare_change_acceptance(dsn, request, report).body == result.body
        assert len(connections) == 4
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == files
