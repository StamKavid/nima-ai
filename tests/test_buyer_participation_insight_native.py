"""Restricted SQL, real archives and no HTTP for the insight library/export path."""

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import snapshot
from nima.analytics.buyer_readout import prepare_buyer_result
from nima.dataops.buyer_acceptance import prepare_buyer_acceptance
from nima.insights import buyer_participation as insight
from nima.storage.connection import connect
from tests.buyer_acceptance_samples import request_file
from tests.test_analytics_snapshot import reader, state
from tests.test_buyer_readout import record, request_for
from tests.test_citation_acceptance import subject
from tests.test_cpv_readout import seed
from tests.test_graph_pilot_archive import state as file_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Insight attempted HTTP")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


@pytest.mark.parametrize("unknown", [False, True])
def test_verified_export_retries_relocates_and_preserves_sql_and_originals(
    unknown: bool,
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "raw"
    records = [
        {**record("A", "B1", ["111111111"]), "cancelled": False},
        {**record("B", "B1", ["222222222"]), "cancelled": False},
        {**record("C", "B1", ["111111111", "222222222"]), "cancelled": False},
    ]
    if unknown:
        records.append({**record("D", "B1", None), "cancelled": False})
    request = request_for(seed(pg_dsn, root, records), root)
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        parent = prepare_buyer_result(dsn, request)
        report = subject(tmp_path / "reports", parent.body)
        before, raw = state(pg_dsn), file_state(root)
        calls: list[Any] = []
        consumers = 0
        original = prepare_buyer_acceptance

        def counted(value: str) -> Any:
            connection = connect(value)
            calls.append(connection)
            return connection

        def consumed(*args: Any) -> Any:
            nonlocal consumers
            consumers += 1
            return original(*args)

        monkeypatch.setattr(snapshot, "connect", counted)
        monkeypatch.setattr(insight, "prepare_buyer_acceptance", consumed)
        output = tmp_path / "output"
        first = insight.export_buyer_insight(dsn, selection, report, output)
        assert first.status == ("insufficient_evidence" if unknown else "review_required")
        assert consumers == 1 and len(calls) == 2 and all(c.closed for c in calls)
        artifact = output / (first.artifact_sha256 + ".json")
        stable = artifact.read_bytes(), artifact.stat().st_mtime_ns
        assert artifact.stat().st_mode & 0o777 == 0o600
        assert output.stat().st_mode & 0o777 == 0o700
        data = json.loads(stable[0])
        assert data["answer"] is None and data["subject"]["readout_sha256"] == report.stem
        assert insight.export_buyer_insight(dsn, selection, report, output) == first
        assert consumers == 2 and len(calls) == 4
        assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == stable
        moved = tmp_path / "relocated"
        shutil.copytree(root, moved)
        relocated = replace(
            request, archive_bindings=(replace(request.archive_bindings[0], root=moved),)
        )
        assert insight.prepare_buyer_insight(dsn, relocated, report).body == stable[0]
        assert consumers == 3 and len(calls) == 6
        from nima.__main__ import main

        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            main(
                [
                    "insights",
                    "buyer-participation",
                    "--request",
                    str(selection),
                    "--report",
                    str(report),
                    "--output-dir",
                    str(output),
                ]
            )
            == 3
        )
        assert json.loads(capsys.readouterr().out)["artifact_sha256"] == first.artifact_sha256
        assert consumers == 4 and len(calls) == 8
        assert state(pg_dsn) == before and file_state(root) == raw
        assert report.read_bytes() == parent.body
        original_page = next(root.rglob("*.body"))
        original_page.unlink()
        with pytest.raises(insight.InsightError, match="^insight_evidence$"):
            insight.export_buyer_insight(dsn, selection, report, output)
        assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == stable


def test_empty_capture_is_not_a_zero_supplier_claim(pg_dsn: str, tmp_path: Path) -> None:
    from nima.analytics.buyer_request import BuyerRequest
    from tests.test_analytics_reconcile import captured
    from tests.test_buyer_concentration import CUTOFF

    saved, _ = captured(pg_dsn, tmp_path / "raw", empty=True)
    request = BuyerRequest(saved.run_ids, CUTOFF, "B1", saved.archive_bindings)
    with reader(pg_dsn) as (dsn, _):
        parent = prepare_buyer_result(dsn, request)
        data = json.loads(
            insight.prepare_buyer_insight(
                dsn, request, subject(tmp_path / "reports", parent.body)
            ).body
        )
    assert data["status"] == "insufficient_evidence" and data["answer"] is None
    assert {"provider_empty_capture", "no_resolved_denominator", "metric_not_certified"} <= set(
        data["reason_codes"]
    )


def test_owner_role_and_forged_certification_are_rejected(pg_dsn: str, tmp_path: Path) -> None:
    from nima.identity.artifacts import encode

    root = tmp_path / "raw"
    request = request_for(
        seed(pg_dsn, root, [{**record("A", "B1", ["111111111"]), "cancelled": False}]), root
    )
    with reader(pg_dsn) as (dsn, _):
        parent = prepare_buyer_result(dsn, request)
        report = subject(tmp_path / "reports", parent.body)
        with pytest.raises(insight.InsightError, match="^insight_database$"):
            insight.prepare_buyer_insight(pg_dsn, request, report)
        forged = json.loads(parent.body)
        forged["metric"]["definition"]["status"] = "certified"
        with pytest.raises(insight.InsightError, match="^insight_evidence$"):
            insight.prepare_buyer_insight(
                dsn, request, subject(tmp_path / "forged", encode(forged))
            )


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "permissions"])
def test_unsafe_parent_input_never_publishes(unsafe: str, pg_dsn: str, tmp_path: Path) -> None:
    from tests.buyer_acceptance_samples import request_file

    root = tmp_path / "raw"
    request = request_for(
        seed(pg_dsn, root, [{**record("A", "B1", ["111111111"]), "cancelled": False}]), root
    )
    selected = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        parent = prepare_buyer_result(dsn, request)
        report = subject(tmp_path / "reports", parent.body)
        if unsafe == "symlink":
            target = report.with_suffix(".saved")
            report.rename(target)
            report.symlink_to(target)
        elif unsafe == "hardlink":
            report.with_suffix(".linked").hardlink_to(report)
        else:
            report.chmod(0o644)
        output = tmp_path / "output"
        with pytest.raises(insight.InsightError, match="^insight_(input|evidence)$"):
            insight.export_buyer_insight(dsn, selected, report, output)
        assert not output.exists()
