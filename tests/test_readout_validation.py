"""An explicit journal writer verifies actual private artifacts and original SQL."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from nima.analytics.export import export_readout
from nima.dataops.validation import validate_readout
from nima.storage.validations import show_validation
from tests.test_analytics_reconcile import seed_cohort
from tests.test_analytics_snapshot import reader, state
from tests.test_market_analytics import request_file
from tests.test_validation_store import journal_role


def test_fresh_and_cached_checks_preserve_sources_and_report(pg_dsn: str, tmp_path: Path) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "raw")
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (source, _), journal_role(pg_dsn) as journal:
        summary = export_readout(source, selection, tmp_path / "reports")
        report = tmp_path / "reports" / (summary.artifact_sha256 + ".json")
        before, body = state(pg_dsn), report.read_bytes()
        first_id = uuid4()
        first = validate_readout(source, journal, first_id, selection, report)
        assert first["status"] == "passed" and first["reused"] is False
        report.unlink()
        cached = validate_readout(source, journal, first_id, selection, report)
        assert cached == {**first, "reused": True}
        new_id = uuid4()
        blocked = validate_readout(source, journal, new_id, selection, report)
        assert blocked["status"] == "blocked"
        assert show_validation(journal, first_id)["status"] == "passed"
        report.write_bytes(body)
        report.chmod(0o600)
        second = validate_readout(source, journal, uuid4(), selection, report)
        assert second["outcome_sha256"] == first["outcome_sha256"]
        assert second["recorded_at"] != first["recorded_at"]
        assert state(pg_dsn) == before and report.read_bytes() == body


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("digest", "artifact_digest"),
        ("contract", "contract_rejected"),
        ("whitespace", "bytes_differ"),
        ("original", "inputs_unavailable"),
        ("symlink", "artifact_unavailable"),
        ("mode", "artifact_unavailable"),
    ],
)
def test_failed_or_blocked_inputs_are_recorded_without_mutation(
    pg_dsn: str, tmp_path: Path, fault: str, expected: str
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "raw")
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (source, _), journal_role(pg_dsn) as journal:
        summary = export_readout(source, selection, tmp_path / "reports")
        report = tmp_path / "reports" / (summary.artifact_sha256 + ".json")
        if fault in {"contract", "whitespace"}:
            body = report.read_bytes()
            if fault == "contract":
                value = json.loads(body)
                value["metric"]["result"]["total"] = 900
                body = json.dumps(value).encode()
            else:
                body += b"\n"
            report = report.with_name(hashlib.sha256(body).hexdigest() + ".json")
            report.write_bytes(body)
            report.chmod(0o600)
        elif fault == "digest":
            report.write_bytes(b"private-sentinel")
        elif fault == "original":
            next((tmp_path / "raw").rglob("*.body")).write_bytes(b"private-sentinel")
        elif fault == "symlink":
            saved = report.with_suffix(".saved")
            report.rename(saved)
            report.symlink_to(saved)
        elif fault == "mode":
            report.chmod(0o644)
        before = state(pg_dsn)
        attempt = uuid4()
        result = validate_readout(source, journal, attempt, selection, report)
        outcome = result["outcome"]
        assert isinstance(outcome, dict)
        assert outcome["reason"] == expected
        assert outcome["snapshot_sha256"] is None
        assert result["status"] in {"failed", "blocked"}
        assert show_validation(journal, attempt)["outcome"] == result["outcome"]
        assert "private-sentinel" not in json.dumps(result)
        assert str(tmp_path) not in json.dumps(result)
        assert state(pg_dsn) == before
