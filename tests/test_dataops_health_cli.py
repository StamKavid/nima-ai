"""Actual CLI, private publication, fixed events and no source requests."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from nima.__main__ import main
from nima.projections.worker import drain
from tests.test_analytics_snapshot import state
from tests.test_dataops_health_store import health_reader
from tests.test_metadata_export import kimdis_run


def arguments(tmp: Path, run: UUID) -> list[str]:
    return [
        "dataops",
        "health",
        "--run-id",
        str(run),
        "--capacity-dir",
        str(tmp / "archive"),
        "--max-capture-age-hours",
        "24",
        "--min-free-bytes",
        "1",
        "--output-dir",
        str(tmp / "out"),
    ]


@pytest.mark.parametrize("attention", [False, True])
def test_actual_cli_private_report_and_events_leave_sql_and_archive_unchanged(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    attention: bool,
) -> None:
    run = kimdis_run(
        pg_dsn,
        tmp_path / "archive",
        observed_at=datetime.now(UTC) - timedelta(hours=25 if attention else 0),
    )
    drain(pg_dsn, run_id=run)
    before = state(pg_dsn)
    originals = {p: p.read_bytes() for p in (tmp_path / "archive").rglob("*") if p.is_file()}
    args = arguments(tmp_path, run)
    if attention:
        args[args.index("--max-capture-age-hours") + 1] = "1"

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("source request")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    with health_reader(pg_dsn) as dsn:
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(args) == (3 if attention else 0)
    terminal = capsys.readouterr()
    expected = "attention" if attention else "checks_passed"
    assert json.loads(terminal.out) == {"status": expected, "attention_count": int(attention)}
    assert [json.loads(line)["event"] for line in terminal.err.splitlines()] == [
        "started",
        "completed",
    ]
    assert all(value not in terminal.out + terminal.err for value in (str(run), str(tmp_path), dsn))
    report = next((tmp_path / "out").glob("*.json"))
    assert json.loads(report.read_bytes())["status"] == expected
    assert report.stat().st_mode & 0o777 == 0o600
    assert state(pg_dsn) == before and all(p.read_bytes() == v for p, v in originals.items())


@pytest.mark.parametrize(
    "kind",
    [
        "threshold",
        "relative_capacity",
        "relative_output",
        "nested_output",
        "bad_run",
        "missing_dsn",
    ],
)
def test_configuration_errors_never_publish_or_echo_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    kind: str,
) -> None:
    args = arguments(tmp_path, UUID(int=1))
    monkeypatch.setenv("NIMA_DATABASE_URL", "invalid-private-dsn")
    if kind == "threshold":
        args[args.index("--min-free-bytes") + 1] = "0"
    elif kind == "relative_capacity":
        args[args.index("--capacity-dir") + 1] = "private-marker"
    elif kind == "relative_output":
        args[args.index("--output-dir") + 1] = "private-marker"
    elif kind == "nested_output":
        args[args.index("--output-dir") + 1] = str(tmp_path / "archive" / "reports")
    elif kind == "bad_run":
        args[args.index("--run-id") + 1] = "private-marker"
    else:
        monkeypatch.delenv("NIMA_DATABASE_URL")
    assert main(args) == 2
    terminal = capsys.readouterr()
    assert json.loads(terminal.out) == {"status": "failed", "failure": "health_configuration"}
    assert "private-marker" not in terminal.out + terminal.err
    assert json.loads(terminal.err.splitlines()[-1])["event"] == "failed"
    assert not (tmp_path / "out").exists()


def test_unsafe_output_preserves_existing_directory_and_reports_fixed_failure(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = kimdis_run(pg_dsn, tmp_path / "archive")
    out = tmp_path / "out"
    out.mkdir(mode=0o700)
    out.chmod(0o755)
    with health_reader(pg_dsn) as dsn:
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(arguments(tmp_path, run)) == 1
    terminal = capsys.readouterr()
    assert json.loads(terminal.out) == {"status": "failed", "failure": "health_output"}
    assert list(out.iterdir()) == [] and out.stat().st_mode & 0o777 == 0o755
    assert str(tmp_path) not in terminal.out + terminal.err


def test_interrupt_is_fixed_private_failure_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nima.dataops import health_cli

    def stop(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(health_cli, "prepare_health", stop)
    assert main(arguments(tmp_path, UUID(int=1))) == 130
    terminal = capsys.readouterr()
    assert json.loads(terminal.out) == {"status": "failed", "failure": "health_interrupted"}
    assert json.loads(terminal.err.splitlines()[-1])["reason"] == "health_interrupted"
    assert not (tmp_path / "out").exists()
