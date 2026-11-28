"""Real archive and restricted SQL proof for the offline evidence view."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import snapshot
from nima.analytics.buyer_readout import prepare_buyer_result
from nima.insights.buyer_participation import prepare_buyer_insight
from nima.storage.connection import connect
from nima.views import buyer_evidence as view
from nima.views.request import BuyerViewEntry, ViewError
from tests.buyer_acceptance_samples import request_file
from tests.test_analytics_snapshot import reader, state
from tests.test_buyer_readout import record, request_for
from tests.test_citation_acceptance import subject
from tests.test_cpv_readout import seed
from tests.test_graph_pilot_archive import state as file_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("View attempted source HTTP")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)


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


def test_export_retries_with_exact_bytes_and_no_partial_view_on_failure(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = (selection(pg_dsn, tmp_path / "one"),)
    config = tmp_path / "view.json"
    config.write_text(
        json.dumps(
            {
                "version": "nima-buyer-evidence-view-request-v1",
                "entries": [
                    {
                        "label": e.label,
                        "request_path": str(e.request_path),
                        "report_path": str(e.report_path),
                    }
                    for e in entries
                ],
            }
        )
    )
    config.chmod(0o600)
    output = tmp_path / "views"
    with reader(pg_dsn) as (dsn, _):
        first = view.export_buyer_evidence_view(dsn, config, output)
        assert first.entry_states == ("review_required",)
        artifact = output / (first.artifact_sha256 + ".html")
        stable = artifact.read_bytes(), artifact.stat().st_mtime_ns
        assert artifact.stat().st_mode & 0o777 == 0o600
        assert output.stat().st_mode & 0o777 == 0o700
        assert (output / ".gitignore").read_bytes() == b"*\n"
        assert view.export_buyer_evidence_view(dsn, config, output) == first
        assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == stable
        from nima.__main__ import main

        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert (
            main(
                [
                    "analytics",
                    "buyer-evidence-view",
                    "--config",
                    str(config),
                    "--output-dir",
                    str(output),
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["artifact_sha256"] == first.artifact_sha256
        from dataclasses import replace

        from nima.analytics.buyer_request import read_buyer_request

        request = read_buyer_request(entries[0].request_path)
        moved = tmp_path / "relocated"
        shutil.copytree(tmp_path / "one/raw", moved)
        request_file(
            replace(
                request,
                archive_bindings=tuple(replace(b, root=moved) for b in request.archive_bindings),
            ),
            entries[0].request_path,
        )
        assert view.export_buyer_evidence_view(dsn, config, output) == first
        assert (artifact.read_bytes(), artifact.stat().st_mtime_ns) == stable
        next(moved.rglob("*.body")).unlink()
        with pytest.raises(ViewError, match="^view_evidence$"):
            view.export_buyer_evidence_view(dsn, config, tmp_path / "failed-output")
        assert not (tmp_path / "failed-output").exists()


def test_original_removed_after_fresh_provider_is_rejected_by_the_embedding_read(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = selection(pg_dsn, tmp_path / "one")

    def removed(*args: Any) -> Any:
        fresh = prepare_buyer_insight(*args)
        next((tmp_path / "one/raw").rglob("*.body")).unlink()
        return fresh

    monkeypatch.setattr(view, "prepare_buyer_insight", removed)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ViewError, match="^view_evidence$"):
        view.prepare_buyer_evidence_view(dsn, (entry,))


def test_view_uses_only_provider_selected_observations_with_old_and_future_captures(
    pg_dsn: str, tmp_path: Path
) -> None:
    from dataclasses import replace
    from datetime import UTC, datetime

    from nima.graph.pilot_archive import ArchiveBinding
    from nima.views.html import render_view

    root = tmp_path / "raw"
    times = (
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2026, 6, 2, tzinfo=UTC),
    )
    runs = tuple(
        sorted(
            seed(
                pg_dsn,
                root,
                [
                    {
                        **record("Stable", "B1", ["111111111"]),
                        "title": f"Fictional revision {index}",
                        "cancelled": False,
                    }
                ],
                observed=when,
            )
            for index, when in enumerate(times)
        )
    )
    request = replace(
        request_for(runs[0], root),
        run_ids=runs,
        archive_bindings=tuple(ArchiveBinding("kimdis", run, root) for run in runs),
    )
    with reader(pg_dsn) as (dsn, _):
        report = prepare_buyer_result(dsn, request)
        entry = BuyerViewEntry(
            "Repeated",
            request_file(request, tmp_path / "request.json"),
            subject(tmp_path / "reports", report.body),
        )
        prepared = view.prepare_buyer_evidence_view(dsn, (entry,))
    text = render_view(prepared).decode()
    assert text.count("<h3>Selected observation</h3>") == 1
    assert times[1].isoformat() in text
    assert times[0].isoformat() not in text and times[2].isoformat() not in text
    assert len(prepared.originals) == 3


def test_actual_aggregate_observation_boundary_accepts_500_and_rejects_501(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.projections.worker import drain

    entries = []
    for index, count in enumerate((250, 250, 251)):
        directory = tmp_path / str(index)
        directory.mkdir(mode=0o700)
        root = directory / "raw"
        records = [
            {**record(f"V{index}-{i}", "B1", ["111111111"]), "cancelled": False}
            for i in range(count)
        ]
        run = seed(pg_dsn, root, records)
        drain(pg_dsn, max_events=1000, run_id=run)
        request = request_for(run, root)
        with reader(pg_dsn) as (dsn, _):
            parent = prepare_buyer_result(dsn, request)
        entries.append(
            BuyerViewEntry(
                f"Volume {index}",
                request_file(request, directory / "request.json"),
                subject(directory / "reports", parent.body),
            )
        )
    with reader(pg_dsn) as (dsn, _):
        assert len(view.prepare_buyer_evidence_view(dsn, tuple(entries[:2])).entries) == 2
        with pytest.raises(ViewError, match="^view_limit$"):
            view.prepare_buyer_evidence_view(dsn, (entries[0], entries[2]))
