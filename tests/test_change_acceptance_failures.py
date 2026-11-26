"""Closed producer/policy/file boundaries; no saved JSON flag may substitute proof."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest

from nima.analytics.metric_readout import cohort_hash, definition_hash
from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.analytics.snapshot import MAX_INPUT_BYTES
from nima.contracts import acceptance as policy
from nima.dataops import change_acceptance as adapter
from nima.dataops.change_acceptance import ChangeAcceptanceError
from nima.identity.artifacts import encode
from tests.change_acceptance_samples import captures, producer, request_file
from tests.test_citation_acceptance import subject


@pytest.mark.parametrize(
    "fault",
    [
        "fresh_type",
        "body_type",
        "fresh_limit",
        "metric_type",
        "pages_type",
        "cohort_type",
        "cohort_limit",
        "reasons_definition",
        "unknown_reason",
        "run_selection",
        "run_facts",
        "incomparable_evidence",
        "added_existing",
        "missing_existing",
        "changed_equal",
        "unchanged_different",
        "count_drift",
        "duplicate_category",
        "omitted_category",
    ],
)
def test_protocol_rejects_missing_or_contradictory_fresh_proof(
    fault: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = captures()
    if fault == "incomparable_evidence":
        b = replace(b, runs=(replace(b.runs[0], collection_complete=False),))
    request, fresh = producer(a, b)
    body = json.loads(fresh.body)
    expected = "acceptance_contract"
    if fault == "fresh_type":
        fresh = cast(Any, None)
    elif fault == "body_type":
        fresh = replace(fresh, body=cast(Any, "wrong"))
    elif fault == "fresh_limit":
        fresh = replace(fresh, body=b"x" * (MAX_RESULT_BYTES + 1))
        expected = "acceptance_limit"
    elif fault == "metric_type":
        fresh = replace(fresh, metric=cast(Any, None))
    elif fault == "pages_type":
        fresh = replace(fresh, pages=cast(Any, None))
    elif fault == "cohort_type":
        fresh = replace(fresh, cohort_json=cast(Any, 42))
    elif fault == "cohort_limit":
        fresh = replace(fresh, cohort_json=" " * (MAX_INPUT_BYTES + 1))
        expected = "acceptance_limit"
    elif fault == "reasons_definition":
        body["metric"]["definition"]["reasons"] = []
        body["metric"]["definition_sha256"] = definition_hash(body["metric"]["definition"])
    elif fault == "run_selection":
        fresh = replace(
            fresh,
            earlier=replace(
                fresh.earlier,
                runs=(
                    replace(fresh.earlier.runs[0], run_id="00000000-0000-4000-8000-000000000003"),
                ),
            ),
        )
    elif fault == "run_facts":
        body["run_facts"]["earlier"][0]["collection_complete"] = 1
    elif fault == "incomparable_evidence":
        body["evidence"] = [{}]
    else:
        result = fresh.metric
        if fault == "unknown_reason":
            result = replace(result, reasons=("PRIVATE",))
        elif fault == "added_existing":
            result = replace(result, added=(replace(result.added[0], source_id="kimdis:X"),))
        elif fault == "missing_existing":
            result = replace(
                result,
                missing_from_later_capture=(
                    replace(result.missing_from_later_capture[0], source_id="kimdis:X"),
                ),
            )
        elif fault == "changed_equal":
            result = replace(
                result,
                changed=(
                    replace(result.changed[0], earlier_version=result.changed[0].later_version),
                ),
            )
        elif fault == "unchanged_different":
            result = replace(result, unchanged=("kimdis:Y",))
        elif fault == "count_drift":
            result = replace(result, counts=replace(result.counts, added=2))
        elif fault == "duplicate_category":
            result = replace(
                result, added=(*result.added, *result.added), counts=replace(result.counts, added=2)
            )
        elif fault == "omitted_category":
            result = replace(result, added=(), counts=replace(result.counts, added=0))
        fresh = replace(fresh, metric=result)
        body["metric"]["result"] = result.payload()
    if fault not in {
        "fresh_type",
        "body_type",
        "fresh_limit",
        "metric_type",
        "pages_type",
        "cohort_type",
        "cohort_limit",
    }:
        fresh = replace(fresh, body=encode(body))
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    report = subject(
        tmp_path / "reports",
        fresh.body if fault not in {"fresh_type", "body_type", "fresh_limit"} else encode(body),
    )
    with pytest.raises(ChangeAcceptanceError, match=f"^{expected}$"):
        adapter.prepare_change_acceptance("fixture", request, report)


@pytest.mark.parametrize("fault", ["witness", "summary", "ambiguous", "categories"])
def test_typed_category_bindings_cannot_disagree_with_capture_versions(
    fault: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer(*captures())
    metric = fresh.metric
    if fault == "witness":
        metric = replace(
            metric, changed=(replace(metric.changed[0], later_observation_ids=(999,)),)
        )
    elif fault == "summary":
        metric = replace(metric, earlier=replace(metric.earlier, records=999))
    elif fault == "ambiguous":
        metric = replace(
            metric, earlier=replace(metric.earlier, ambiguous_source_ids=("kimdis:Z",))
        )
    else:
        metric = replace(metric, unchanged=("kimdis:Z",))
    body = json.loads(fresh.body)
    body["metric"]["result"] = metric.payload()
    fresh = replace(fresh, metric=metric, body=encode(body))
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_change_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


@pytest.mark.parametrize(
    "path,value",
    [
        ("version", "future"),
        ("source", "other"),
        ("request", {}),
        ("request_sha256", "f" * 64),
        ("cohort_sha256", "f" * 64),
        ("metric.definition_sha256", "f" * 64),
        ("metric.result", {}),
        ("metric.definition.source", "other"),
        ("metric.definition.status", "unknown"),
        ("metric.definition.abstains", None),
        ("metric.definition.revision", ""),
        ("verified_pages", None),
        ("verified_pages", []),
        ("evidence", [None]),
        ("evidence", []),
        ("quality.raw_bytes", "cached"),
        ("interpretation_limits", [42]),
    ],
)
def test_malformed_fresh_envelope_fails_closed(
    path: str, value: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer(*captures())
    data = json.loads(fresh.body)
    target = data
    parts = path.split(".")
    for key in parts[:-1]:
        target = target[key]
    target[parts[-1]] = value
    fresh = replace(fresh, body=encode(data))
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_change_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


@pytest.mark.parametrize(
    "area,key,value",
    [
        ("root", "runs", {}),
        ("root", "pages", {}),
        ("root", "records", {}),
        ("run", "status", "interrupted"),
        ("run", "managed", 1),
        ("run", "query", []),
        ("run", "run_id", "00000000-0000-0000-0000-000000000003"),
        ("run", "connector_version", None),
        ("run", "quarantine_count", True),
        ("run", "quarantine_count", -1),
        ("page", "record_count", True),
        ("record", "observation_id", True),
        ("record", "record_index", 99),
        ("record", "source_id", "kimdis:OTHER"),
    ],
)
def test_frozen_metadata_cannot_disagree(
    area: str, key: str, value: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer(*captures())
    data = json.loads(cast(str, fresh.cohort_json))
    row = (
        data
        if area == "root"
        else data[{"run": "runs", "page": "pages", "record": "records"}[area]][0]
    )
    row[key] = value
    body = json.loads(fresh.body)
    body["cohort_sha256"] = cohort_hash(data)
    fresh = replace(fresh, body=encode(body), cohort_json=encode(data).decode())
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_change_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("analytics_input", "acceptance_input"),
        ("analytics_limit", "acceptance_limit"),
        *[
            (x, "acceptance_evidence")
            for x in (
                "analytics_archive",
                "analytics_coverage",
                "analytics_projection",
                "analytics_evidence",
            )
        ],
        *[
            (x, "acceptance_database")
            for x in ("analytics_role", "analytics_schema", "analytics_database")
        ],
        *[
            (x, "acceptance_contract")
            for x in (
                "analytics_version",
                "analytics_metric",
                "analytics_contract",
                "PRIVATE_ERROR",
            )
        ],
        ("analytics_output", "acceptance_output"),
        ("psycopg", "acceptance_database"),
    ],
)
def test_verifier_errors_are_closed(
    reason: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer(*captures())

    def fail(*args: object) -> Any:
        if reason == "psycopg":
            raise psycopg.OperationalError("PRIVATE_DSN")
        raise ReadoutError(reason)

    monkeypatch.setattr(adapter, "prepare_change_result", fail)
    with pytest.raises(ChangeAcceptanceError, match=f"^{expected}$"):
        adapter.prepare_change_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


@pytest.mark.parametrize("body", [b"\xff", b"{}", b'{"x":1,"x":2}', b'{"x":NaN}'])
def test_fresh_json_is_strict(body: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, fresh = producer(*captures())
    fresh = replace(fresh, body=body)
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_change_acceptance("fixture", request, subject(tmp_path / "reports", body))


def test_saved_success_and_oversize_subject_are_not_a_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer(*captures())
    calls = 0

    def reconstruct(*args: object) -> Any:
        nonlocal calls
        calls += 1
        return fresh

    monkeypatch.setattr(adapter, "prepare_change_result", reconstruct)
    report = subject(tmp_path / "reports", encode({"verified": True, "status": "ready"}))
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_evidence$"):
        adapter.prepare_change_acceptance("fixture", request, report)
    assert calls == 1
    report = subject(tmp_path / "oversize", b"x" * (MAX_RESULT_BYTES + 1))
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_limit$"):
        adapter.prepare_change_acceptance("fixture", request, report)
    assert calls == 1


@pytest.mark.parametrize(
    "case", ["dsn", "relative", "suffix", "hash", "type", "overlap", "side_type", "binding"]
)
def test_configuration_fails_before_inspection(case: str, tmp_path: Path) -> None:
    request, _ = producer(*captures())
    report = tmp_path / ("a" * 64 + ".json")
    if case == "type":
        request = cast(Any, None)
    elif case == "overlap":
        request = replace(request, earlier_run_ids=request.later_run_ids)
    elif case == "side_type":
        request = replace(request, earlier_run_ids=cast(Any, (42,)))
    elif case == "binding":
        request = replace(request, archive_bindings=cast(Any, (None,)))
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_input$"):
        adapter.prepare_change_acceptance(
            " " if case == "dsn" else "fixture",
            request,
            Path("relative")
            if case == "relative"
            else report.with_suffix(".txt")
            if case == "suffix"
            else report.with_name("BAD.json")
            if case == "hash"
            else report,
        )


@pytest.mark.parametrize(
    "case", ["policy", "binding", "check_status", "check_reason", "limitations"]
)
def test_policy_drift_cannot_publish(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer(*captures())
    if case == "policy":
        monkeypatch.setattr(policy, "definition", lambda: {"version": "future"})
    else:
        evaluate = policy.evaluate

        def wrong(facts: policy.DatasetFacts) -> policy.Assessment:
            result = evaluate(facts)
            if case == "binding":
                return replace(result, request_sha256="f" * 64)
            if case == "limitations":
                return replace(result, limitations=("PRIVATE",))
            check = replace(
                result.checks[0], **{"status" if case == "check_status" else "reason": "PRIVATE"}
            )
            return replace(result, checks=(check, *result.checks[1:]))

        monkeypatch.setattr(policy, "evaluate", wrong)
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_change_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


def test_supported_unadmitted_definition_is_not_assessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.semantics.observed_change import definition

    meta = definition()
    meta["status"] = "reviewed"
    request, fresh = producer(*captures())
    doc = json.loads(fresh.body)
    doc["metric"]["definition"] = meta
    doc["metric"]["definition_sha256"] = definition_hash(meta)
    fresh = replace(fresh, body=encode(doc))
    assert definition_hash(meta) == json.loads(fresh.body)["metric"]["definition_sha256"]
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    report = subject(tmp_path / "reports", fresh.body)
    result = adapter.prepare_change_acceptance("fixture", request, report)
    assert result.assessment.status == "not_assessed"
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(result.body))
    assert adapter.prepare_change_acceptance("fixture", request, report).body == result.body
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(result.body) - 1)
    with pytest.raises(ChangeAcceptanceError, match="^acceptance_limit$"):
        adapter.prepare_change_acceptance("fixture", request, report)


@pytest.mark.parametrize(
    "case",
    ["request_relative", "output_relative", "request_missing", "request_limit", "conflict", "io"],
)
def test_export_failures_never_fake_success(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.analytics.request import MAX_REQUEST_BYTES

    request, fresh = producer(*captures())
    selection = request_file(request, tmp_path / "request.json")
    report = subject(tmp_path / "reports", fresh.body)
    output = tmp_path / "output"
    monkeypatch.setattr(adapter, "prepare_change_result", lambda *_: fresh)
    expected = "acceptance_input"
    if case == "request_relative":
        selection = Path("request.json")
    elif case == "output_relative":
        output = Path("output")
    elif case == "request_missing":
        selection.unlink()
    elif case == "request_limit":
        selection.write_bytes(b"x" * (MAX_REQUEST_BYTES + 1))
        expected = "acceptance_limit"
    elif case == "conflict":
        prepared = adapter.prepare_change_acceptance("fixture", request, report)
        output.mkdir(mode=0o700)
        path = output / (hashlib.sha256(prepared.body).hexdigest() + ".json")
        path.write_bytes(b"conflict")
        path.chmod(0o600)
        expected = "acceptance_output"
    else:

        def fail(*args: object) -> Any:
            raise OSError("PRIVATE")

        monkeypatch.setattr(adapter, "publish", fail)
        expected = "acceptance_output"
    with pytest.raises(ChangeAcceptanceError, match=f"^{expected}$"):
        adapter.export_change_acceptance("fixture", selection, report, output)
