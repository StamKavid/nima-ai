"""Exact insight states and cited arithmetic over controlled, fictional provider frames."""

import json
from pathlib import Path

import pytest

from nima.insights import buyer_participation as insight
from tests.buyer_insight_samples import frame


def test_ready_draft_is_not_a_certified_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, fitness = frame(tmp_path, monkeypatch)
    assert fitness.assessment.status == "ready"
    result = insight._compose(request, parent, fitness)
    data = json.loads(result.body)
    assert result.status == data["status"] == "review_required"
    assert data["answer"] is None
    assert data["reason_codes"] == ["metric_not_certified"]
    assert data["data_fitness"] == json.loads(fitness.body)
    assert b"111111111" not in result.body and b"222222222" not in result.body


def test_unknown_record_preserves_limited_and_draft_reasons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, fitness = frame(tmp_path, monkeypatch, unknown=True)
    assert fitness.assessment.status == "limited"
    result = insight._compose(request, parent, fitness)
    data = json.loads(result.body)
    assert result.status == "insufficient_evidence" and data["answer"] is None
    assert {"metric_not_certified", "data_limited", "unresolved_suppliers"} <= set(
        data["reason_codes"]
    )
    assert data["reason_codes"] == sorted(set(data["reason_codes"]))


def test_fictional_certified_ties_keep_exact_counts_and_selected_witnesses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.buyer_insight_samples import certified

    request, parent, fitness = frame(tmp_path, monkeypatch)
    parent, fitness = certified(parent, fitness)
    result = insight._compose(request, parent, fitness)
    data = json.loads(result.body)
    assert result.status == "answered" and data["reason_codes"] == []
    answer = data["answer"]
    assert answer["share"] == {"numerator": 2, "denominator": 3}
    assert answer["participation_total"] == 4 and answer["joint_records"] == 1
    assert answer["unresolved_share"] == {"numerator": 0, "denominator": 3}
    assert [g["supplier_ref"] for g in answer["top_groups"]] == [
        "/metric/result/suppliers/0",
        "/metric/result/suppliers/1",
    ]
    assert answer["top_groups"][0]["record_refs"] == [
        "/metric/result/records/0",
        "/metric/result/records/2",
    ]
    assert answer["top_groups"][1]["record_refs"] == [
        "/metric/result/records/1",
        "/metric/result/records/2",
    ]
    assert answer["denominator_record_refs"] == [f"/metric/result/records/{i}" for i in range(3)]
    assert answer["evidence_refs"] == ["/evidence/0", "/evidence/1", "/evidence/2"]
    assert "2 of 3" in answer["statement"]
    for tax in (b"111111111", b"222222222"):
        assert tax not in result.body


def test_parent_must_match_the_freshly_bound_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, fitness = frame(tmp_path, monkeypatch)
    with pytest.raises(insight.InsightError, match="^insight_contract$"):
        insight._compose(request, parent + b" ", fitness)


@pytest.mark.parametrize("status", ["blocked", "not_assessed"])
def test_returned_unusable_assessments_are_preserved(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import asdict, replace

    from nima.identity.artifacts import encode

    request, parent, fitness = frame(tmp_path, monkeypatch)
    assessment = replace(fitness.assessment, status=status)
    sidecar = json.loads(fitness.body)
    sidecar["assessment"] = asdict(assessment)
    fitness = replace(fitness, assessment=assessment, body=encode(sidecar))
    result = insight._compose(request, parent, fitness)
    data = json.loads(result.body)
    assert result.status == "insufficient_evidence" and data["answer"] is None
    assert f"data_{status}" in data["reason_codes"]


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "older",
        "cutoff",
        "wrong_buyer",
        "wrong_version",
        "wrong_source",
        "wrong_normalizer",
        "missing_page",
        "duplicate",
        "duplicate_page",
        "no_ids",
        "missing_top",
        "wrong_count",
        "wrong_top_count",
        "wrong_denominator",
    ],
)
def test_fictional_answer_cannot_point_at_unselected_or_incomplete_witnesses(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    from dataclasses import replace

    from nima.identity.artifacts import encode
    from tests.buyer_insight_samples import certified

    request, parent, fitness = frame(tmp_path, monkeypatch)
    parent, fitness = certified(parent, fitness)
    report = json.loads(parent)
    evidence, result = report["evidence"], report["metric"]["result"]
    if kind == "missing":
        evidence.pop(0)
    elif kind == "duplicate":
        evidence.append(evidence[0])
    elif kind == "duplicate_page":
        report["verified_pages"].append(report["verified_pages"][0])
    elif kind == "no_ids":
        result["records"][0]["observation_ids"] = []
    elif kind == "missing_top":
        result["top_supplier_keys"] = []
    elif kind == "wrong_count":
        result["suppliers"][0]["record_count"] += 1
    elif kind == "wrong_top_count":
        result["top_record_count"] += 1
    elif kind == "wrong_denominator":
        result["resolved_records"] += 1
    else:
        field, value = {
            "older": ("selection", "earlier_observation"),
            "cutoff": ("observed_at", "2099-01-01T00:00:00+00:00"),
            "wrong_buyer": ("reported_buyer_key", "OTHER"),
            "wrong_version": ("content_sha256", "f" * 64),
            "wrong_source": ("source_id", "kimdis:OTHER"),
            "wrong_normalizer": ("normalizer_version", "future"),
            "missing_page": ("page_number", 99),
        }[kind]
        evidence[0][field] = value
    parent = encode(report)
    digest = hashlib.sha256(parent).hexdigest()
    sidecar = json.loads(fitness.body)
    sidecar["subject"]["artifact_sha256"] = digest
    fitness = replace(fitness, subject_sha256=digest, body=encode(sidecar))
    with pytest.raises(insight.InsightError, match="^insight_contract$"):
        insight._compose(request, parent, fitness)
