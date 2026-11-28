"""Fresh-provider bindings and global budgets fail before a view is published."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from nima.analytics import buyer_view as view
from nima.analytics.buyer_view_request import ViewError
from nima.analytics.request import RequestError
from nima.dataops.acceptance_files import AcceptanceError
from nima.graph.pilot_archive import PilotArchiveError
from nima.identity import AssessmentError
from nima.insights.buyer_participation import InsightError, prepare_buyer_insight
from tests.test_analytics_snapshot import reader
from tests.test_buyer_view_native import selection


@pytest.mark.parametrize(
    "dsn,entries", [("", ()), (None, ()), ("x", []), ("x", ()), ("x", (None,))]
)
def test_bad_library_inputs_have_closed_errors(dsn: Any, entries: Any) -> None:
    with pytest.raises(ViewError):
        view.prepare_buyer_evidence_view(dsn, entries)


@pytest.mark.parametrize(
    "error,reason",
    [
        (InsightError("insight_database"), "database"),
        (RequestError("analytics_input"), "input"),
        (RequestError("analytics_limit"), "limit"),
        (AcceptanceError("acceptance_evidence"), "evidence"),
        (PilotArchiveError("pilot_archive"), "evidence"),
        (PilotArchiveError("pilot_limit"), "limit"),
        (AssessmentError("assessment_limit"), "limit"),
        (KeyError("private-value"), "contract"),
    ],
)
def test_maps_dependency_failures_without_private_details(
    error: Exception, reason: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = selection(pg_dsn, tmp_path / "one")

    def fail(*args: object, **kwargs: object) -> Any:
        raise error

    monkeypatch.setattr(view, "prepare_buyer_insight", fail)
    with pytest.raises(ViewError, match="^view_" + reason + "$"):
        view.prepare_buyer_evidence_view("fixture", (entry,))


@pytest.mark.parametrize("limit", ["MAX_PAGES", "MAX_OBSERVATIONS", "MAX_RAW_BYTES"])
def test_global_limits_refuse_instead_of_truncating(
    limit: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = selection(pg_dsn, tmp_path / "one")
    monkeypatch.setattr(view, limit, 1 if limit != "MAX_PAGES" else 0)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ViewError, match="^view_limit$"):
        view.prepare_buyer_evidence_view(dsn, (entry,))


@pytest.mark.parametrize("change", ["subject", "status", "assessment", "readout"])
def test_rejects_a_changed_or_inconsistent_prepared_provider_frame(
    change: str, pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = selection(pg_dsn, tmp_path / "one")
    from nima.analytics.buyer_request import read_buyer_request

    with reader(pg_dsn) as (dsn, _):
        fresh = prepare_buyer_insight(
            dsn, read_buyer_request(entry.request_path), entry.report_path
        )
    data = json.loads(fresh.body)
    if change == "subject":
        fresh = replace(fresh, subject_sha256="0" * 64)
    else:
        if change == "status":
            data["status"] = "answered"
        elif change == "assessment":
            data["data_fitness"]["assessment"]["status"] = "ready-forged"
        else:
            data["subject"]["readout_sha256"] = "0" * 64
        fresh = replace(fresh, body=json.dumps(data).encode())
    monkeypatch.setattr(view, "prepare_buyer_insight", lambda *args: fresh)
    with pytest.raises(
        ViewError, match="^view_" + ("evidence" if change == "subject" else "contract") + "$"
    ):
        view.prepare_buyer_evidence_view("fixture", (entry,))
