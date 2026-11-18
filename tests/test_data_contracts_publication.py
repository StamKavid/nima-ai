"""The actual reader/reconciler/publisher refuses producer contract violations."""

import json
import socket
from pathlib import Path
from typing import Any, Never

import pytest

from nima.__main__ import main
from nima.analytics import export
from nima.analytics.reconcile import reconcile
from nima.analytics.result import build_result
from nima.analytics.snapshot import read_snapshot
from nima.contracts import contract
from nima.identity.artifacts import encode
from tests.test_analytics_cli import arguments
from tests.test_analytics_reconcile import seed_cohort
from tests.test_analytics_snapshot import reader, state
from tests.test_market_analytics import request_file


@pytest.mark.parametrize(
    "fault",
    [
        "missing_field",
        "wrong_type",
        "negative",
        "wrong_total",
        "definition",
        "duplicate",
        "bool",
        "contract_drift",
    ],
)
def test_contract_failure_preserves_previous_report_rows_and_originals(
    pg_dsn: str,
    tmp_path: Path,
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "archive")
    selection = request_file(request, tmp_path / "request.json")
    output = tmp_path / "reports"
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        snapshot = read_snapshot(
            dsn, request.run_ids, tax_id=request.supplier_tax_id, cutoff=request.observation_cutoff
        )
        legacy_bytes = build_result(reconcile(snapshot, request))
        assert main(arguments(selection, output)) == 0
        summary = json.loads(capsys.readouterr().out)
        prior = output / (summary["artifact_sha256"] + ".json")
        assert prior.read_bytes() == legacy_bytes
        preserved = prior.read_bytes(), prior.stat().st_mtime_ns
        assert json.loads(legacy_bytes)["metric"]["result"]["total"] == 5
        before = state(pg_dsn)
        originals = {p: p.read_bytes() for p in (tmp_path / "archive").rglob("*.body")}

        def malformed(*args: Any, **kwargs: Any) -> bytes:
            result = json.loads(build_result(*args, **kwargs))
            if fault == "missing_field":
                del result["evidence"]
            elif fault == "wrong_type":
                result["metric"]["result"]["total"] = "private-sentinel"
            elif fault == "negative":
                result["metric"]["result"]["total"] = -1
            elif fault == "wrong_total":
                result["metric"]["result"]["total"] = 7
            elif fault == "definition":
                result["metric"]["definition"]["revision"] = "private-sentinel"
            elif fault == "bool":
                result["metric"]["result"]["buyers"][1]["record_count"] = True
            else:
                result["evidence"][1] = result["evidence"][0]
            return encode(result)

        def forbidden(*args: object, **kwargs: object) -> Never:
            pytest.fail("Contract validation must not open a source or schema route")

        if fault == "contract_drift":
            metadata = contract()
            metadata["customProperties"][0]["value"]["revision"] = "private-sentinel"
            monkeypatch.setattr("nima.contracts.contract", lambda: metadata)
        else:
            monkeypatch.setattr(export, "build_result", malformed)
        monkeypatch.setattr("httpx.Client", forbidden)
        monkeypatch.setattr(socket, "socket", forbidden)
        for destination in (output, tmp_path / "must-not-exist"):
            assert main(arguments(selection, destination)) == 1
            terminal = capsys.readouterr()
            assert json.loads(terminal.out) == {"status": "failed", "failure": "analytics_contract"}
            assert not terminal.err
            assert "private-sentinel" not in terminal.out and str(tmp_path) not in terminal.out
        assert not (tmp_path / "must-not-exist").exists()
        assert list(output.glob("*.json")) == [prior]
        assert preserved == (prior.read_bytes(), prior.stat().st_mtime_ns)
        assert state(pg_dsn) == before
        assert all(p.read_bytes() == body for p, body in originals.items())
