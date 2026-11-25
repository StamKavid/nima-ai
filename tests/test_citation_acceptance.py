"""A freshly reconstructed subject, never a cached success flag, gets a sidecar."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from nima.analytics.citation_readout import prepare_citation_readout
from nima.dataops import citation_acceptance as adapter
from nima.dataops.citation_acceptance import prepare_citation_acceptance
from nima.identity.artifacts import encode
from nima.semantics.citations import ContractObservation, DecisionObservation
from tests.citation_acceptance_samples import producer
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_cohort import seed
from tests.test_graph_pilot_archive import state as archive_state
from tests.test_source_citations import contract, decision


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Acceptance attempted HTTP")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


def subject(root: Path, body: bytes) -> Path:
    root.mkdir(mode=0o700)
    path = root / (hashlib.sha256(body).hexdigest() + ".json")
    path.write_bytes(body)
    path.chmod(0o600)
    return path


def test_reconstructs_one_verified_subject_and_maps_every_counter(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Acceptance must never fetch source evidence")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    request = seed(pg_dsn, tmp_path / "raw")
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_citation_readout(dsn, request)
        path = subject(tmp_path / "reports", body)
        before, originals = state(pg_dsn), archive_state(tmp_path)
        prepared = prepare_citation_acceptance(dsn, request, path)
        data = json.loads(prepared.body)
        assert data["version"] == "nima-citation-acceptance-v1"
        assert data["subject"]["artifact_sha256"] == path.stem
        assert data["assessment"]["status"] == "ready"
        assert {n["name"]: n["value"] for n in data["assessment"]["counts"]} == {
            "observations": 2,
            "pages": 2,
            "page_records": 2,
            "quarantined": 0,
            "selected_records": 1,
            "ambiguous_records": 0,
            "unknown_reference_lists": 0,
            "unresolved_citations": 0,
            "ambiguous_targets": 0,
            "unknown_target_types": 0,
            "mismatched_target_types": 0,
            "unknown_cancellations": 0,
            "cancelled_records": 0,
            "revoked_targets": 0,
        }
        assert prepare_citation_acceptance(dsn, request, path).body == prepared.body
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == originals


def test_shared_revoked_targets_are_edges_and_reobservations_do_not_multiply_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = replace(contract(1, "C"), cancelled=True)
    rows = (first, replace(first, observation_id=2), replace(contract(3, "D"), cancelled=None))
    request, data, result = producer(rows, (replace(decision(), decision_status="REVOKED"),))
    body = encode(data)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    prepared = prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))
    counts = {c.name: c.value for c in prepared.assessment.counts}
    assert counts["observations"] == counts["page_records"] == 4
    assert counts["selected_records"] == counts["revoked_targets"] == 2
    assert counts["cancelled_records"] == counts["unknown_cancellations"] == 1
    assert prepared.assessment.status == "limited"


@pytest.mark.parametrize(
    "case",
    [
        "source_tie",
        "target_tie",
        "a_b_a",
        "unknown_refs",
        "empty_refs",
        "after_cutoff",
        "unknown_type",
        "wrong_type",
        "pending",
    ],
)
def test_hand_computed_selection_and_unknowns(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = contract(1), decision()
    rows: tuple[ContractObservation, ...] = (source,)
    targets: tuple[DecisionObservation, ...] = (target,)
    expected: dict[str, int] = {}
    if case == "source_tie":
        rows += (replace(source, observation_id=2, content_sha256="e" * 64, cancelled=True),)
        expected = {"ambiguous_records": 1, "selected_records": 0, "cancelled_records": 0}
    elif case == "target_tie":
        targets += (replace(target, observation_id=101, content_sha256="e" * 64),)
        expected = {"ambiguous_targets": 1}
    elif case == "a_b_a":
        rows += (
            replace(
                source,
                observation_id=2,
                observed_at=source.observed_at.replace(day=2),
                content_sha256="e" * 64,
                cancelled=True,
            ),
            replace(source, observation_id=3, observed_at=source.observed_at.replace(day=3)),
        )
        expected = {"selected_records": 1, "cancelled_records": 0}
    elif case == "unknown_refs":
        rows = (replace(source, references=None),)
        expected = {"unknown_reference_lists": 1, "unresolved_citations": 0}
    elif case == "empty_refs":
        rows = (replace(source, references=()),)
        expected = {"unknown_reference_lists": 0, "unresolved_citations": 0}
    elif case == "after_cutoff":
        rows = (replace(source, observed_at=source.observed_at.replace(day=11)),)
        expected = {"selected_records": 0, "observations": 2}
    elif case == "unknown_type":
        targets = (replace(target, decision_type=None),)
        expected = {"unknown_target_types": 1}
    elif case == "wrong_type":
        targets = (replace(target, decision_type="Δ.2.2"),)
        expected = {"mismatched_target_types": 1}
    else:
        targets = (replace(target, decision_status="PENDING_REVOCATION"),)
        expected = {"revoked_targets": 0}
    request, data, result = producer(rows, targets)
    body = encode(data)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    prepared = prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))
    counts = {c.name: c.value for c in prepared.assessment.counts}
    for name, value in expected.items():
        assert counts[name] == value
    assert prepared.assessment.status == (
        "ready" if case in {"a_b_a", "empty_refs", "after_cutoff", "pending"} else "limited"
    )
