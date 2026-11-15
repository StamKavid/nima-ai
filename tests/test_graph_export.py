"""Real SQL graph publication is private, reproducible, bounded and read-only."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Never, cast
from uuid import UUID

import pytest

from nima.graph import GraphError, export, snapshot
from nima.graph.build import InvestigationGraph, build_graph
from nima.graph.snapshot import GraphSnapshot
from nima.identity import artifacts, review_store
from nima.identity.artifacts import encode, publish
from nima.identity.registry_cohort import read_comparison_cohort
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import Connection, _connect
from tests.test_graph_support import database_snapshot
from tests.test_identity_report import seed
from tests.test_identity_review_accept import request
from tests.test_identity_review_evidence import report, seed_report
from tests.test_identity_review_reversal import revoke
from tests.test_kimdis_pages import record
from tests.test_registry_cohort import registry_import


@pytest.mark.parametrize("value", ["private-sentinel", True, 1])
def test_invalid_export_focus_fails_before_sql(
    value: object, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid focus must fail before SQL")

    monkeypatch.setattr(export, "read_snapshot", forbidden)
    from tests.test_graph_build import inputs

    with pytest.raises(ValueError, match="^graph_configuration$"):
        export.export_graph(
            "private-sentinel", inputs().review.report, tmp_path, entity_id=cast(UUID, value)
        )


def test_export_closes_every_sql_connection_before_build_encode_and_publish_and_reuses_bytes(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    before = database_snapshot(pg_dsn)
    connections: list[Connection] = []

    @contextmanager
    def tracked(dsn: str) -> Iterator[Connection]:
        with _connect(dsn) as connection:
            connections.append(connection)
            yield connection

    def closed_build(data: GraphSnapshot, *, entity_id: UUID | None = None) -> InvestigationGraph:
        assert len(connections) >= 2 and all(c.closed for c in connections)
        return build_graph(data, entity_id=entity_id)

    def closed_encode(data: object) -> bytes:
        assert all(c.closed for c in connections)
        return encode(data)

    def closed_publish(directory: Path, body: bytes) -> str:
        assert all(c.closed for c in connections)
        return publish(directory, body)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Graph export is offline")

    monkeypatch.setattr(snapshot, "_connect", tracked)
    monkeypatch.setattr("nima.storage.postgres._connect", tracked)
    monkeypatch.setattr(export, "build_graph", closed_build)
    monkeypatch.setattr(export, "encode", closed_encode)
    monkeypatch.setattr(export, "publish", closed_publish)
    monkeypatch.setattr("httpx.Client", forbidden)
    output = tmp_path / "exports"
    first = export.export_graph(pg_dsn, parsed, output, entity_id=chosen.entity_id)
    artifact = output / (str(first["graph_sha256"]) + ".json")
    old = artifact.read_bytes(), artifact.stat().st_mtime_ns
    assert hashlib.sha256(old[0]).hexdigest() == first["graph_sha256"]
    data = json.loads(old[0])
    assert data["focus"]["state"] == "active_links"
    assert data["focus"]["contracts"][0]["buyer_selection"] == "selected"
    assert data["reviewed_resolution_sha256"] == first["reviewed_resolution_sha256"]
    assert (
        hashlib.sha256(encode(data["reviewed_resolution"])).hexdigest()
        == first["reviewed_resolution_sha256"]
    )
    assert first == export.export_graph(pg_dsn, parsed, output, entity_id=chosen.entity_id)
    assert old == (artifact.read_bytes(), artifact.stat().st_mtime_ns)
    assert output.stat().st_mode & 0o777 == 0o700 and artifact.stat().st_mode & 0o777 == 0o600
    assert len(before) == 26 and database_snapshot(pg_dsn) == before
    assert first["automatic_identity_links"] == 0 and first["reviewed_accepted_links"] == 1
    assert not any(
        k in first for k in ("nodes", "edges", "name", "title", "rationale", "output_dir")
    )
    assert chosen.rationale not in json.dumps(first, ensure_ascii=False)


def test_exact_final_byte_limit_precedes_output_creation(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    expected = encode(build_graph(snapshot.read_snapshot(pg_dsn, parsed)))
    before = database_snapshot(pg_dsn)
    monkeypatch.setattr(artifacts, "MAX_REPORT_BYTES", len(expected))
    result = export.export_graph(pg_dsn, parsed, tmp_path / "exact")
    assert (tmp_path / "exact" / (str(result["graph_sha256"]) + ".json")).read_bytes() == expected
    monkeypatch.setattr(artifacts, "MAX_REPORT_BYTES", len(expected) - 1)
    with pytest.raises(GraphError, match="^graph_limit$"):
        export.export_graph(pg_dsn, parsed, tmp_path / "too-large")
    assert not (tmp_path / "too-large").exists()
    assert database_snapshot(pg_dsn) == before


@pytest.mark.parametrize("failure", ["permissions", "symlink", "tampered"])
def test_output_failures_are_fixed_without_replacing_files_or_writing_sql(
    pg_dsn: str, tmp_path: Path, failure: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    before = database_snapshot(pg_dsn)
    output = tmp_path / "private-output-sentinel"
    artifact: Path | None = None
    if failure == "permissions":
        output.mkdir(mode=0o755)
        output.chmod(0o755)
    elif failure == "symlink":
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        output.symlink_to(target, target_is_directory=True)
    else:
        first = export.export_graph(pg_dsn, parsed, output)
        artifact = output / (str(first["graph_sha256"]) + ".json")
        artifact.write_bytes(b"private-corrupt-sentinel")
    with pytest.raises(GraphError, match="^graph_output$"):
        export.export_graph(pg_dsn, parsed, output)
    if artifact is not None:
        assert artifact.read_bytes() == b"private-corrupt-sentinel"
    assert database_snapshot(pg_dsn) == before


def test_joint_suppliers_keep_contract_money_once_and_focus_does_not_expand_selection(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(
        pg_dsn,
        tmp_path,
        {
            **record(),
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": "Άλφα", "vatNumber": "001234567", "country": {"key": "GR"}},
                    {"name": "Άλλος", "vatNumber": "001234567", "country": {"key": "GR"}},
                ]
            },
        },
    )
    imported = registry_import(pg_dsn, tmp_path)
    full = read_comparison_cohort(pg_dsn, run, (imported,), PROJECTION_VERSION)
    parsed = report(replace(full, parties=tuple(p for p in full.parties if p.role == "supplier")))
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    output = tmp_path / "exports"
    before = database_snapshot(pg_dsn)
    result = export.export_graph(pg_dsn, parsed, output, entity_id=chosen.entity_id)
    data = json.loads((output / (str(result["graph_sha256"]) + ".json")).read_bytes())
    contracts = [n for n in data["nodes"] if n["kind"] == "contract_version"]
    assert len(contracts) == 1 and contracts[0]["data"]["net_amount"] == "0.10"
    assert contracts[0]["data"]["supplier_count"] == 2
    assert contracts[0]["data"]["selected_supplier_occurrence_count"] == 2
    assert data["focus"]["contracts"][0]["buyer_selection"] == "not_selected"
    assert len([n for n in data["nodes"] if n["kind"] == "party_occurrence"]) == 2
    assert len([e for e in data["edges"] if e["kind"] == "reviewed_as"]) == 1
    assert all("amount" not in key for e in data["edges"] for key in e["data"])
    review_store.review(pg_dsn, revoke(chosen, 1))
    after_writer = database_snapshot(pg_dsn)
    assert all(
        after_writer[k] == v
        for k, v in before.items()
        if k != "identity_review_events" and k != "identity_review_heads"
    )
    changed = export.export_graph(pg_dsn, parsed, output, entity_id=chosen.entity_id)
    assert changed["graph_sha256"] != result["graph_sha256"]
    assert database_snapshot(pg_dsn) == after_writer
