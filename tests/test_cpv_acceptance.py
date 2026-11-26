"""U2 fitness derives ten counters from fresh originals and frozen SQL facts."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import cpv_readout, snapshot
from nima.analytics.cpv_readout import prepare_cpv_result
from nima.dataops.cpv_acceptance import prepare_cpv_acceptance
from nima.storage.connection import connect
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_acceptance import subject
from tests.test_cpv_readout import request_for, seed
from tests.test_graph_pilot_archive import state as archive_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Acceptance must not request source data")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def test_native_ten_counters_use_one_cohort_and_preserve_private_inputs(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "originals"
    request = request_for(seed(pg_dsn, root), root)
    with reader(pg_dsn) as (dsn, _):
        original = prepare_cpv_result(dsn, request)
        report = subject(tmp_path / "reports", original.body)
        before, files = state(pg_dsn), archive_state(tmp_path)
        connections: list[Any] = []
        cohorts = 0
        read_cohort = snapshot.read_cohort

        def counted(value: str) -> Any:
            connection = connect(value)
            connections.append(connection)
            return connection

        def cohort(*args: Any) -> Any:
            nonlocal cohorts
            cohorts += 1
            return read_cohort(*args)

        monkeypatch.setattr(snapshot, "connect", counted)
        monkeypatch.setattr(cpv_readout, "read_cohort", cohort)
        prepared = prepare_cpv_acceptance(dsn, request, report)
        assert len(connections) == 2 and all(c.closed for c in connections)
        assert cohorts == 1
        data = json.loads(prepared.body)
        assert data["version"] == "nima-cpv-acceptance-v1"
        assert data["subject"]["artifact_sha256"] == report.stem
        assert data["subject"]["request_sha256"] == request.request_sha256
        assert data["subject"]["cohort_sha256"] == json.loads(original.body)["cohort_sha256"]
        assert (
            data["subject"]["diagnostic_scope"] == "selected_unambiguous_before_cpv_period_filters"
        )
        assert data["assessment"]["provider_status"] == "observed_activity"
        assert data["assessment"]["status"] == "limited"
        assert {c["name"]: c["value"] for c in data["assessment"]["counts"]} == {
            "observations": 3,
            "pages": 1,
            "page_records": 3,
            "quarantined": 0,
            "selected_records": 3,
            "ambiguous_records": 0,
            "unknown_dates": 0,
            "unclassified_cpv": 1,
            "unknown_cancellations": 3,
            "cancelled_records": 0,
        }
        assert data["subject"]["metric"]["status"] == "draft"
        assert "request" not in data["subject"]
        for value in ("012345678", "kimdis:A", "45000000", "Synthetic", str(tmp_path)):
            assert value.encode() not in prepared.body
        assert prepare_cpv_acceptance(dsn, request, report).body == prepared.body
        assert len(connections) == 4 and cohorts == 2
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == files


@pytest.mark.parametrize(
    "case",
    [
        "overlap_cancel",
        "duplicate_code",
        "unknown_date",
        "bad_date",
        "unclassified",
        "unavailable",
        "invalid_code",
        "unknown_cancel",
        "ambiguous",
        "reobserved",
        "a_b_a",
        "after_cutoff",
        "filtered_code",
        "filtered_period",
        "empty_capture",
    ],
)
def test_hand_calculated_diagnostics_keep_distinct_records_and_prefilter_scope(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from nima.dataops import cpv_acceptance as adapter
    from nima.semantics.cpv_period import CpvAssertion, Observation
    from tests.cpv_acceptance_samples import observation, producer

    first = observation()
    assert first.cpv is not None
    rows: tuple[Observation, ...] = (first,)
    selection: dict[str, Any] = {}
    expected = {
        "observations": 1,
        "pages": 1,
        "page_records": 1,
        "quarantined": 0,
        "selected_records": 1,
        "ambiguous_records": 0,
        "unknown_dates": 0,
        "unclassified_cpv": 0,
        "unknown_cancellations": 0,
        "cancelled_records": 0,
    }
    status, decision = "observed_activity", "ready"
    if case in {"overlap_cancel", "duplicate_code"}:
        rows = (
            replace(
                first,
                cancelled=case == "overlap_cancel",
                cpv=(
                    *first.cpv,
                    CpvAssertion(
                        "reported", "45100000-8" if case == "overlap_cancel" else "45000000-3"
                    ),
                ),
            ),
        )
        if case == "overlap_cancel":
            expected["cancelled_records"] = 1
            decision = "limited"
    elif case in {"unknown_date", "bad_date", "filtered_period"}:
        rows = (replace(first, submitted_text="not a date" if case == "bad_date" else None),)
        expected["unknown_dates"] = 1
        decision = "limited"
        if case == "filtered_period":
            selection.update(period_from="2026-03", period_to="2026-03")
            status = "selection_unresolved"
    elif case in {"unclassified", "unavailable", "invalid_code", "filtered_code"}:
        rows = (
            replace(
                first,
                cpv=None
                if case == "unavailable"
                else (CpvAssertion("invalid" if case == "invalid_code" else "missing", None),),
            ),
        )
        expected["unclassified_cpv"] = 1
        decision = "limited"
        if case == "filtered_code":
            selection["cpv_base_code"] = "99999999"
            status = "selection_unresolved"
    elif case == "unknown_cancel":
        rows = (replace(first, cancelled=None),)
        expected["unknown_cancellations"] = 1
        decision = "limited"
    elif case == "ambiguous":
        first = replace(first, cpv=None, submitted_text=None, cancelled=None)
        rows = (first, replace(first, observation_id=2, content_sha256="c" * 64))
        expected.update(
            observations=2, pages=2, page_records=2, selected_records=0, ambiguous_records=1
        )
        status, decision = "selection_unresolved", "limited"
    elif case in {"reobserved", "a_b_a"}:
        rows = (
            first,
            replace(first, observation_id=2, observed_at=first.observed_at.replace(day=2)),
        )
        if case == "a_b_a":
            rows = (
                first,
                replace(rows[1], content_sha256="c" * 64, cancelled=True),
                replace(first, observation_id=3, observed_at=first.observed_at.replace(day=3)),
            )
        expected.update(observations=len(rows), pages=len(rows), page_records=len(rows))
    elif case == "after_cutoff":
        rows = (replace(first, observed_at=first.observed_at.replace(month=7)),)
        expected["selected_records"] = 0
        status = "no_observations_before_cutoff"
    else:
        rows = ()
        expected.update(observations=0, page_records=0, selected_records=0)
        status = "empty_capture"
    request, fresh = producer(rows, **selection)
    calls = 0

    def reconstruct(*args: object) -> Any:
        nonlocal calls
        calls += 1
        return fresh

    monkeypatch.setattr(adapter, "prepare_cpv_result", reconstruct)
    result = prepare_cpv_acceptance("fixture", request, subject(tmp_path / "reports", fresh.body))
    assert calls == 1
    assert {c.name: c.value for c in result.assessment.counts} == expected
    assert result.assessment.provider_status == status
    assert result.assessment.status == decision
    for value in ("DO_NOT_EXPORT", "012345678", "PRIVATE_ID", "45000000", "/unused"):
        assert value.encode() not in result.body
