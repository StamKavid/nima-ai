"""Shared preparation preserves original readout bytes and SELECT-only behavior."""

from pathlib import Path

from nima.analytics.export import export_readout, prepare_readout
from nima.analytics.reconcile import reconcile
from nima.analytics.result import build_result
from nima.analytics.snapshot import read_snapshot
from tests.test_analytics_reconcile import seed_cohort
from tests.test_analytics_snapshot import reader, state
from tests.test_market_analytics import request_file


def test_preparation_matches_original_bytes_and_does_not_publish(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "raw")
    path = request_file(request, tmp_path / "request.json")
    before = state(pg_dsn)
    output = tmp_path / "reports"
    with reader(pg_dsn) as (dsn, _):
        snapshot = read_snapshot(
            dsn, request.run_ids, tax_id=request.supplier_tax_id, cutoff=request.observation_cutoff
        )
        expected = build_result(reconcile(snapshot, request))
        prepared = prepare_readout(dsn, request)
        assert prepared.body == expected
        assert prepared.snapshot == snapshot and not output.exists()
        summary = export_readout(dsn, path, output)
        assert (output / (summary.artifact_sha256 + ".json")).read_bytes() == expected
    assert state(pg_dsn) == before
