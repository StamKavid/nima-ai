"""Graph operator parsing, private inputs and real SQL exports use fixed safe summaries."""

import hashlib
import json
import os
from pathlib import Path
from typing import Never

import psycopg
import pytest

from nima.__main__ import main
from nima.graph import GraphError, commands
from nima.identity import review_store
from nima.identity.artifacts import encode
from nima.identity.registry_report import build_report
from nima.identity.review_types import ReviewError
from nima.storage.postgres import MigrationError
from tests.test_graph_support import database_snapshot
from tests.test_identity_review_accept import request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import private_file, report_body
from tests.test_identity_review_reversal import revoke


def arguments(report: Path, output: Path) -> list[str]:
    return ["graph", "snapshot", "--report-file", str(report), "--output-dir", str(output)]


@pytest.mark.parametrize("route", [[], ["graph"], ["graph", "snapshot"]])
def test_graph_is_discoverable_and_help_has_only_offline_options(
    route: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main([*route, "--help"])
    assert stopped.value.code == 0
    output = capsys.readouterr()
    assert not output.err
    if not route:
        assert "graph" in output.out
    elif len(route) == 1:
        assert "snapshot" in output.out
    else:
        assert all(
            flag in output.out
            for flag in ("--report-file", "--output-dir", "--entity-id", "--max-events")
        )
        assert "--database-url" not in output.out and "--api-key" not in output.out


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        ["private-sentinel"],
        ["snapshot"],
        ["--private-sentinel", "snapshot"],
        ["snapshot", "--entity-id", "private-sentinel"],
        ["snapshot", "--max-events", "private-sentinel"],
        ["snapshot", "--database-url", "private-sentinel"],
        ["--report-file", "private-sentinel", "snapshot"],
        ["snapshot", "--report-file", "private-sentinel"],
        ["snapshot", "--report", "private-sentinel", "--output-dir", "private-sentinel"],
        [
            "snapshot",
            "--report-file",
            "private-sentinel",
            "--output-dir",
            "private-sentinel",
            "private-sentinel",
        ],
    ],
)
def test_graph_parser_failures_redact_unknown_misplaced_and_invalid_values(
    tokens: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Bad graph parsing must fail before private file/SQL access")

    monkeypatch.setattr(commands, "read_report", forbidden)
    monkeypatch.setattr(commands, "export_graph", forbidden)
    assert main(["graph", *tokens]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "failure": "graph_configuration"}
    assert not captured.err and "private-sentinel" not in captured.out


@pytest.mark.parametrize("fault", ["zero", "negative", "over", "database"])
def test_configuration_fails_before_private_file_or_sql_access(
    fault: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    args = arguments(tmp_path / "private-sentinel", tmp_path / "absent")
    if fault == "database":
        monkeypatch.delenv("NIMA_DATABASE_URL")
    else:
        args += ["--max-events", {"zero": "0", "negative": "-1", "over": "10001"}[fault]]

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid configuration must precede private I/O")

    monkeypatch.setattr(commands, "read_report", forbidden)
    assert main(args) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "failure": "graph_configuration"}
    assert not captured.err and not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "fault,code,reason",
    [
        ("missing", 1, "graph_input_io"),
        ("permissions", 1, "graph_input_io"),
        ("symlink", 1, "graph_input_io"),
        ("shape", 2, "graph_input"),
        ("duplicate", 2, "graph_input"),
    ],
)
def test_private_report_failures_are_fixed_and_precede_sql(
    fault: str,
    code: int,
    reason: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = private_file(tmp_path, "private-sentinel.json", report_body())
    if fault == "missing":
        path.unlink()
    elif fault == "permissions":
        path.chmod(0o644)
    elif fault == "symlink":
        link = tmp_path / "private-link-sentinel"
        link.symlink_to(path)
        path = link
    else:
        path.write_bytes(
            b'{"private-sentinel":true}'
            if fault == "shape"
            else b'{"private-sentinel":1,"private-sentinel":2}'
        )
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid private report must not reach SQL")

    monkeypatch.setattr(commands, "export_graph", forbidden)
    assert main(arguments(path, tmp_path / "absent")) == code
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "failure": reason}
    assert not captured.err and "private-sentinel" not in captured.out
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "error,code,reason",
    [
        (GraphError("graph_evidence"), 1, "graph_evidence"),
        (GraphError("graph_state"), 1, "graph_state"),
        (GraphError("graph_limit"), 1, "graph_limit"),
        (GraphError("graph_permission"), 1, "graph_permission"),
        (GraphError("graph_output"), 1, "graph_output"),
        (GraphError("graph_input"), 2, "graph_input"),
        (GraphError("graph_configuration"), 2, "graph_configuration"),
        (GraphError("graph_interrupted"), 130, "graph_interrupted"),
        (ReviewError("review_input"), 2, "graph_input"),
        (ReviewError("review_input_io"), 1, "graph_input_io"),
        (ReviewError("review_limit"), 1, "graph_limit"),
        (ReviewError("review_evidence"), 1, "graph_evidence"),
        (MigrationError("private-sentinel"), 1, "graph_schema"),
        (psycopg.OperationalError("private-sentinel"), 1, "graph_database"),
        (OSError("private-sentinel"), 1, "graph_output"),
        (ValueError("private-sentinel"), 2, "graph_configuration"),
        (KeyboardInterrupt("private-sentinel"), 130, "graph_interrupted"),
    ],
)
def test_runtime_failures_have_fixed_graph_codes_without_private_details(
    error: BaseException,
    code: int,
    reason: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = private_file(tmp_path, "report.json", report_body())
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def fail(*args: object, **kwargs: object) -> Never:
        raise error

    monkeypatch.setattr(commands, "export_graph", fail)
    assert main(arguments(path, tmp_path / "private-sentinel")) == code
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "failure": reason}
    assert not captured.err and "private-sentinel" not in captured.out


@pytest.mark.parametrize("focused", [False, True])
def test_real_graph_cli_is_offline_private_read_only_and_keeps_old_snapshots(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    focused: bool,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    path = private_file(tmp_path, "report.json", encode(build_report(parsed.cohort)))
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    original = os.environ.get

    def get(key: str, default: str | None = None) -> str | None:
        assert key != "NIMA_GEMI_API_KEY"
        return original(key, default)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Offline graph CLI must not create an HTTP client")

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr("httpx.Client", forbidden)
    output = tmp_path / "exports"
    args = arguments(path, output)
    if focused:
        args += ["--entity-id", str(chosen.entity_id)]
    before = database_snapshot(pg_dsn)
    assert main(args) == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    artifact = output / (summary["graph_sha256"] + ".json")
    old = artifact.read_bytes(), artifact.stat().st_mtime_ns
    data = json.loads(old[0])
    assert hashlib.sha256(old[0]).hexdigest() == summary["graph_sha256"]
    assert len([e for e in data["edges"] if e["kind"] == "reviewed_as"]) == 1
    assert data["focus"]["state"] == ("active_links" if focused else "omitted")
    assert summary["automatic_identity_links"] == 0 and summary["reviewed_accepted_links"] == 1
    assert not captured.err
    for value in (pg_dsn, str(path), str(output), chosen.rationale, "001234567", "Άλφα"):
        assert value not in captured.out
    assert main(args) == 0 and json.loads(capsys.readouterr().out) == summary
    assert old == (artifact.read_bytes(), artifact.stat().st_mtime_ns)
    assert database_snapshot(pg_dsn) == before
    review_store.review(pg_dsn, revoke(chosen, 1))
    after_writer = database_snapshot(pg_dsn)
    assert main(args) == 0
    changed = json.loads(capsys.readouterr().out)
    assert (
        changed["graph_sha256"] != summary["graph_sha256"]
        and changed["reviewed_accepted_links"] == 0
    )
    assert old == (artifact.read_bytes(), artifact.stat().st_mtime_ns)
    assert database_snapshot(pg_dsn) == after_writer
