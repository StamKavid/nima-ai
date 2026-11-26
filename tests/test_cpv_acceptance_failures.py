"""No saved flag or malformed producer frame may attest a CPV report."""

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
from nima.dataops import cpv_acceptance as adapter
from nima.dataops.cpv_acceptance import CpvAcceptanceError
from nima.identity.artifacts import encode
from tests.cpv_acceptance_samples import observation, producer
from tests.test_citation_acceptance import subject


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
        ("metric.definition.normalizer", None),
        ("metric.definition.cpv", ""),
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
    request, fresh = producer((observation(),))
    data = json.loads(fresh.body)
    target = data
    parts = path.split(".")
    for key in parts[:-1]:
        target = target[key]
    target[parts[-1]] = value
    fresh = replace(fresh, body=encode(data))
    monkeypatch.setattr(adapter, "prepare_cpv_result", lambda *_: fresh)
    with pytest.raises(CpvAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_cpv_acceptance(
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
    request, fresh = producer((observation(),))
    data = json.loads(fresh.cohort_json)
    row = (
        data
        if area == "root"
        else data[{"run": "runs", "page": "pages", "record": "records"}[area]][0]
    )
    row[key] = value
    body = json.loads(fresh.body)
    body["cohort_sha256"] = cohort_hash(data)
    fresh = replace(fresh, body=encode(body), cohort_json=encode(data).decode())
    monkeypatch.setattr(adapter, "prepare_cpv_result", lambda *_: fresh)
    with pytest.raises(CpvAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_cpv_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


@pytest.mark.parametrize(
    "case",
    [
        "fresh_type",
        "body_type",
        "fresh_limit",
        "cohort_type",
        "cohort_limit",
        "metric_type",
        "observations_type",
        "pages_type",
        "duplicate_ids",
        "zero_id",
        "page_facts",
        "cited_facts",
        "duplicate_records",
        "ambiguous_ids",
        "record_flags",
        "selected_count",
        "class_count",
        "date_count",
        "unknown_class",
        "unknown_date",
        "invalid_cancel",
        "provider_status",
    ],
)
def test_internal_boundaries_refuse_bad_types_or_diagnostics(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer((observation(),))
    original = fresh.body
    body = json.loads(original)
    expected = "acceptance_contract"
    if case == "fresh_type":
        fresh = cast(Any, None)
    elif case == "body_type":
        fresh = replace(fresh, body=cast(Any, "bad"))
    elif case == "fresh_limit":
        fresh = replace(fresh, body=b"x" * (MAX_RESULT_BYTES + 1))
        expected = "acceptance_limit"
    elif case == "cohort_type":
        fresh = replace(fresh, cohort_json=cast(Any, None))
    elif case == "cohort_limit":
        fresh = replace(fresh, cohort_json=" " * (MAX_INPUT_BYTES + 1))
        expected = "acceptance_limit"
    elif case == "metric_type":
        fresh = replace(fresh, metric=cast(Any, None))
    elif case == "observations_type":
        fresh = replace(fresh, observations=cast(Any, None))
    elif case == "pages_type":
        fresh = replace(fresh, pages=cast(Any, None))
    elif case == "duplicate_ids":
        fresh = replace(fresh, observations=(*fresh.observations, *fresh.observations))
    elif case == "zero_id":
        fresh = replace(fresh, observations=(replace(fresh.observations[0], observation_id=0),))
    elif case == "page_facts":
        fresh = replace(fresh, pages=(replace(fresh.pages[0], record_count=99),))
    elif case == "cited_facts":
        body["evidence"][0]["cancelled"] = True
        fresh = replace(fresh, body=encode(body))
    else:
        result = fresh.metric
        record = result.records[0]
        if case == "duplicate_records":
            result = replace(result, records=(record, record))
        elif case == "ambiguous_ids":
            result = replace(result, ambiguous_source_ids=(record.source_id,))
        elif case == "record_flags":
            result = replace(result, records=(replace(record, ambiguous=cast(Any, 1)),))
        elif case == "selected_count":
            result = replace(result, coverage=replace(result.coverage, selected_records=2))
        elif case == "class_count":
            result = replace(result, coverage=replace(result.coverage, classified=True))
        elif case == "date_count":
            result = replace(result, coverage=replace(result.coverage, period_parsed=0))
        elif case == "unknown_class":
            result = replace(
                result,
                records=(replace(record, classification="PRIVATE"),),
                coverage=replace(result.coverage, classified=0),
            )
        elif case == "unknown_date":
            result = replace(
                result,
                records=(replace(record, date_outcome="PRIVATE"),),
                coverage=replace(result.coverage, period_parsed=0),
            )
        elif case == "invalid_cancel":
            result = replace(result, records=(replace(record, cancelled=cast(Any, 1)),))
        else:
            result = replace(result, status="future")
        body["metric"]["result"] = result.payload()
        fresh = replace(fresh, metric=result, body=encode(body))
    inspected = original if case in {"fresh_type", "body_type", "fresh_limit"} else fresh.body
    monkeypatch.setattr(adapter, "prepare_cpv_result", lambda *_: fresh)
    with pytest.raises(CpvAcceptanceError, match=f"^{expected}$"):
        adapter.prepare_cpv_acceptance("fixture", request, subject(tmp_path / "reports", inspected))


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
    request, fresh = producer((observation(),))

    def fail(*args: object) -> Any:
        if reason == "psycopg":
            raise psycopg.OperationalError("PRIVATE_DSN")
        raise ReadoutError(reason)

    monkeypatch.setattr(adapter, "prepare_cpv_result", fail)
    with pytest.raises(CpvAcceptanceError, match=f"^{expected}$"):
        adapter.prepare_cpv_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


@pytest.mark.parametrize("body", [b"\xff", b"{}", b'{"x":1,"x":2}', b'{"x":NaN}'])
def test_fresh_json_is_strict(body: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, fresh = producer((observation(),))
    fresh = replace(fresh, body=body)
    monkeypatch.setattr(adapter, "prepare_cpv_result", lambda *_: fresh)
    with pytest.raises(CpvAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_cpv_acceptance("fixture", request, subject(tmp_path / "reports", body))


def test_saved_success_and_oversize_subject_are_not_a_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer((observation(),))
    calls = 0

    def reconstruct(*args: object) -> Any:
        nonlocal calls
        calls += 1
        return fresh

    monkeypatch.setattr(adapter, "prepare_cpv_result", reconstruct)
    report = subject(tmp_path / "reports", encode({"verified": True, "status": "ready"}))
    with pytest.raises(CpvAcceptanceError, match="^acceptance_evidence$"):
        adapter.prepare_cpv_acceptance("fixture", request, report)
    assert calls == 1
    report = subject(tmp_path / "oversize", b"x" * (MAX_RESULT_BYTES + 1))
    with pytest.raises(CpvAcceptanceError, match="^acceptance_limit$"):
        adapter.prepare_cpv_acceptance("fixture", request, report)
    assert calls == 1


@pytest.mark.parametrize(
    "case", ["dsn", "relative", "suffix", "hash", "type", "cpv", "period", "binding"]
)
def test_configuration_fails_before_inspection(case: str, tmp_path: Path) -> None:
    request, _ = producer((observation(),))
    report = tmp_path / ("a" * 64 + ".json")
    if case == "type":
        request = cast(Any, None)
    elif case == "cpv":
        request = replace(request, cpv_base_code="bad")
    elif case == "period":
        request = replace(request, period_from=cast(Any, 42))
    elif case == "binding":
        request = replace(request, archive_bindings=cast(Any, (None,)))
    with pytest.raises(CpvAcceptanceError, match="^acceptance_input$"):
        adapter.prepare_cpv_acceptance(
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
    request, fresh = producer((observation(),))
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
    monkeypatch.setattr(adapter, "prepare_cpv_result", lambda *_: fresh)
    with pytest.raises(CpvAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_cpv_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


def test_supported_unadmitted_definition_is_not_assessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.semantics.cpv_period import definition

    meta = definition()
    meta["status"] = "reviewed"
    request, fresh = producer((observation(),), definition=meta)
    assert definition_hash(meta) == json.loads(fresh.body)["metric"]["definition_sha256"]
    monkeypatch.setattr(adapter, "prepare_cpv_result", lambda *_: fresh)
    report = subject(tmp_path / "reports", fresh.body)
    result = adapter.prepare_cpv_acceptance("fixture", request, report)
    assert result.assessment.status == "not_assessed"
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(result.body))
    assert adapter.prepare_cpv_acceptance("fixture", request, report).body == result.body
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(result.body) - 1)
    with pytest.raises(CpvAcceptanceError, match="^acceptance_limit$"):
        adapter.prepare_cpv_acceptance("fixture", request, report)


@pytest.mark.parametrize(
    "case",
    ["request_relative", "output_relative", "request_missing", "request_limit", "conflict", "io"],
)
def test_export_failures_never_fake_success(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.analytics.request import MAX_REQUEST_BYTES
    from tests.cpv_acceptance_samples import request_file

    request, fresh = producer((observation(),))
    selection = request_file(request, tmp_path / "request.json")
    report = subject(tmp_path / "reports", fresh.body)
    output = tmp_path / "output"
    monkeypatch.setattr(adapter, "prepare_cpv_result", lambda *_: fresh)
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
        prepared = adapter.prepare_cpv_acceptance("fixture", request, report)
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
    with pytest.raises(CpvAcceptanceError, match=f"^{expected}$"):
        adapter.export_cpv_acceptance("fixture", selection, report, output)
