"""Actual selected-journal health uses only restricted SQL and packaged policy."""

import json
from uuid import uuid4

import httpx
import psycopg
import pytest

from nima.__main__ import main
from nima.contracts.history import Intent, Outcome
from nima.dataops.validation_health import current_policy
from nima.storage.postgres import migrate
from nima.storage.validations import Journal
from tests.test_validation_store import journal_role


@pytest.mark.parametrize(
    "status,expected", [("passed", 0), ("failed", 3), ("pending", 3), ("empty", 3)]
)
def test_actual_health_and_existing_routes_need_no_source_access(
    pg_dsn: str,
    status: str,
    expected: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    policy = current_policy()
    value = Intent("a" * 64, "b" * 64, policy["contract_version"], policy["contract_sha256"])
    with journal_role(pg_dsn) as writer:
        if status != "empty":
            with Journal(writer, uuid4(), value).session() as journal:
                if status == "passed":
                    journal.finish(
                        Outcome(value.digest, "passed", "byte_equivalence", "ok", "f" * 64, 1, 1)
                    )
                elif status == "failed":
                    journal.finish(
                        Outcome(value.digest, "failed", "artifact_integrity", "artifact_digest")
                    )
    with psycopg.connect(pg_dsn) as c:
        before = c.execute("SELECT count(*) FROM nima_validation.attempts").fetchone()

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Journal health must not revalidate artifacts or contact a source")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr("nima.evidence.artifacts.read", forbidden)
    monkeypatch.setattr("nima.analytics.snapshot.read_snapshot", forbidden)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    with journal_role(pg_dsn, write=False) as reader:
        monkeypatch.setenv("NIMA_VALIDATION_DATABASE_URL", reader)
        assert (
            main(
                [
                    "dataops",
                    "validation-health",
                    "--artifact-sha256",
                    "b" * 64,
                    "--max-check-age-hours",
                    "24",
                    "--max-pending-age-minutes",
                    "30",
                ]
            )
            == expected
        )
    terminal = capsys.readouterr()
    result = json.loads(terminal.out)
    assert result["status"] == ("checks_passed" if expected == 0 else "attention")
    assert result["verification_scope"] == "recorded_validation_history_only"
    assert [json.loads(line)["event"] for line in terminal.err.splitlines()] == [
        "started",
        "completed",
    ]
    assert pg_dsn not in terminal.out + terminal.err and reader not in terminal.out + terminal.err
    with psycopg.connect(pg_dsn) as c:
        assert c.execute("SELECT count(*) FROM nima_validation.attempts").fetchone() == before


@pytest.mark.parametrize("fault", ["artifact", "threshold", "missing", "unknown"])
def test_bad_configuration_is_fixed_and_never_echoed(
    fault: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("NIMA_VALIDATION_DATABASE_URL", "private-sentinel")
    args = [
        "dataops",
        "validation-health",
        "--artifact-sha256",
        "b" * 64,
        "--max-check-age-hours",
        "24",
        "--max-pending-age-minutes",
        "30",
    ]
    if fault == "artifact":
        args[3] = "private-sentinel"
    elif fault == "threshold":
        args[-1] = "0"
    elif fault == "missing":
        args = args[:-2]
    else:
        args.extend(["--unknown", "private-sentinel"])
    assert main(args) == 2
    terminal = capsys.readouterr()
    assert json.loads(terminal.out) == {"status": "failed", "failure": "validation_configuration"}
    assert "private-sentinel" not in terminal.out + terminal.err


def test_unbound_current_policy_refuses_health_before_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from nima.contracts import contract
    from nima.contracts.history import HistoryError
    from nima.dataops import validation_health

    metadata = contract()
    metadata["customProperties"][0]["value"]["revision"] = "private-sentinel"
    monkeypatch.setattr("nima.contracts.contract", lambda: metadata)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Bad supported policy must fail before SQL")

    monkeypatch.setattr(validation_health, "read_validation_history", forbidden)
    with pytest.raises(HistoryError, match="^validation_policy$"):
        validation_health.prepare_validation_health(
            "unused", "b" * 64, max_check_age_hours=24, max_pending_age_minutes=30
        )
