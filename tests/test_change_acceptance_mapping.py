"""Hand-computed distinct unions and honest missing evidence on controlled frames."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from nima.dataops import change_acceptance as adapter
from tests.change_acceptance_samples import captures, producer
from tests.test_citation_acceptance import subject
from tests.test_observed_change import at, sha, ver


@pytest.mark.parametrize(
    "case",
    [
        "plain",
        "one_ambiguous",
        "both_ambiguous",
        "repeated",
        "a_b_a",
        "all_ambiguous",
        "empty",
        "empty_earlier",
        "empty_later",
        "query_mismatch",
        "not_later",
        "incomplete",
        "quarantined",
        "no_runs",
        "all_reasons",
    ],
)
def test_mapping_keeps_distinct_records_and_unavailable_proof(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = captures()
    expected = {
        "observations": 6,
        "pages": 6,
        "page_records": 6,
        "selected_records": 4,
        "ambiguous_records": 0,
        "quarantined": 0,
    }
    decision = "ready"
    if case == "one_ambiguous":
        b = replace(
            b, versions=(*b.versions, ver(7, "Z", "z2", at(3, 1)), ver(8, "Z", "z3", at(3, 1)))
        )
        expected.update(
            observations=8, pages=8, page_records=8, selected_records=3, ambiguous_records=1
        )
        decision = "limited"
    elif case == "both_ambiguous":
        a = replace(a, versions=(*a.versions, ver(7, "Y", "y0", at(1, 1))))
        b = replace(b, versions=(*b.versions, ver(8, "Y", "y3", at(3, 1))))
        expected.update(
            observations=8, pages=8, page_records=8, selected_records=3, ambiguous_records=1
        )
        decision = "limited"
    elif case == "repeated":
        b = replace(b, versions=(*b.versions, ver(7, "X", "x1", at(3, 1))))
        expected.update(observations=7, pages=7, page_records=7)
    elif case == "a_b_a":
        b = replace(
            b, versions=(*b.versions, ver(7, "X", "x2", at(3, 2)), ver(8, "X", "x1", at(3, 3)))
        )
        expected.update(observations=8, pages=8, page_records=8)
    elif case == "all_ambiguous":
        a = replace(a, versions=(ver(1, "X", "x1", at(1, 1)), ver(2, "X", "x2", at(1, 1))))
        b = replace(b, versions=(ver(3, "X", "x1", at(3, 1)), ver(4, "X", "x2", at(3, 1))))
        expected.update(
            observations=4, pages=4, page_records=4, selected_records=0, ambiguous_records=1
        )
        decision = "limited"
    elif case in {"empty", "empty_earlier", "empty_later"}:
        if case != "empty_later":
            a = replace(a, versions=())
        if case != "empty_earlier":
            b = replace(b, versions=())
        n = len(a.versions) + len(b.versions)
        expected.update(observations=n, pages=n, page_records=n, selected_records=n)
        # Empty controlled frames still carry their actual archived empty page.
    elif case == "query_mismatch":
        b = replace(b, runs=(replace(b.runs[0], query_sha256=sha("other")),))
    elif case == "not_later":
        b = replace(b, runs=(replace(b.runs[0], observed_from=a.runs[0].observed_to),))
    elif case == "incomplete":
        b = replace(b, runs=(replace(b.runs[0], collection_complete=False),))
    elif case == "quarantined":
        b = replace(b, runs=(replace(b.runs[0], quarantined=2),))
    elif case == "no_runs":
        a = replace(a, runs=(), versions=())
    elif case == "all_reasons":
        a = replace(a, runs=(replace(a.runs[0], quarantined=2, query_sha256=sha("other")),))
        b = replace(b, runs=(replace(b.runs[0], observed_from=at(1), collection_complete=False),))
    request, fresh = producer(a, b)
    if fresh.cohort_json is None:
        expected = {"quarantined": sum(r.quarantined for c in (a, b) for r in c.runs)}
        decision = "blocked"
    else:
        expected["pages"] = len(fresh.pages)
    calls = 0

    def prepare(*args: object) -> object:
        nonlocal calls
        calls += 1
        return fresh

    monkeypatch.setattr(adapter, "prepare_change_result", prepare)
    assessed = adapter.prepare_change_acceptance(
        "fixture", request, subject(tmp_path / "reports", fresh.body)
    )
    assert calls == 1
    assert assessed.assessment.status == decision
    assert {c.name: c.value for c in assessed.assessment.counts} == expected
    data = json.loads(assessed.body)
    assert data["subject"]["reasons"] == list(fresh.metric.reasons)
    assert data["assessment"]["provider_status"] == fresh.metric.status
    assert data["subject"]["captures"] == request.semantic_payload()
    if fresh.cohort_json is None:
        assert data["assessment"]["cohort_sha256"] is None
        assert data["subject"]["run_profiles"] == []
        assert all(
            c.status == "not_assessed"
            for c in assessed.assessment.checks
            if c.check_id not in {"comparability", "capture_completeness"}
        )
    for value in ("kimdis:X", "kimdis:Y", str(tmp_path), "/private/fixture"):
        assert value.encode() not in assessed.body
