"""Fresh bindings, private inputs and closed operational failures are mandatory."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from nima.analytics.result import MAX_RESULT_BYTES
from nima.dataops.acceptance_files import AcceptanceError
from nima.dataops.buyer_acceptance import MAX_ACCEPTANCE_BYTES
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.insights import buyer_participation as insight
from tests.buyer_insight_samples import frame
from tests.test_citation_acceptance import subject


@pytest.mark.parametrize(
    "kind", ["input", "limit", "evidence", "database", "contract", "output", "interrupted"]
)
def test_consumer_operation_failures_are_not_business_refusals(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, _ = frame(tmp_path, monkeypatch)
    path = subject(tmp_path / "parent", parent)

    def fail(*args: object) -> Any:
        raise AcceptanceError(f"acceptance_{kind}")

    monkeypatch.setattr(insight, "prepare_buyer_acceptance", fail)
    with pytest.raises(insight.InsightError, match=f"^insight_{kind}$"):
        insight.prepare_buyer_insight("fixture", request, path)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("kind", ["wrong_type", "changed_subject"])
def test_intervening_parent_or_invalid_fresh_result_fails(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, fresh = frame(tmp_path, monkeypatch)
    value = None if kind == "wrong_type" else replace(fresh, subject_sha256="f" * 64)
    monkeypatch.setattr(insight, "prepare_buyer_acceptance", lambda *_: value)
    with pytest.raises(insight.InsightError, match="^insight_(contract|evidence)$"):
        insight.prepare_buyer_insight("fixture", request, subject(tmp_path / "parent", parent))


@pytest.mark.parametrize(
    "area,path,value",
    [
        ("parent", "version", "future"),
        ("parent", "source", "other"),
        ("sidecar", "version", "future"),
        ("sidecar", "subject.version", "future"),
        ("sidecar", "subject.request_sha256", "f" * 64),
        ("parent", "request", {}),
        ("parent", "request_sha256", "f" * 64),
        ("sidecar", "subject.metric.status", "certified"),
        ("parent", "metric.definition_sha256", "f" * 64),
        ("sidecar", "policy.definition.uses.U3.definition_sha256", "f" * 64),
        ("sidecar", "policy.definition.uses.U3.metric_id", "other"),
        ("sidecar", "policy.definition.uses.U3.sql_sha256", "f" * 64),
        ("sidecar", "policy.definition_sha256", "f" * 64),
        ("sidecar", "policy.definition.required_checks.U3", []),
        ("sidecar", "policy.definition.id", "other"),
        ("sidecar", "policy.definition.version", "future"),
        ("sidecar", "assessment.status", "ready"),
    ],
)
def test_hash_request_metric_and_policy_disagreements_are_operational_errors(
    area: str, path: str, value: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, fresh = frame(tmp_path, monkeypatch, unknown=True)
    report, sidecar = json.loads(parent), json.loads(fresh.body)
    target = report if area == "parent" else sidecar
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    parent = encode(report)
    digest = hashlib.sha256(parent).hexdigest()
    sidecar["subject"]["artifact_sha256"] = digest
    fresh = replace(fresh, subject_sha256=digest, body=encode(sidecar))
    with pytest.raises(insight.InsightError, match="^insight_contract$"):
        insight._compose(request, parent, fresh)


@pytest.mark.parametrize(
    "kind", ["json", "duplicate", "nan", "shape", "noncanonical", "parent_limit", "sidecar_limit"]
)
def test_malformed_or_excessive_frames_fail_closed(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, fresh = frame(tmp_path, monkeypatch)
    if kind == "json":
        parent = b"\xff"
    elif kind == "duplicate":
        parent = b'{"version":1,"version":2}'
    elif kind == "nan":
        parent = b'{"value":NaN}'
    elif kind == "shape":
        parent = b"[]"
    elif kind == "noncanonical":
        fresh = replace(fresh, body=fresh.body + b" ")
    elif kind == "parent_limit":
        parent = b"x" * (MAX_RESULT_BYTES + 1)
    else:
        fresh = replace(fresh, body=b"x" * (MAX_ACCEPTANCE_BYTES + 1))
    with pytest.raises(insight.InsightError, match="^insight_(contract|limit)$"):
        insight._compose(request, parent, fresh)


@pytest.mark.parametrize(
    "dsn,request_value,path",
    [
        (None, "valid", "/private/a.json"),
        ("", "valid", "/private/a.json"),
        ("fixture", None, "/private/a.json"),
        ("fixture", "valid", "relative.json"),
        ("fixture", "valid", "/private/a.txt"),
    ],
)
def test_invalid_preparation_arguments_fail_before_verification(
    dsn: Any, request_value: Any, path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _, _ = frame(tmp_path, monkeypatch)
    with pytest.raises(insight.InsightError, match="^insight_input$"):
        insight.prepare_buyer_insight(
            dsn, request if request_value == "valid" else request_value, Path(path)
        )


@pytest.mark.parametrize(
    "kind",
    [
        "request_path",
        "output_path",
        "invalid_request",
        "request_limit",
        "publisher_os",
        "publisher_contract",
        "interrupted",
    ],
)
def test_export_input_and_publication_failures_never_emit_success(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.buyer_acceptance_samples import request_file

    request, parent, _ = frame(tmp_path, monkeypatch)
    selection = request_file(request, tmp_path / "request.json")
    report = subject(tmp_path / "parent", parent)
    output = tmp_path / "output"
    expected = "input"
    if kind == "request_path":
        selection = Path("relative.json")
    elif kind == "output_path":
        output = Path("relative")
    elif kind == "invalid_request":
        selection.write_bytes(b"{}")
    elif kind == "request_limit":
        selection.write_bytes(b"x" * (16 * 1024 + 1))
        expected = "limit"
    else:
        expected = "output"

        def fail(*args: object) -> Any:
            if kind == "publisher_os":
                raise OSError("private path must stay private")
            if kind == "publisher_contract":
                raise AssessmentError("output_path")
            raise KeyboardInterrupt

        monkeypatch.setattr(insight, "publish", fail)
    if kind == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            insight.export_buyer_insight("fixture", selection, report, output)
    else:
        with pytest.raises(insight.InsightError, match=f"^insight_{expected}$"):
            insight.export_buyer_insight("fixture", selection, report, output)
    assert not (tmp_path / "output").exists()


def test_output_overflow_does_not_truncate_or_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, parent, fresh = frame(tmp_path, monkeypatch)
    # Input fits, but embedding the full assessment and limits exceeds the artifact cap.
    report = json.loads(parent)
    report["interpretation_limits"] = ["x" * (MAX_RESULT_BYTES - len(parent) - 30)]
    parent = encode(report)
    digest = hashlib.sha256(parent).hexdigest()
    sidecar = json.loads(fresh.body)
    sidecar["subject"]["artifact_sha256"] = digest
    fresh = replace(fresh, subject_sha256=digest, body=encode(sidecar))
    with pytest.raises(insight.InsightError, match="^insight_limit$"):
        insight._compose(request, parent, fresh)


def test_unknown_error_reason_is_sanitized() -> None:
    assert str(insight.InsightError("private/source/value")) == "insight_contract"
