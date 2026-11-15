"""Operator review/resolution commands expose fixed summaries and redact private values."""

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Never
from uuid import UUID

import psycopg
import pytest

from nima.__main__ import main
from nima.identity.artifacts import encode
from nima.identity.review_inputs import decode_report
from nima.identity.review_types import ReviewError
from nima.storage.postgres import MigrationError
from tests.test_identity_review_accept import ledger, request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import private_file, report_body
from tests.test_identity_review_reversal import revoke
from tests.test_identity_review_support import source_snapshot


def arguments(operation: str, path: Path, output: Path) -> list[str]:
    if operation == "review":
        return ["identities", "review", str(UUID(int=99)), "--request-file", str(path)]
    return ["identities", "resolution", "--report-file", str(path), "--output-dir", str(output)]


@pytest.mark.parametrize("operation", ["review", "resolution"])
def test_operator_help_exposes_only_explicit_files_and_bounds(
    operation: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["identities", operation, "--help"])
    assert stopped.value.code == 0
    output = capsys.readouterr()
    flags = (
        ("--request-file", "--report-file")
        if operation == "review"
        else ("--report-file", "--output-dir", "--max-events")
    )
    assert all(flag in output.out for flag in flags) and not output.err


@pytest.mark.parametrize(
    "fault",
    [
        "uuid",
        "missing_request",
        "unknown",
        "integer",
        "missing_output",
        "misplaced",
        "unknown_route",
    ],
)
def test_malformed_private_options_never_echo_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    args = arguments("review", tmp_path / "private-sentinel", tmp_path)
    if fault == "uuid":
        args[2] = "private-sentinel"
    elif fault == "missing_request":
        args = args[:3]
    elif fault == "unknown":
        args += ["--private-sentinel"]
    elif fault == "integer":
        args = arguments("resolution", tmp_path / "private-sentinel", tmp_path) + [
            "--max-events",
            "private-sentinel",
        ]
    elif fault == "missing_output":
        args = ["identities", "resolution", "--report-file", "private-sentinel"]
    elif fault == "misplaced":
        args = ["identities", "--private-sentinel", "review"]
    else:
        args = ["identities", "private-sentinel"]
    assert main(args) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": "configuration"}
    assert not output.err and "private-sentinel" not in output.out


@pytest.mark.parametrize("operation", ["review", "resolution"])
@pytest.mark.parametrize(
    "error,code,reason",
    [
        (ReviewError("review_input"), 2, "review_input"),
        (ReviewError("review_input_io"), 1, "review_input_io"),
        (ReviewError("review_conflict"), 1, "review_conflict"),
        (ReviewError("review_permission"), 1, "review_permission"),
        (ReviewError("review_evidence"), 1, "review_evidence"),
        (ReviewError("review_limit"), 1, "review_limit"),
        (MigrationError("private-sentinel"), 1, "review_schema"),
        (psycopg.OperationalError("private-sentinel"), 1, "review_database"),
        (OSError("private-sentinel"), 1, "io"),
        (ValueError("private-sentinel"), 2, "configuration"),
        (KeyboardInterrupt("private-sentinel"), 130, "interrupted"),
    ],
)
def test_operator_failure_mapping_is_fixed_and_value_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    error: BaseException,
    code: int,
    reason: str,
) -> None:
    raw = report_body()
    parsed = decode_report(raw)
    chosen = request(parsed)
    file = private_file(
        tmp_path,
        "request.json" if operation == "review" else "report.json",
        encode(chosen.payload()) if operation == "review" else raw,
    )
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def fail(*args: object, **kwargs: object) -> Never:
        raise error

    target = "record_review" if operation == "review" else "export_resolution"
    monkeypatch.setattr("nima.__main__." + target, fail, raising=False)
    assert main(arguments(operation, file, tmp_path / "private-sentinel")) == code
    output = capsys.readouterr()
    expected = (
        {"review": "review_input_io", "resolution": "review_output"}[operation]
        if reason == "io"
        else reason
    )
    assert json.loads(output.out) == {"status": "failed", "failure": expected}
    assert not output.err and "private-sentinel" not in output.out


@pytest.mark.parametrize("fault", ["zero", "over", "database", "request_body"])
def test_invalid_operator_configuration_does_not_reach_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    raw = report_body()
    path = private_file(tmp_path, "report.json", raw)
    args = arguments("resolution", path, tmp_path / "absent")
    if fault in {"zero", "over"}:
        args += ["--max-events", "0" if fault == "zero" else "10001"]
    elif fault == "database":
        monkeypatch.delenv("NIMA_DATABASE_URL")
    else:
        path = private_file(tmp_path, "request.json", b'{"private-sentinel":true}')
        args = arguments("review", path, tmp_path)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid configuration reached SQL")

    monkeypatch.setattr("nima.identity.review_snapshot.check_schema", forbidden)
    monkeypatch.setattr("nima.identity.review_store.check_schema", forbidden)
    assert main(args) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["failure"] in {"configuration", "review_input"}
    assert (
        not output.err
        and "private-sentinel" not in output.out
        and not (tmp_path / "absent").exists()
    )


@pytest.mark.parametrize("operation", ["accept", "reject"])
def test_real_operator_workflow_and_old_receipt_replay_are_offline_and_private(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
) -> None:
    from nima.identity.registry_report import build_report

    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    if operation == "reject":
        chosen = replace(chosen, operation="reject", entity_id=None)
    req = private_file(tmp_path, "request.json", encode(chosen.payload()))
    comparison = private_file(tmp_path, "report.json", encode(build_report(parsed.cohort)))
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    original = os.environ.get

    def get(key: str, default: str | None = None) -> str | None:
        assert key != "NIMA_GEMI_API_KEY"
        return original(key, default)

    monkeypatch.setattr(os.environ, "get", get)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Operator review must not create an HTTP client")

    monkeypatch.setattr("httpx.Client", forbidden)
    before = source_snapshot(pg_dsn)
    args = arguments("review", req, tmp_path)
    args[2] = str(chosen.request_id)
    args += ["--report-file", str(comparison)]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["event_id"] == str(chosen.request_id) and not first["replayed"]
    assert main(args) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["replayed"] and again["subject_revision"] == 1
    output = tmp_path / "exports"
    assert main(arguments("resolution", comparison, output)) == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["reviewed_accepted_links"] == int(operation == "accept")
    assert summary["automatic_identity_links"] == 0
    for value in (
        pg_dsn,
        str(req),
        str(comparison),
        str(output),
        chosen.rationale,
        "001234567",
        "Άλφα",
    ):
        assert value not in captured.out
    assert not captured.err
    artifact = next(output.glob("*.json"))
    old = artifact.read_bytes()
    undone = revoke(chosen, 1)
    path = private_file(tmp_path, "revoke.json", encode(undone.payload()))
    comparison.unlink()
    args = arguments("review", path, tmp_path)
    args[2] = str(undone.request_id)
    assert main([*args, "--report-file", str(comparison)]) == 0
    assert json.loads(capsys.readouterr().out)["operation"] == "revoke"
    args = arguments("review", req, tmp_path)
    args[2] = str(chosen.request_id)
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["replayed"]
    assert ledger(pg_dsn) == (1, int(operation == "accept"), 2) and artifact.read_bytes() == old
    assert source_snapshot(pg_dsn) == before
