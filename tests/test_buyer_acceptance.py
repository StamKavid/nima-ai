"""U3 fitness derives fourteen counters from fresh originals and frozen SQL facts."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics import buyer_readout, snapshot
from nima.analytics.buyer_readout import prepare_buyer_result
from nima.dataops.buyer_acceptance import prepare_buyer_acceptance
from nima.storage.connection import connect
from tests.test_analytics_snapshot import reader, state
from tests.test_buyer_readout import RECORDS, request_for
from tests.test_citation_acceptance import subject
from tests.test_cpv_readout import seed
from tests.test_graph_pilot_archive import state as archive_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Acceptance must not request source data")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def test_native_fourteen_counters_use_one_cohort_and_preserve_private_inputs(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.dataops import buyer_acceptance as adapter
    from nima.semantics.selection import select_latest

    root = tmp_path / "originals"
    request = request_for(seed(pg_dsn, root, RECORDS), root)
    with reader(pg_dsn) as (dsn, _):
        original = prepare_buyer_result(dsn, request)
        report = subject(tmp_path / "reports", original.body)
        before, files = state(pg_dsn), archive_state(tmp_path)
        connections: list[Any] = []
        cohorts = 0
        selections = 0
        read_cohort = snapshot.read_cohort

        def counted(value: str) -> Any:
            connection = connect(value)
            connections.append(connection)
            return connection

        def cohort(*args: Any) -> Any:
            nonlocal cohorts
            cohorts += 1
            return read_cohort(*args)

        def selected(*args: Any) -> Any:
            nonlocal selections
            selections += 1
            return select_latest(*args)

        monkeypatch.setattr(snapshot, "connect", counted)
        monkeypatch.setattr(buyer_readout, "read_cohort", cohort)
        monkeypatch.setattr(adapter, "select_latest", selected)
        prepared = prepare_buyer_acceptance(dsn, request, report)
        assert len(connections) == 2 and all(c.closed for c in connections)
        assert cohorts == selections == 1
        data = json.loads(prepared.body)
        assert data["version"] == "nima-buyer-acceptance-v1"
        assert data["subject"]["artifact_sha256"] == report.stem
        assert data["subject"]["request_sha256"] == request.request_sha256
        assert data["subject"]["cohort_sha256"] == json.loads(original.body)["cohort_sha256"]
        assert data["subject"]["diagnostic_scope"] == {
            "cohort": "latest_selection_before_buyer_filter",
            "buyer": "unambiguous_selected_buyer_records",
        }
        assert data["assessment"]["provider_status"] == "observed_concentration"
        assert data["assessment"]["status"] == "limited"
        assert {c["name"]: c["value"] for c in data["assessment"]["counts"]} == {
            "observations": 4,
            "pages": 1,
            "page_records": 4,
            "quarantined": 0,
            "selected_records": 4,
            "ambiguous_records": 0,
            "buyer_records": 3,
            "resolved_records": 2,
            "unresolved_suppliers": 1,
            "partial_suppliers": 0,
            "joint_records": 1,
            "supplier_participations": 3,
            "unknown_cancellations": 3,
            "cancelled_records": 0,
        }
        assert data["subject"]["metric"]["status"] == "draft"
        assert "request" not in data["subject"]
        for value in ("012345678", "kimdis:A", "kimdis.buyer-key:B1", "Synthetic", str(tmp_path)):
            assert value.encode() not in prepared.body
        assert prepare_buyer_acceptance(dsn, request, report).body == prepared.body
        assert len(connections) == 4 and cohorts == selections == 2
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == files


@pytest.mark.parametrize(
    "case",
    [
        "joint_cancel",
        "joint",
        "duplicates",
        "partial",
        "partial_joint",
        "unknown",
        "empty",
        "ineligible",
        "other_buyer",
        "missing_buyer",
        "global_ambiguity",
        "reobserved",
        "a_b_a",
        "buyer_changed",
        "unknown_cancel",
        "unresolved_cancel",
        "unresolved_unknown_cancel",
        "after_cutoff",
        "empty_capture",
        "top_tie",
    ],
)
def test_hand_computed_scopes_and_denominators(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from nima.dataops import buyer_acceptance as adapter
    from nima.semantics.participation import Observation, Supplier
    from tests.buyer_acceptance_samples import observation, producer

    first = observation()
    assert first.suppliers is not None
    suppliers: tuple[Supplier, ...] | None
    rows: tuple[Observation, ...] = (first,)
    expected = {
        "observations": 1,
        "pages": 1,
        "page_records": 1,
        "quarantined": 0,
        "selected_records": 1,
        "ambiguous_records": 0,
        "buyer_records": 1,
        "resolved_records": 1,
        "unresolved_suppliers": 0,
        "partial_suppliers": 0,
        "joint_records": 0,
        "supplier_participations": 1,
        "unknown_cancellations": 0,
        "cancelled_records": 0,
    }
    status, decision = "observed_concentration", "ready"
    if case in {"joint_cancel", "joint", "partial_joint", "duplicates", "partial"}:
        suppliers = (
            *first.suppliers,
            Supplier(1, "987654321" if case != "duplicates" else first.suppliers[0].tax_id, "EL"),
        )
        if case in {"partial", "partial_joint"}:
            suppliers = (
                *first.suppliers,
                *((Supplier(1, "987654321", "GR"),) if case == "partial_joint" else ()),
                Supplier(2, "invalid", "GR"),
                Supplier(3, "111111111", "DE"),
            )
            expected["partial_suppliers"] = 1
            decision = "limited"
        suppliers = tuple(replace(s, ordinal=i) for i, s in enumerate(suppliers))
        rows = (replace(first, suppliers=suppliers, cancelled=case == "joint_cancel"),)
        if case in {"joint_cancel", "joint", "partial_joint"}:
            expected.update(joint_records=1, supplier_participations=2)
        if case == "joint_cancel":
            expected["cancelled_records"] = 1
            decision = "limited"
    elif case in {
        "unknown",
        "empty",
        "ineligible",
        "unresolved_cancel",
        "unresolved_unknown_cancel",
    }:
        suppliers = (
            () if case == "empty" else (Supplier(0, "bad", "GR"),) if case == "ineligible" else None
        )
        rows = (
            replace(
                first,
                suppliers=suppliers,
                cancelled=True
                if case == "unresolved_cancel"
                else None
                if case == "unresolved_unknown_cancel"
                else False,
            ),
        )
        expected.update(resolved_records=0, unresolved_suppliers=1, supplier_participations=0)
        expected["cancelled_records"] = int(case == "unresolved_cancel")
        expected["unknown_cancellations"] = int(case == "unresolved_unknown_cancel")
        status, decision = "buyer_records_unresolved", "limited"
    elif case in {"other_buyer", "missing_buyer", "buyer_changed"}:
        changed = replace(first, buyer_key="OTHER" if case != "missing_buyer" else None)
        rows = (changed,)
        if case == "buyer_changed":
            rows = (
                first,
                replace(
                    changed,
                    observation_id=2,
                    content_sha256="c" * 64,
                    observed_at=first.observed_at.replace(day=2),
                ),
            )
            expected.update(observations=2, pages=2, page_records=2)
        expected.update(buyer_records=0, resolved_records=0, supplier_participations=0)
        status = "no_observed_buyer_records"
    elif case == "global_ambiguity":
        first = replace(first, buyer_key="OTHER", suppliers=None, cancelled=None)
        rows = (first, replace(first, observation_id=2, content_sha256="c" * 64))
        expected.update(
            observations=2,
            pages=2,
            page_records=2,
            selected_records=0,
            ambiguous_records=1,
            buyer_records=0,
            resolved_records=0,
            supplier_participations=0,
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
    elif case == "unknown_cancel":
        rows = (replace(first, cancelled=None),)
        expected["unknown_cancellations"] = 1
        decision = "limited"
    elif case == "after_cutoff":
        rows = (replace(first, observed_at=first.observed_at.replace(day=11)),)
        expected.update(
            selected_records=0, buyer_records=0, resolved_records=0, supplier_participations=0
        )
        status = "no_observations_before_cutoff"
    elif case == "empty_capture":
        rows = ()
        expected.update(
            observations=0,
            page_records=0,
            selected_records=0,
            buyer_records=0,
            resolved_records=0,
            supplier_participations=0,
        )
        status = "empty_capture"
    else:
        rows = (
            first,
            replace(
                first,
                observation_id=2,
                source_id="kimdis:T",
                suppliers=(Supplier(0, "987654321", "GR"),),
            ),
        )
        expected.update(
            observations=2,
            pages=2,
            page_records=2,
            selected_records=2,
            buyer_records=2,
            resolved_records=2,
            supplier_participations=2,
        )
    request, fresh = producer(rows)
    calls = 0

    def reconstruct(*args: object) -> Any:
        nonlocal calls
        calls += 1
        return fresh

    monkeypatch.setattr(adapter, "prepare_buyer_result", reconstruct)
    value = prepare_buyer_acceptance("fixture", request, subject(tmp_path / "reports", fresh.body))
    assert calls == 1
    assert {c.name: c.value for c in value.assessment.counts} == expected
    assert value.assessment.provider_status == status
    assert value.assessment.status == decision
    for detail in (
        "DO_NOT_EXPORT",
        "123456789",
        "987654321",
        "kimdis:S",
        "kimdis.buyer-key:B",
        "/unused",
    ):
        assert detail.encode() not in value.body
