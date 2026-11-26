"""Measured U1 fitness, bound to one actually reconstructed private subject."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import snapshot as sessions
from nima.analytics.export import prepare_readout
from nima.dataops.participation_acceptance import prepare_participation_acceptance
from nima.storage.connection import connect
from tests.test_analytics_reconcile import seed_cohort
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_acceptance import subject
from tests.test_graph_pilot_archive import state as archive_state
from tests.test_semantics import TAX


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Acceptance must not request source data")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def test_native_cohort_has_eleven_measured_counters_and_no_copied_supplier(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "raw")
    with reader(pg_dsn) as (dsn, _):
        original = prepare_readout(dsn, request)
        report = subject(tmp_path / "reports", original.body)
        before, files = state(pg_dsn), archive_state(tmp_path)
        calls = 0

        def counted(value: str) -> Any:
            nonlocal calls
            calls += 1
            return connect(value)

        monkeypatch.setattr(sessions, "connect", counted)
        prepared = prepare_participation_acceptance(dsn, request, report)
        assert calls == 1
        data = json.loads(prepared.body)
        assert data["version"] == "nima-participation-acceptance-v1"
        assert data["subject"]["artifact_sha256"] == report.stem
        assert data["subject"]["request_sha256"] == request.request_sha256
        assert data["subject"]["snapshot_sha256"] == original.snapshot.input_sha256
        assert data["assessment"]["provider_status"] == "observed_participation"
        assert data["assessment"]["status"] == "limited"
        assert {c["name"]: c["value"] for c in data["assessment"]["counts"]} == {
            "observations": 11,
            "pages": 4,
            "page_records": 11,
            "quarantined": 0,
            "selected_records": 7,
            "ambiguous_records": 1,
            "unknown_suppliers": 1,
            "unassigned_buyers": 1,
            "invalid_supplier_occurrences": 0,
            "unknown_cancellations": 1,
            "cancelled_records": 1,
        }
        assert data["subject"]["metric"]["status"] == "draft"
        assert "request" not in data["subject"]
        for value in (TAX, "kimdis.buyer-key:B1", "Συνθετική δημοσίευση", str(tmp_path)):
            assert value.encode() not in prepared.body
        assert prepare_participation_acceptance(dsn, request, report).body == prepared.body
        assert calls == 2
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == files


@pytest.mark.parametrize(
    "case",
    [
        "unknown_list",
        "empty_list",
        "unknown_country",
        "foreign_country",
        "ambiguous_unknown",
        "ambiguous_invalid",
        "duplicate_match",
        "reobserved",
        "a_b_a",
        "after_cutoff",
        "unknown_buyer",
        "cancelled",
        "unknown_cancel",
        "empty_capture",
    ],
)
def test_hand_computed_selection_diagnostics(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from nima.dataops import participation_acceptance as adapter
    from nima.semantics.participation import Observation, Supplier
    from tests.participation_acceptance_samples import observation, producer

    first = observation()
    rows: tuple[Observation, ...] = (first,)
    expected = {
        "observations": 1,
        "pages": 1,
        "page_records": 1,
        "quarantined": 0,
        "selected_records": 1,
        "ambiguous_records": 0,
        "unknown_suppliers": 0,
        "unassigned_buyers": 0,
        "invalid_supplier_occurrences": 0,
        "unknown_cancellations": 0,
        "cancelled_records": 0,
    }
    status = "observed_participation"
    decision = "ready"
    if case == "unknown_list":
        rows = (replace(first, suppliers=None),)
        expected["unknown_suppliers"] = 1
        status = "selection_unresolved"
        decision = "limited"
    elif case == "empty_list":
        rows = (replace(first, suppliers=()),)
        status = "no_observed_participation"
    elif case in {"unknown_country", "foreign_country"}:
        rows = (
            replace(
                first, suppliers=(Supplier(0, TAX, None if case == "unknown_country" else "DE"),)
            ),
        )
        expected["unknown_suppliers"] = 1
        status = "selection_unresolved"
        decision = "limited"
    elif case in {"ambiguous_unknown", "ambiguous_invalid"}:
        first = replace(
            first,
            suppliers=None if case == "ambiguous_unknown" else (Supplier(0, "invalid", "GR"),),
        )
        rows = (first, replace(first, observation_id=2, content_sha256="c" * 64))
        expected.update(
            observations=2, pages=2, page_records=2, selected_records=0, ambiguous_records=1
        )
        status = (
            "selection_unresolved" if case == "ambiguous_unknown" else "no_observed_participation"
        )
        decision = "limited"
        expected["invalid_supplier_occurrences"] = 2 if case == "ambiguous_invalid" else 0
    elif case == "duplicate_match":
        rows = (
            replace(
                first,
                suppliers=(
                    Supplier(0, TAX, "GR"),
                    Supplier(1, "987654321", "GR"),
                    Supplier(2, TAX, "EL"),
                ),
            ),
        )
    elif case == "reobserved":
        rows = (
            first,
            replace(first, observation_id=2, observed_at=first.observed_at.replace(day=2)),
        )
        expected.update(observations=2, pages=2, page_records=2)
    elif case == "a_b_a":
        rows = (
            first,
            replace(
                first,
                observation_id=2,
                observed_at=first.observed_at.replace(day=2),
                content_sha256="c" * 64,
                cancelled=True,
            ),
            replace(first, observation_id=3, observed_at=first.observed_at.replace(day=3)),
        )
        expected.update(observations=3, pages=3, page_records=3)
    elif case == "after_cutoff":
        rows = (replace(first, observed_at=first.observed_at.replace(day=11)),)
        expected["selected_records"] = 0
        status = "no_observations_before_cutoff"
    elif case == "unknown_buyer":
        rows = (replace(first, buyer_key=None),)
        expected["unassigned_buyers"] = 1
        decision = "limited"
    elif case == "cancelled":
        rows = (replace(first, cancelled=True),)
        expected["cancelled_records"] = 1
        decision = "limited"
    elif case == "unknown_cancel":
        rows = (replace(first, cancelled=None),)
        expected["unknown_cancellations"] = 1
        decision = "limited"
    elif case == "empty_capture":
        rows = ()
        expected.update(observations=0, page_records=0, selected_records=0)
        status = "empty_capture"
    request, fresh = producer(rows)
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    prepared = prepare_participation_acceptance(
        "fixture", request, subject(tmp_path / "reports", fresh.body)
    )
    assert {c.name: c.value for c in prepared.assessment.counts} == expected
    assert prepared.assessment.provider_status == status
    assert prepared.assessment.status == decision
    assert TAX.encode() not in prepared.body


def test_overlapping_unknown_flags_count_the_record_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from nima.dataops import participation_acceptance as adapter
    from nima.identity.artifacts import encode
    from tests.participation_acceptance_samples import observation, producer

    request, fresh = producer((observation(),))
    result = replace(
        fresh.snapshot.metric,
        records=(
            replace(fresh.snapshot.metric.records[0], unknown_suppliers=True, unassessed=True),
        ),
    )
    body = json.loads(fresh.body)
    body["metric"]["result"] = result.payload()
    fresh = replace(fresh, body=encode(body), snapshot=replace(fresh.snapshot, metric=result))
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    result_frame = prepare_participation_acceptance(
        "fixture", request, subject(tmp_path / "reports", fresh.body)
    )
    assert {c.name: c.value for c in result_frame.assessment.counts}["unknown_suppliers"] == 1
    assert result_frame.assessment.status == "limited"
