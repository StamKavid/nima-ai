"""A malformed producer, saved flag or failed verifier cannot attest a U1 subject."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import httpx
import psycopg
import pytest

from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.dataops import participation_acceptance as adapter
from nima.dataops.participation_acceptance import ParticipationAcceptanceError
from nima.identity.artifacts import encode
from tests.participation_acceptance_samples import observation, producer
from tests.test_citation_acceptance import subject


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Failure handling attempted a source request")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


@pytest.mark.parametrize(
    "path,value",
    [
        ("version", "future"),
        ("source", "other"),
        ("request", {}),
        ("request_sha256", "f" * 64),
        ("snapshot_sha256", "f" * 64),
        ("metric.definition_sha256", "f" * 64),
        ("metric.result", {}),
        ("metric.definition.source", "other"),
        ("metric.definition.status", "unknown"),
        ("metric.definition.tax_id", None),
        ("metric.definition.country_aliases", "GR"),
        ("metric.definition.country_aliases", [42]),
        ("coverage.observation_count", True),
        ("coverage.pages", None),
        ("coverage.raw_object_count", 1.0),
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
    body = json.loads(fresh.body)
    target = body
    parts = path.split(".")
    for name in parts[:-1]:
        target = target[name]
    target[parts[-1]] = value
    fresh = replace(fresh, body=encode(body))
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    with pytest.raises(ParticipationAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_participation_acceptance(
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
    ],
)
def test_snapshot_metadata_cannot_disagree(
    area: str, key: str, value: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer((observation(),))
    data = json.loads(fresh.snapshot.document_json)
    row = (
        data
        if area == "root"
        else data[{"run": "runs", "page": "pages", "record": "records"}[area]][0]
    )
    row[key] = value
    fresh = replace(fresh, snapshot=replace(fresh.snapshot, document_json=encode(data).decode()))
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    with pytest.raises(ParticipationAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_participation_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


@pytest.mark.parametrize(
    "error,expected",
    [
        (ReadoutError("analytics_input"), "acceptance_input"),
        (ReadoutError("analytics_limit"), "acceptance_limit"),
        (ReadoutError("analytics_archive"), "acceptance_evidence"),
        (ReadoutError("analytics_coverage"), "acceptance_evidence"),
        (ReadoutError("analytics_projection"), "acceptance_evidence"),
        (ReadoutError("analytics_evidence"), "acceptance_evidence"),
        (ReadoutError("analytics_role"), "acceptance_database"),
        (ReadoutError("analytics_schema"), "acceptance_database"),
        (ReadoutError("analytics_database"), "acceptance_database"),
        (ReadoutError("analytics_version"), "acceptance_contract"),
        (ReadoutError("analytics_metric"), "acceptance_contract"),
        (ReadoutError("analytics_contract"), "acceptance_contract"),
        (ReadoutError("analytics_output"), "acceptance_output"),
        (ReadoutError("PRIVATE_EXCEPTION"), "acceptance_contract"),
        (psycopg.OperationalError("PRIVATE_DSN"), "acceptance_database"),
    ],
)
def test_preparation_failures_have_closed_reasons(
    error: Exception, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer((observation(),))

    def fail(*args: object) -> Any:
        raise error

    monkeypatch.setattr(adapter, "prepare_readout", fail)
    with pytest.raises(ParticipationAcceptanceError, match=f"^{expected}$"):
        adapter.prepare_participation_acceptance(
            "fixture", request, subject(tmp_path / "reports", fresh.body)
        )


def test_saved_success_is_not_a_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, fresh = producer((observation(),))
    calls = 0

    def reconstruct(*args: object) -> Any:
        nonlocal calls
        calls += 1
        return fresh

    monkeypatch.setattr(adapter, "prepare_readout", reconstruct)
    report = subject(tmp_path / "reports", encode({"verified": True, "status": "ready"}))
    with pytest.raises(ParticipationAcceptanceError, match="^acceptance_evidence$"):
        adapter.prepare_participation_acceptance("fixture", request, report)
    assert calls == 1


def test_subject_limit_is_u1_one_mib_before_sql(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _ = producer((observation(),))
    path = subject(tmp_path / "reports", b"x" * (MAX_RESULT_BYTES + 1))

    def forbidden(*args: object) -> Any:
        pytest.fail("Oversize U1 subject reached SQL")

    monkeypatch.setattr(adapter, "prepare_readout", forbidden)
    with pytest.raises(ParticipationAcceptanceError, match="^acceptance_limit$"):
        adapter.prepare_participation_acceptance("fixture", request, path)


@pytest.mark.parametrize("body", [b"\xff", b"{}", b'{"x":1,"x":2}', b'{"x":NaN}'])
def test_producer_json_must_be_strict(
    body: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer((observation(),))
    fresh = replace(fresh, body=body)
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    with pytest.raises(ParticipationAcceptanceError, match="^acceptance_contract$"):
        adapter.prepare_participation_acceptance(
            "fixture", request, subject(tmp_path / "reports", body)
        )


@pytest.mark.parametrize(
    "case",
    [
        "snapshot_type",
        "snapshot_limit",
        "observation_ids",
        "run_state",
        "run_binding",
        "record_flags",
        "duplicate_records",
        "ambiguous_ids",
        "policy_drift",
        "policy_binding",
        "check_status",
        "check_reason",
        "limitations",
        "fresh_type",
        "fresh_limit",
    ],
)
def test_internal_boundaries_never_publish_bad_protocol(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.analytics.snapshot import MAX_INPUT_BYTES
    from nima.contracts import acceptance as policy

    request, fresh = producer((observation(),))
    original = fresh.body
    body = json.loads(fresh.body)
    document = json.loads(fresh.snapshot.document_json)
    expected = "acceptance_contract"
    if case == "snapshot_type":
        fresh = replace(fresh, snapshot=cast(Any, None))
    elif case == "snapshot_limit":
        fresh = replace(
            fresh, snapshot=replace(fresh.snapshot, document_json=" " * (MAX_INPUT_BYTES + 1))
        )
        expected = "acceptance_limit"
    elif case in {"observation_ids", "run_state", "run_binding"}:
        if case == "observation_ids":
            document["records"][0]["observation_id"] = 2
        elif case == "run_state":
            document["runs"][0]["managed"] = False
        else:
            document["runs"][0]["run_id"] = "00000000-0000-0000-0000-000000000003"
        body["coverage"]["runs"] = document["runs"]
        fresh = replace(
            fresh,
            snapshot=replace(fresh.snapshot, document_json=encode(document).decode()),
            body=encode(body),
        )
    elif case in {"record_flags", "duplicate_records", "ambiguous_ids"}:
        result = fresh.snapshot.metric
        if case == "record_flags":
            result = replace(
                result, records=(replace(result.records[0], unknown_suppliers=cast(Any, 1)),)
            )
        elif case == "duplicate_records":
            result = replace(result, records=(result.records[0], result.records[0]))
        else:
            result = replace(result, ambiguous_source_ids=("kimdis:S",))
        body["metric"]["result"] = result.payload()
        fresh = replace(fresh, body=encode(body), snapshot=replace(fresh.snapshot, metric=result))
    elif case == "policy_drift":
        monkeypatch.setattr(policy, "definition", lambda: {"version": "future"})
    elif case in {"policy_binding", "check_status", "check_reason", "limitations"}:
        original_evaluate = policy.evaluate

        def wrong(facts: policy.DatasetFacts) -> policy.Assessment:
            value = original_evaluate(facts)
            if case == "policy_binding":
                return replace(value, request_sha256="f" * 64)
            if case == "limitations":
                return replace(value, limitations=("PRIVATE_VALUE",))
            check = replace(
                value.checks[0],
                **{"status" if case == "check_status" else "reason": "PRIVATE_VALUE"},
            )
            return replace(value, checks=(check, *value.checks[1:]))

        monkeypatch.setattr(policy, "evaluate", wrong)
    elif case == "fresh_type":
        fresh = cast(Any, None)
    elif case == "fresh_limit":
        fresh = replace(fresh, body=b"x" * (MAX_RESULT_BYTES + 1))
        expected = "acceptance_limit"
    inspected = original if case in {"fresh_type", "fresh_limit"} else fresh.body
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    with pytest.raises(ParticipationAcceptanceError, match=f"^{expected}$"):
        adapter.prepare_participation_acceptance(
            "fixture", request, subject(tmp_path / "reports", inspected)
        )


@pytest.mark.parametrize("case", ["dsn", "report", "request", "ordering"])
def test_configuration_is_validated_before_evidence(case: str, tmp_path: Path) -> None:
    from uuid import UUID

    from nima.graph.pilot_archive import ArchiveBinding

    request, _ = producer((observation(),))
    report = tmp_path / ("a" * 64 + ".json")
    if case == "request":
        request = replace(request, supplier_country="DE")
    elif case == "ordering":
        request = replace(
            request,
            run_ids=(UUID(int=2), UUID(int=1)),
            archive_bindings=(
                ArchiveBinding("kimdis", UUID(int=2), Path("/unused/2")),
                ArchiveBinding("kimdis", UUID(int=1), Path("/unused/1")),
            ),
        )
    with pytest.raises(ParticipationAcceptanceError, match="^acceptance_input$"):
        adapter.prepare_participation_acceptance(
            " " if case == "dsn" else "fixture",
            request,
            Path("relative") if case == "report" else report,
        )


@pytest.mark.parametrize(
    "case",
    ["request_relative", "output_relative", "request_missing", "request_limit", "conflict", "io"],
)
def test_export_refusals_do_not_fake_success(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from nima.analytics.request import MAX_REQUEST_BYTES
    from tests.test_market_analytics import request_file

    request, fresh = producer((observation(),))
    selection = request_file(request, tmp_path / "request.json")
    report = subject(tmp_path / "reports", fresh.body)
    output = tmp_path / "output"
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
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
        prepared = adapter.prepare_participation_acceptance("fixture", request, report)
        output.mkdir(mode=0o700)
        path = output / (hashlib.sha256(prepared.body).hexdigest() + ".json")
        path.write_bytes(b"conflict")
        path.chmod(0o600)
        expected = "acceptance_output"
    else:

        def fail(*args: object) -> Any:
            raise OSError("PRIVATE_VALUE")

        monkeypatch.setattr(adapter, "publish", fail)
        expected = "acceptance_output"
    with pytest.raises(ParticipationAcceptanceError, match=f"^{expected}$"):
        adapter.export_participation_acceptance("fixture", selection, report, output)


def test_exact_sidecar_bound_and_shared_quarantine_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, fresh = producer((observation(),))
    body = json.loads(fresh.body)
    document = json.loads(fresh.snapshot.document_json)
    document["runs"][0]["quarantine_count"] = 1
    document["pages"][0]["record_count"] = 2
    body["coverage"]["runs"] = document["runs"]
    body["coverage"]["pages"][0]["record_count"] = 2
    fresh = replace(
        fresh,
        body=encode(body),
        snapshot=replace(fresh.snapshot, document_json=encode(document).decode()),
    )
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    report = subject(tmp_path / "reports", fresh.body)
    prepared = adapter.prepare_participation_acceptance("fixture", request, report)
    # Controlled verified-producer frame, not a claim that an actual U1 partial capture passes.
    assert prepared.assessment.status == "blocked"
    assert {c.name: c.value for c in prepared.assessment.counts}["quarantined"] == 1
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(prepared.body))
    assert (
        adapter.prepare_participation_acceptance("fixture", request, report).body == prepared.body
    )
    monkeypatch.setattr(adapter, "MAX_ACCEPTANCE_BYTES", len(prepared.body) - 1)
    with pytest.raises(ParticipationAcceptanceError, match="^acceptance_limit$"):
        adapter.prepare_participation_acceptance("fixture", request, report)


def test_unadmitted_definition_is_explicit_not_assessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.semantics.participation import definition

    meta = definition()
    meta["status"] = "reviewed"
    request, fresh = producer((observation(),), definition=meta)
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    result = adapter.prepare_participation_acceptance(
        "fixture", request, subject(tmp_path / "reports", fresh.body)
    )
    assert result.assessment.status == "not_assessed"


@pytest.mark.parametrize("decision", ["blocked", "not_assessed"])
def test_negative_fitness_is_published_and_cli_exits_three(
    decision: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nima.dataops import cli
    from nima.semantics.participation import definition
    from tests.test_market_analytics import request_file

    meta = definition()
    if decision == "not_assessed":
        meta["status"] = "reviewed"
    request, fresh = producer((observation(),), definition=meta)
    if decision == "blocked":
        document = json.loads(fresh.snapshot.document_json)
        body = json.loads(fresh.body)
        document["runs"][0]["quarantine_count"] = 1
        document["pages"][0]["record_count"] = 2
        body["coverage"]["runs"] = document["runs"]
        body["coverage"]["pages"][0]["record_count"] = 2
        fresh = replace(
            fresh,
            body=encode(body),
            snapshot=replace(fresh.snapshot, document_json=encode(document).decode()),
        )
    monkeypatch.setattr(adapter, "prepare_readout", lambda *_: fresh)
    monkeypatch.setenv("NIMA_DATABASE_URL", "fixture")
    selection = request_file(request, tmp_path / "request.json")
    report = subject(tmp_path / "reports", fresh.body)
    output = tmp_path / "output"
    exported = adapter.export_participation_acceptance("fixture", selection, report, output)
    assert exported.decision == decision
    artifact = output / (exported.artifact_sha256 + ".json")
    assert json.loads(artifact.read_bytes())["assessment"]["status"] == decision
    assert (
        cli.run(
            [
                "assess-participation",
                "--request",
                str(selection),
                "--report",
                str(report),
                "--output-dir",
                str(output),
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().out)["decision"] == decision
