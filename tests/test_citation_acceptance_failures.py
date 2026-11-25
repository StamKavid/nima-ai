"""Wrong producer shapes, bindings and private subjects cannot become attestations."""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import psycopg
import pytest

from nima.analytics.metric_readout import definition_hash
from nima.analytics.request import RequestError
from nima.analytics.result import ReadoutError
from nima.contracts import acceptance as policy
from nima.dataops import citation_acceptance as adapter
from nima.dataops.citation_acceptance import CitationAcceptanceError, prepare_citation_acceptance
from nima.identity.artifacts import encode
from nima.semantics.citations import MAX_OUTPUT_BYTES
from tests.citation_acceptance_samples import producer
from tests.test_citation_acceptance import subject
from tests.test_source_citations import contract, decision


@pytest.fixture(autouse=True)
def no_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Acceptance attempted HTTP on a failure path")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


@pytest.mark.parametrize(
    "area,key,value",
    [
        ("root", "version", "future"),
        ("root", "request_sha256", "a" * 64),
        ("root", "cohort_sha256", "invalid"),
        ("root", "unexpected", True),
        ("root", "captures", {}),
        ("root", "verified_pages", {}),
        ("root", "evidence", [None]),
        ("root", "model", {}),
        ("capture", "run_id", "bad"),
        ("capture", "source", "wrong"),
        ("capture", "connector_version", None),
        ("capture", "collection_complete", 1),
        ("capture", "normalization_complete", 0),
        ("capture", "quarantined_count", True),
        ("capture", "normalized_observations", -1),
        ("capture", "committed_page_count", 1.0),
        ("capture", "query", []),
        ("capture", "source_attribution", []),
        ("capture", "reported_total_records", True),
        ("capture", "observed_from", 42),
        ("capture", "run_id", "00000000-0000-0000-0000-000000000003"),
        (
            "capture",
            "source_attribution",
            {"license": 7, "documentation_url": "x", "statements": []},
        ),
        ("page", "record_count", True),
        ("page", "raw_sha256", "bad"),
        ("page", "source_ids", [42]),
        ("page", "source", "wrong"),
        ("page", "source_ids", None),
        ("evidence", "observation_id", True),
        ("evidence", "field_locations", []),
        ("evidence", "run_id", "bad"),
        ("evidence", "source_id", 42),
        ("evidence", "observation_id", 0),
        ("evidence", "selection", "wrong"),
        ("quality", "coverage", "invented"),
        ("quality", "raw_bytes", "cached_verified"),
        ("quality", "legal_identity", "certified"),
        ("model", "definition_sha256", "a" * 64),
        ("model", "result", {}),
    ],
)
def test_bad_producer_metadata_is_a_closed_contract_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    area: str,
    key: str,
    value: Any,
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    data: dict[str, Any] = frame
    target = (
        data
        if area == "root"
        else data["captures"][0]
        if area == "capture"
        else data["verified_pages"][0]
        if area == "page"
        else data["evidence"][0]
        if area == "evidence"
        else data[area]
    )
    target[key] = value
    body = encode(data)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    with pytest.raises(CitationAcceptanceError, match="^acceptance_contract$"):
        prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))


def test_every_required_outcome_is_measured_not_defaulted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    del result.outcome_counts["unresolved"]
    cast(dict[str, object], frame["model"])["result"] = result.payload()
    body = encode(frame)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    with pytest.raises(CitationAcceptanceError, match="^acceptance_contract$"):
        prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))


@pytest.mark.parametrize(
    "fault", ["missing", "corrupt", "symlink", "hardlink", "mode", "parent_mode", "oversize"]
)
def test_unusable_subject_stops_before_reconstruction(
    fault: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, _ = producer((contract(1),), (decision(),))
    path = subject(tmp_path / "reports", encode(frame))

    def forbidden(*args: object) -> None:
        pytest.fail("Broken subject must fail before SQL preparation")

    monkeypatch.setattr(adapter, "prepare_citation_readout", forbidden)
    expected = "acceptance_evidence"
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"bad")
    elif fault == "symlink":
        other = path.with_suffix(".original")
        path.rename(other)
        path.symlink_to(other)
    elif fault == "hardlink":
        os.link(path, path.with_suffix(".alias"))
    elif fault == "mode":
        path.chmod(0o644)
    elif fault == "parent_mode":
        path.parent.chmod(0o755)
    else:
        with path.open("wb") as file:
            file.truncate(MAX_OUTPUT_BYTES + 1)
        expected = "acceptance_limit"
    with pytest.raises(CitationAcceptanceError, match=f"^{expected}$"):
        prepare_citation_acceptance("fixture", request, path)


def test_saved_success_flags_never_substitute_for_reconstruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    path = subject(tmp_path / "reports", encode({"verified": True, "status": "ready"}))
    calls = 0

    def fresh(*args: object) -> Any:
        nonlocal calls
        calls += 1
        return encode(frame), result

    monkeypatch.setattr(adapter, "prepare_citation_readout", fresh)
    with pytest.raises(CitationAcceptanceError, match="^acceptance_evidence$"):
        prepare_citation_acceptance("fixture", request, path)
    assert calls == 1


@pytest.mark.parametrize("which", ["page", "evidence", "capture"])
def test_duplicate_producer_rows_are_not_admitted(
    which: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    rows = cast(
        list[object],
        frame[{"page": "verified_pages", "capture": "captures", "evidence": "evidence"}[which]],
    )
    rows.append(rows[0])
    body = encode(frame)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    with pytest.raises(CitationAcceptanceError, match="^acceptance_contract$"):
        prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))


@pytest.mark.parametrize("body", [b'{"version":1,"version":2}', b'{"x":NaN}', b"\xff", b"[]"])
def test_strict_json_is_required_even_from_the_producer(
    body: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _, result = producer((contract(1),), (decision(),))
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    with pytest.raises(CitationAcceptanceError, match="^acceptance_contract$"):
        prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))


@pytest.mark.parametrize(
    "case", ["dsn", "relative", "suffix", "digest", "nul", "double", "parent", "git", "request"]
)
def test_invalid_configuration_stops_before_reconstruction(case: str, tmp_path: Path) -> None:
    request, _, _ = producer((contract(1),), (decision(),))
    path = Path("/PRIVATE/" + "a" * 64 + ".json")
    if case == "relative":
        path = Path("relative.json")
    elif case == "suffix":
        path = path.with_suffix(".txt")
    elif case == "digest":
        path = path.with_name("ABC.json")
    elif case == "nul":
        path = Path("/PRIVATE/\x00.json")
    elif case == "double":
        path = Path("//PRIVATE/" + path.name)
    elif case == "parent":
        path = Path("/PRIVATE/../" + path.name)
    elif case == "git":
        path = Path("/PRIVATE/.git/" + path.name)
    elif case == "request":
        request = replace(request, kimdis_run_ids=())
    with pytest.raises(CitationAcceptanceError, match="^acceptance_input$"):
        prepare_citation_acceptance(" " if case == "dsn" else "fixture", request, path)


@pytest.mark.parametrize(
    "error,expected",
    [
        (RequestError("citation_input"), "acceptance_input"),
        (RequestError("citation_limit"), "acceptance_limit"),
        (RequestError("unknown"), "acceptance_input"),
        (ReadoutError("citation_evidence"), "acceptance_evidence"),
        (ReadoutError("citation_database"), "acceptance_database"),
        (ReadoutError("citation_contract"), "acceptance_contract"),
        (ReadoutError("citation_limit"), "acceptance_limit"),
        (ReadoutError("private_details"), "acceptance_contract"),
        (psycopg.OperationalError("PRIVATE_DSN"), "acceptance_database"),
    ],
)
def test_preparation_errors_are_closed(
    error: Exception, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, _ = producer((contract(1),), (decision(),))

    def fail(*args: object) -> Any:
        raise error

    monkeypatch.setattr(adapter, "prepare_citation_readout", fail)
    with pytest.raises(CitationAcceptanceError, match=f"^{expected}$"):
        prepare_citation_acceptance(
            "fixture", request, subject(tmp_path / "reports", encode(frame))
        )


@pytest.mark.parametrize(
    "fresh,expected",
    [(None, "acceptance_contract"), (b"x" * (MAX_OUTPUT_BYTES + 1), "acceptance_limit")],
)
def test_unbounded_or_wrong_type_fresh_output_is_refused(
    fresh: object, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (fresh, result))
    with pytest.raises(CitationAcceptanceError, match=f"^{expected}$"):
        prepare_citation_acceptance(
            "fixture", request, subject(tmp_path / "reports", encode(frame))
        )


@pytest.mark.parametrize("case", ["policy_drift", "returned_binding", "sidecar_limit"])
def test_policy_and_output_contracts_cannot_silently_drift(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    body = encode(frame)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    expected = "acceptance_contract"
    if case == "policy_drift":
        monkeypatch.setattr(policy, "definition", lambda: {"version": "unknown"})
    elif case == "returned_binding":
        evaluate = policy.evaluate
        monkeypatch.setattr(
            policy, "evaluate", lambda f: replace(evaluate(f), request_sha256="d" * 64)
        )
    else:
        monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", 1)
        expected = "acceptance_limit"
    with pytest.raises(CitationAcceptanceError, match=f"^{expected}$"):
        prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))


@pytest.mark.parametrize(
    "case",
    [
        "check_status",
        "check_reason",
        "limitation",
        "model_scalar",
        "model_list",
        "model_list_type",
        "limits",
    ],
)
def test_closed_producer_and_assessment_vocabulary(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    model = cast(dict[str, Any], frame["model"])
    if case == "model_scalar":
        model["definition"]["matching"] = None
    elif case == "model_list":
        model["definition"]["diavgeia_normalizers"] = [42]
    elif case == "model_list_type":
        model["definition"]["diavgeia_normalizers"] = None
    elif case == "limits":
        frame["interpretation_limits"] = 42
    if case.startswith("model"):
        model["definition_sha256"] = definition_hash(model["definition"])
    evaluate = policy.evaluate
    if case in {"check_status", "check_reason", "limitation"}:

        def malformed(facts: policy.DatasetFacts) -> policy.Assessment:
            assessed = evaluate(facts)
            if case == "limitation":
                return replace(assessed, limitations=("PRIVATE_DATA",))
            check = replace(
                assessed.checks[0],
                **{"status" if case == "check_status" else "reason": "PRIVATE_DATA"},
            )
            return replace(assessed, checks=(check, *assessed.checks[1:]))

        monkeypatch.setattr(policy, "evaluate", malformed)
    body = encode(frame)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    with pytest.raises(CitationAcceptanceError, match="^acceptance_contract$"):
        prepare_citation_acceptance("fixture", request, subject(tmp_path / "reports", body))


@pytest.mark.parametrize(
    "case,expected_decision", [("blocked", "blocked"), ("unknown_definition", "not_assessed")]
)
def test_negative_fitness_can_be_published_after_successful_reconstruction(
    case: str, expected_decision: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    if case == "blocked":
        # Coherent typed/serialized result, but incompatible measured denominator.
        result = replace(result, records=3)
        cast(dict[str, object], frame["model"])["result"] = result.payload()
    else:
        model = cast(dict[str, Any], frame["model"])
        model["definition"]["status"] = "reviewed"
        model["definition_sha256"] = definition_hash(model["definition"])
    body = encode(frame)
    path = subject(tmp_path / "reports", body)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    monkeypatch.setattr(adapter, "read_citation_request", lambda _: request)
    output = tmp_path / "output"
    exported = adapter.export_citation_acceptance("fixture", tmp_path / "request", path, output)
    assert exported.decision == expected_decision
    sidecar = json.loads((output / (exported.artifact_sha256 + ".json")).read_bytes())
    assert sidecar["assessment"]["status"] == expected_decision


@pytest.mark.parametrize("case", ["relative", "request", "oserror", "conflict"])
def test_export_failures_are_private_and_never_fake_success(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    body = encode(frame)
    path = subject(tmp_path / "reports", body)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    output = tmp_path / "output"
    expected = "acceptance_input" if case in {"relative", "request"} else "acceptance_output"
    if case != "request":
        monkeypatch.setattr(adapter, "read_citation_request", lambda _: request)
    if case == "oserror":

        def fail(*args: object) -> Any:
            raise OSError("PRIVATE")

        monkeypatch.setattr(adapter, "publish", fail)
    elif case == "conflict":
        prepared = prepare_citation_acceptance("fixture", request, path)
        output.mkdir(mode=0o700)
        target = output / (hashlib.sha256(prepared.body).hexdigest() + ".json")
        target.write_bytes(b"conflicting")
        target.chmod(0o600)
    with pytest.raises(CitationAcceptanceError, match=f"^{expected}$"):
        adapter.export_citation_acceptance(
            "fixture",
            tmp_path / "missing",
            path,
            Path("relative") if case == "relative" else output,
        )


def test_sidecar_byte_limit_accepts_exact_bound_and_refuses_one_less(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, frame, result = producer((contract(1),), (decision(),))
    body = encode(frame)
    report = subject(tmp_path / "reports", body)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    original = prepare_citation_acceptance("fixture", request, report).body
    assert isinstance(original, bytes) and len(original) <= 64 * 1024
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(original))
    assert prepare_citation_acceptance("fixture", request, report).body == original
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(original) - 1)
    with pytest.raises(CitationAcceptanceError, match="^acceptance_limit$"):
        prepare_citation_acceptance("fixture", request, report)
