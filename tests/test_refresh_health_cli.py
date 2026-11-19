"""Actual command publication stays private and never executes source/control requests."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from nima.__main__ import main
from tests.test_graph_support import database_snapshot
from tests.test_refresh_health_store import reader
from tests.test_refresh_recovery_control import child


def arguments(policy: UUID, output: Path) -> list[str]:
    return [
        "dataops",
        "refresh-health",
        "--policy-id",
        str(policy),
        "--max-tick-age-hours",
        "24",
        "--max-observation-age-hours",
        "24",
        "--output-dir",
        str(output),
    ]


def test_actual_readonly_command_publishes_private_attention_artifact(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, policy, request = child(pg_dsn, tmp_path / "raw")
    with psycopg.connect(pg_dsn) as c:
        c.execute("UPDATE nima.workflow_requests SET failure='private-failure-marker'")
    before = database_snapshot(pg_dsn)

    def reject(*args: object, **kwargs: object) -> None:
        pytest.fail("Health must not contact any HTTP endpoint")

    monkeypatch.setattr(httpx.Client, "request", reject)
    with reader(pg_dsn) as dsn:
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(arguments(policy, tmp_path / "reports")) == 3
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["status"] == "attention" and summary["attention_count"] > 0
    assert [json.loads(line)["event"] for line in captured.err.splitlines()] == [
        "started",
        "completed",
    ]
    artifact = next((tmp_path / "reports").glob("*.json"))
    data = json.loads(artifact.read_bytes())
    assert data["policy_id"] == str(policy)
    assert any(c["request_id"] == str(request) for c in data["cycle"]["children"])
    assert "dispatch_unknown" in data["attention_reasons"]
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert artifact.parent.stat().st_mode & 0o777 == 0o700
    assert str(tmp_path) not in artifact.read_text() and "archive_root" not in artifact.read_text()
    assert "private-failure-marker" not in artifact.read_text() + captured.out + captured.err
    assert database_snapshot(pg_dsn) == before


@pytest.mark.parametrize(
    "kind", ["bad_policy", "missing_dsn", "bad_age", "relative_output", "unknown_flag"]
)
def test_bad_configuration_is_fixed_and_never_publishes(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = arguments(uuid4(), tmp_path / "reports")
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-invalid-dsn")
    if kind == "bad_policy":
        args[3] = "private-company"
    elif kind == "missing_dsn":
        monkeypatch.delenv("NIMA_DATABASE_URL")
    elif kind == "bad_age":
        args[5] = "0"
    elif kind == "relative_output":
        args[-1] = "relative-private-output"
    else:
        args.append("--private-unknown-flag")
    assert main(args) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": "refresh_health_configuration"}
    assert "private" not in output.out + output.err
    assert not (tmp_path / "reports").exists()


def test_complete_today_with_verified_empty_capture_can_pass(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from datetime import UTC, datetime, timedelta

    from nima.orchestration.refresh import business_date
    from nima.storage.refresh_progress import reconcile
    from tests.test_refresh_progress import finish
    from tests.test_refresh_store import new_policy

    day = business_date(datetime.now(UTC))
    store, policy = new_policy(pg_dsn, tmp_path / "raw", start=day - timedelta(days=1))
    with store.lease(policy) as session:
        session.state("enabled")
        cycle = session.cycle(day)
        assert cycle is not None
        finish(pg_dsn, session.children(cycle)[0].request, empty=True)
        assert reconcile(session)
    with reader(pg_dsn) as dsn:
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(arguments(policy, tmp_path / "reports")) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "checks_passed"


@pytest.mark.parametrize("kind", ["database", "interrupt", "output"])
def test_operational_failures_and_interruption_stay_fixed(
    kind: str,
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nima.dataops import refresh_health_cli

    _, policy, _ = child(pg_dsn, tmp_path / "raw")
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    if kind == "database":
        monkeypatch.setenv("NIMA_DATABASE_URL", "host=127.0.0.1 port=1 dbname=private user=private")
    elif kind == "interrupt":

        def interrupt(*args: object) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(refresh_health_cli, "read_snapshot", interrupt)
    else:
        target = tmp_path / "original"
        target.mkdir(mode=0o700)
        (tmp_path / "reports").symlink_to(target, target_is_directory=True)
    assert main(arguments(policy, tmp_path / "reports")) == (130 if kind == "interrupt" else 1)
    captured = capsys.readouterr()
    assert (
        json.loads(captured.out)["failure"]
        == f"refresh_health_{'interrupted' if kind == 'interrupt' else kind}"
    )
    assert "private" not in captured.out + captured.err
