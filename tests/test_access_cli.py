"""Actual command routes: exit codes, private report, redaction and print-only grants."""

import json
import stat
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from nima.__main__ import main
from nima.dataops import access_audit as aa
from nima.dataops import access_cli as cli
from nima.dataops import access_contract as ac
from nima.dataops.health import HealthError
from nima.identity import AssessmentError
from nima.storage.postgres import migrate
from tests.test_access_audit import clean
from tests.test_access_audit_store import apply_printed_grants, new_role

SECRET = "pa55-secret-marker"
URL = f"postgresql://svc:{SECRET}@127.0.0.1:1/db"


def audit_args(output: Path, role: str = "svc", profile: str = "analytics-reader") -> list[str]:
    return [
        "dataops",
        "access-audit",
        "--role",
        role,
        "--profile",
        profile,
        "--output-dir",
        str(output),
    ]


def events(err: str) -> list[dict[str, str]]:
    return [json.loads(line) for line in err.splitlines() if line.startswith("{")]


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", URL)


def stub(monkeypatch: pytest.MonkeyPatch, snapshot: aa.AccessSnapshot | BaseException) -> None:
    def read(dsn: str, role: str) -> aa.AccessSnapshot:
        assert dsn == URL
        if isinstance(snapshot, BaseException):
            raise snapshot
        return snapshot

    monkeypatch.setattr(cli, "read_snapshot", read)


def artifacts(output: Path) -> list[Path]:
    return sorted(output.glob("*.json")) if output.exists() else []


def test_clean_role_publishes_a_private_passing_report(
    environment: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub(monkeypatch, clean("analytics-reader"))
    assert main(audit_args(tmp_path / "out")) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == {"status": "checks_passed", "attention_count": 0}
    (report,) = artifacts(tmp_path / "out")
    assert stat.S_IMODE(report.stat().st_mode) == 0o600
    body = json.loads(report.read_text())
    assert body["version"] == "access-audit-v1" and body["status"] == "checks_passed"
    assert body["contract_version"] == ac.CONTRACT_VERSION and body["profile"] == "analytics-reader"
    assert body["role"] == "svc" and body["reasons"] == [] and len(body["limitations"]) == 15
    assert [e["event"] for e in events(err)] == ["started", "completed"]
    assert {e["component"] for e in events(err)} == {"dataops.access_audit"}


def test_excess_privilege_publishes_attention_and_exits_three(
    environment: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snap = clean("analytics-reader")
    snap = replace(
        snap,
        tables=tuple(
            replace(t, privileges=t.privileges | {ac.Priv.DELETE})
            if t.name == "nima.observations"
            else t
            for t in snap.tables
        ),
    )
    stub(monkeypatch, snap)
    assert main(audit_args(tmp_path / "out")) == 3
    assert json.loads(capsys.readouterr().out) == {"status": "attention", "attention_count": 1}
    (report,) = artifacts(tmp_path / "out")
    assert json.loads(report.read_text())["reasons"] == [
        {"code": "evidence_rewrite_privilege", "subject": "nima.observations", "detail": "DELETE"}
    ]


def test_worst_case_report_fits_the_bound_and_is_published(
    environment: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snap = clean("analytics-reader")
    everything = frozenset(ac.Priv)
    snap = replace(
        snap,
        role=replace(
            snap.role,
            superuser=True,
            createrole=True,
            createdb=True,
            replication=True,
            bypassrls=True,
            owns_objects=True,
            owner_member=True,
            create_database=True,
            create_schemas=ac.SCHEMAS,
        ),
        schema_usage=ac.SCHEMAS,
        tables=tuple(
            replace(t, privileges=everything, column_updates=frozenset({"a_column"}))
            for t in snap.tables
        ),
        sequences=tuple(
            replace(s, privileges=frozenset({"USAGE", "SELECT", "UPDATE"})) for s in snap.sequences
        ),
    )
    stub(monkeypatch, snap)
    assert main(audit_args(tmp_path / "out")) == 3
    (report,) = artifacts(tmp_path / "out")
    assert 0 < report.stat().st_size <= 32 * 1024


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--role", "svc", "--profile", "analytics-reader"],
        ["--output-dir", "relative/out"],
        ["--output-dir", "/abs/../out"],
        ["--bogus"],
    ],
)
def test_bad_arguments_exit_two_without_connecting(
    environment: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
) -> None:
    stub(monkeypatch, AssertionError("must not connect"))
    argv = ["dataops", "access-audit", *extra] if extra else ["dataops", "access-audit"]
    assert main(argv) == 2
    out, _ = capsys.readouterr()
    assert json.loads(out) == {"status": "failed", "failure": "access_audit_configuration"}


def test_unknown_profile_is_a_configuration_failure_not_a_pass(
    environment: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stub(monkeypatch, clean("analytics-reader"))
    assert main(audit_args(tmp_path / "out", profile="owner")) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "access_audit_configuration"
    assert artifacts(tmp_path / "out") == []


@pytest.mark.parametrize(
    ("failure", "code", "reason"),
    [
        (HealthError("access_audit_unavailable"), 1, "access_audit_unavailable"),
        (HealthError("access_audit_limit"), 1, "access_audit_limit"),
        (HealthError("access_audit_configuration"), 2, "access_audit_configuration"),
        (aa.AuditError("duplicate table facts"), 1, "access_audit_evidence"),
        (KeyboardInterrupt(), 130, "access_audit_interrupted"),
    ],
)
def test_failures_use_fixed_codes_and_never_publish_or_leak(
    environment: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
    code: int,
    reason: str,
) -> None:
    stub(monkeypatch, failure)
    assert main(audit_args(tmp_path / "out")) == code
    out, err = capsys.readouterr()
    assert json.loads(out) == {"status": "failed", "failure": reason}
    assert SECRET not in out + err and artifacts(tmp_path / "out") == []
    assert [e["event"] for e in events(err)] == ["started", "failed"]
    assert events(err)[-1]["reason"] == reason


@pytest.mark.parametrize("error", [OSError("/private/path"), AssessmentError("assessment_limit")])
def test_output_failure_is_fixed_and_exposes_nothing(
    environment: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    stub(monkeypatch, clean("analytics-reader"))

    def refuse(directory: Path, body: bytes) -> str:
        raise error

    monkeypatch.setattr(cli, "publish", refuse)
    assert main(audit_args(tmp_path / "out")) == 1
    out, err = capsys.readouterr()
    assert json.loads(out) == {"status": "failed", "failure": "access_audit_output"}
    assert "/private/path" not in out + err


def test_missing_database_url_is_refused_by_the_adapter_not_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert main(audit_args(tmp_path / "out")) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "access_audit_configuration"


def test_grants_command_prints_only_and_never_touches_a_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def never(*_a: object, **_k: object) -> None:
        raise AssertionError("access-grants must not connect")

    monkeypatch.setattr(psycopg, "connect", never)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    argv = ["dataops", "access-grants", "--profile", "validation-writer", "--role", "svc_role"]
    assert main(argv) == 0
    out, err = capsys.readouterr()
    assert out.startswith("-- access-contract-v1") and 'TO "svc_role";' in out
    assert [e["event"] for e in events(err)] == ["started", "completed"]


@pytest.mark.parametrize(
    "argv",
    [
        ["--profile", "owner", "--role", "svc_role"],
        ["--profile", "analytics-reader", "--role", 'x"; DROP ROLE y; --'],
        ["--profile", "analytics-reader"],
        ["--role", "svc_role"],
        ["--profile", "analytics-reader", "--role", "svc_role", "--extra"],
    ],
)
def test_grants_command_refuses_bad_input_with_no_sql_on_stdout(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    assert main(["dataops", "access-grants", *argv]) == 2
    out, err = capsys.readouterr()
    assert out == "" and "DROP" not in err
    assert events(err)[-1] == {
        "component": "dataops.access_grants",
        "event": "failed",
        "reason": "access_grants_configuration",
    }


def test_router_help_lists_both_new_operations(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dataops", "--help"]) == 0
    out = capsys.readouterr().out
    assert "access-audit" in out and "access-grants" in out


def test_actual_commands_audit_a_real_role_end_to_end(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    with psycopg.connect(pg_dsn, autocommit=True) as c:
        role = new_role(c)
        apply_printed_grants(c, "analytics-reader", role)
        assert main(audit_args(tmp_path / "ok", role)) == 0
        c.execute(sql.SQL("GRANT TRUNCATE ON nima.raw_objects TO {}").format(sql.Identifier(role)))
        assert main(audit_args(tmp_path / "bad", role)) == 3
    out = capsys.readouterr().out.splitlines()
    assert json.loads(out[-1]) == {"status": "attention", "attention_count": 1}
    (report,) = artifacts(tmp_path / "bad")
    reasons = json.loads(report.read_text())["reasons"]
    assert reasons == [
        {"code": "evidence_rewrite_privilege", "subject": "nima.raw_objects", "detail": "TRUNCATE"}
    ]
    assert pg_dsn not in report.read_text()
