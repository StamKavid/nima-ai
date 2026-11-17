"""Injected faults stop the real command before publication, without source access."""

import json
import socket
from dataclasses import replace
from pathlib import Path
from typing import Never

import psycopg
import pytest

from nima.__main__ import main
from tests.test_analytics_cli import arguments
from tests.test_analytics_reconcile import body_path, captured
from tests.test_analytics_snapshot import reader, state
from tests.test_market_analytics import request_file


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("missing_receipt", "analytics_projection"),
        ("duplicate_supplier", "analytics_projection"),
        ("wrong_amount", "analytics_projection"),
        ("corrupt_original", "analytics_archive"),
        ("corrupt_nonmatching", "analytics_archive"),
        ("missing_empty", "analytics_archive"),
    ],
)
def test_faults_block_publication_and_preserve_previous_results_and_all_rows(
    pg_dsn: str,
    tmp_path: Path,
    fault: str,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive", empty=fault == "missing_empty")
    if fault == "corrupt_nonmatching":
        request = replace(request, supplier_tax_id="987654321")
    path = request_file(request, tmp_path / "request.json")
    output = tmp_path / "prior"
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(arguments(path, output)) == 0
        summary = json.loads(capsys.readouterr().out)
        prior = output / (summary["artifact_sha256"] + ".json")
        preserved = prior.read_bytes(), prior.stat().st_mtime_ns
        # Fault injection is privileged fixture setup, never application behavior.
        if fault in {"missing_receipt", "duplicate_supplier", "wrong_amount"}:
            with psycopg.connect(pg_dsn) as admin:
                if fault == "missing_receipt":
                    admin.execute("ALTER TABLE nima.projection_receipts DISABLE TRIGGER USER")
                    admin.execute("DELETE FROM nima.projection_receipts")
                    admin.execute("ALTER TABLE nima.projection_receipts ENABLE TRIGGER USER")
                elif fault == "duplicate_supplier":
                    admin.execute("""INSERT INTO nima.projection_mentions
                        SELECT projection_version,source_id,normalizer_version,content_sha256,
                            role,1,name,tax_id,source_key,country_code
                        FROM nima.projection_mentions WHERE role='supplier' AND ordinal=0""")
                else:
                    admin.execute("ALTER TABLE nima.projection_contracts DISABLE TRIGGER USER")
                    admin.execute("UPDATE nima.projection_contracts SET net_amount=101")
                    admin.execute("ALTER TABLE nima.projection_contracts ENABLE TRIGGER USER")
        elif fault == "missing_empty":
            body_path(request, snapshot).unlink()
        else:
            original = body_path(request, snapshot)
            original.write_bytes(original.read_bytes() + b" ")
        before = state(pg_dsn)
        originals = {p: p.read_bytes() for p in (tmp_path / "archive").rglob("*.body")}

        def forbidden(*args: object, **kwargs: object) -> Never:
            pytest.fail("Offline failure handling must never open a source route")

        monkeypatch.setattr("httpx.Client", forbidden)
        monkeypatch.setattr(socket, "socket", forbidden)
        for destination in (output, tmp_path / "never-created"):
            assert main(arguments(path, destination)) == 1
            terminal = capsys.readouterr()
            assert json.loads(terminal.out) == {"status": "failed", "failure": reason}
            assert (
                not terminal.err and dsn not in terminal.out and str(tmp_path) not in terminal.out
            )
        assert not (tmp_path / "never-created").exists()
        assert preserved == (prior.read_bytes(), prior.stat().st_mtime_ns)
        assert list(output.glob("*.json")) == [prior]
        assert state(pg_dsn) == before
        assert {p: p.read_bytes() for p in originals} == originals


def test_database_grain_rejects_duplicate_observations_without_changing_a_report(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request, _ = captured(pg_dsn, tmp_path / "archive")
    path = request_file(request, tmp_path / "request.json")
    before = state(pg_dsn)
    with psycopg.connect(pg_dsn) as admin, pytest.raises(psycopg.errors.UniqueViolation):
        admin.execute("""INSERT INTO nima.observations
            (run_id,page_number,record_index,source_id,normalizer_version,content_sha256)
            SELECT run_id,page_number,record_index,source_id,normalizer_version,content_sha256
            FROM nima.observations""")
    assert state(pg_dsn) == before
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        assert main(arguments(path, tmp_path / "out")) == 0
    terminal = capsys.readouterr()
    assert json.loads(terminal.out)["record_count"] == 1 and not terminal.err
    assert state(pg_dsn) == before
