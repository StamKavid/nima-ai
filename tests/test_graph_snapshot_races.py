"""Independent committed revocations cannot split an exported graph snapshot."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from nima.graph import export
from nima.graph.build import InvestigationGraph, build_graph
from nima.graph.snapshot import GraphSnapshot
from nima.identity import review_snapshot, review_store
from nima.identity.review_types import ReviewReport
from nima.storage.postgres import Connection
from tests.test_graph_support import database_snapshot
from tests.test_identity_review_accept import request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_reversal import revoke


@pytest.mark.parametrize("phase", ["pinned_read", "closed_read"])
def test_export_is_wholly_before_or_after_a_concurrent_revoke(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    initial = database_snapshot(pg_dsn)
    reversal = revoke(chosen, 1)
    original = review_snapshot.read_snapshot_in_transaction

    def during(
        connection: Connection,
        report: ReviewReport,
        *,
        max_events: int = 10000,
        reserve_bytes: int = 0,
    ) -> review_snapshot.ResolutionSnapshot:
        review_store.review(pg_dsn, reversal)
        return original(connection, report, max_events=max_events, reserve_bytes=reserve_bytes)

    def after_read(data: GraphSnapshot, *, entity_id: UUID | None = None) -> InvestigationGraph:
        review_store.review(pg_dsn, reversal)
        return build_graph(data, entity_id=entity_id)

    output = tmp_path / "exports"
    with monkeypatch.context() as patch:
        if phase == "pinned_read":
            patch.setattr(review_snapshot, "read_snapshot_in_transaction", during)
        else:
            patch.setattr(export, "build_graph", after_read)
        earlier = export.export_graph(pg_dsn, parsed, output, entity_id=chosen.entity_id)
    old_path = output / (str(earlier["graph_sha256"]) + ".json")
    old_bytes = old_path.read_bytes(), old_path.stat().st_mtime_ns
    old = json.loads(old_bytes[0])
    after_writer = database_snapshot(pg_dsn)
    later = export.export_graph(pg_dsn, parsed, output, entity_id=chosen.entity_id)
    new = json.loads((output / (str(later["graph_sha256"]) + ".json")).read_bytes())
    assert earlier["reviewed_accepted_links"] == 1 and later["reviewed_accepted_links"] == 0
    assert old["focus"]["state"] == "active_links" and new["focus"]["state"] == "no_active_links"
    assert len(old["reviewed_resolution"]["events"]) == 1
    assert len(new["reviewed_resolution"]["events"]) == 2
    assert len([e for e in old["edges"] if e["kind"] == "reviewed_as"]) == 1
    assert not any(e["kind"] == "reviewed_as" for e in new["edges"])
    assert any(n["kind"] == "entity_handle" for n in new["nodes"])
    assert [n for n in old["nodes"] if n["kind"] != "party_occurrence"] == [
        n for n in new["nodes"] if n["kind"] != "party_occurrence"
    ]
    assert old_bytes == (old_path.read_bytes(), old_path.stat().st_mtime_ns)
    assert len(list(output.glob("*.json"))) == 2
    assert all(
        after_writer[k] == v
        for k, v in initial.items()
        if k not in {"identity_review_events", "identity_review_heads"}
    )
    assert database_snapshot(pg_dsn) == after_writer
