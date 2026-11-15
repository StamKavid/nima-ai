"""Canonical private resolution artifacts retain evidence and explicit review states."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from nima.identity import review_export, review_snapshot, review_store
from nima.identity.artifacts import encode, publish
from nima.identity.review_inputs import decode_report
from nima.identity.review_state import fold_events
from nima.identity.review_types import ReviewError, ReviewSubject
from nima.storage.postgres import Connection, _connect
from tests.test_identity_review_accept import request
from tests.test_identity_review_evidence import seed_report
from tests.test_identity_review_inputs import report_body
from tests.test_identity_review_reversal import revoke


def unreviewed() -> review_snapshot.ResolutionSnapshot:
    parsed = decode_report(report_body())
    heads = tuple(
        fold_events(
            ReviewSubject(
                parsed.cohort.run_id,
                party.observation_id,
                parsed.cohort.projection_version,
                party.source_id,
                party.normalizer_version,
                party.content_sha256,
                party.role,
                party.ordinal,
            ),
            (),
        )
        for party in parsed.cohort.parties
    )
    return review_snapshot.ResolutionSnapshot(parsed, heads, (), (), 0)


def test_pure_export_keeps_unresolved_context_and_no_generation_clock() -> None:
    data = review_export.build_resolution(unreviewed())
    assert data["report_format"] == "nima-reviewed-resolution-v1"
    assert data["automatic_identity_links"] == data["reviewed_accepted_links"] == 0
    assert data["coverage_assurance"] == "unverified_report_context"
    assert data["comparison_report_sha256"] == unreviewed().report.sha256
    assert "generated_at" not in data
    assert all(item["review_status"] == "unresolved" for item in data["occurrences"])
    assert encode(data) == encode(review_export.build_resolution(unreviewed()))


def test_exact_export_byte_limit_precedes_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = unreviewed()
    body = encode(review_export.build_resolution(snapshot))
    monkeypatch.setattr(review_export, "read_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr("nima.identity.artifacts.MAX_REPORT_BYTES", len(body))
    result = review_export.export_resolution("unused", snapshot.report, tmp_path / "exact")
    assert (tmp_path / "exact" / (str(result["report_sha256"]) + ".json")).read_bytes() == body
    monkeypatch.setattr("nima.identity.artifacts.MAX_REPORT_BYTES", len(body) - 1)
    with pytest.raises(ReviewError, match="^review_limit$"):
        review_export.export_resolution("unused", snapshot.report, tmp_path / "too-large")
    assert not (tmp_path / "too-large").exists()


def test_private_export_closes_sql_then_reuses_exact_artifact_and_preserves_old_snapshot(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    connection_factory = _connect
    active = 0

    @contextmanager
    def tracked(dsn: str) -> Iterator[Connection]:
        nonlocal active
        with connection_factory(dsn) as connection:
            active += 1
            try:
                yield connection
            finally:
                active -= 1

    publisher = publish

    def closed(directory: Path, body: bytes) -> str:
        assert active == 0
        return publisher(directory, body)

    monkeypatch.setattr(review_snapshot, "_connect", tracked)
    monkeypatch.setattr(review_export, "publish", closed)
    output = tmp_path / "exports"
    first = review_export.export_resolution(pg_dsn, parsed, output)
    artifact = output / (str(first["report_sha256"]) + ".json")
    original = artifact.read_bytes(), artifact.stat().st_mtime_ns
    assert first == review_export.export_resolution(pg_dsn, parsed, output)
    assert original == (artifact.read_bytes(), artifact.stat().st_mtime_ns)
    data = json.loads(original[0])
    assert data["reviewed_accepted_links"] == 1 and data["automatic_identity_links"] == 0
    assert data["events"][0]["request"]["rationale"] == chosen.rationale
    assert data["attribution_assurance"] == "database_principal_only"
    assert output.stat().st_mode & 0o777 == 0o700 and artifact.stat().st_mode & 0o777 == 0o600
    review_store.review(pg_dsn, revoke(chosen, 1))
    second = review_export.export_resolution(pg_dsn, parsed, output)
    assert (
        second["report_sha256"] != first["report_sha256"] and second["reviewed_accepted_links"] == 0
    )
    assert original == (artifact.read_bytes(), artifact.stat().st_mtime_ns)
    assert len(list(output.glob("*.json"))) == 2


def test_selected_handle_ambiguity_is_explicit_without_entity_consolidation(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path / "one")
    chosen = request(parsed)
    review_store.review(pg_dsn, chosen, report=parsed)
    other = seed_report(pg_dsn, tmp_path / "two")
    another = request(other)
    review_store.review(pg_dsn, another, report=other)
    review_store.review(pg_dsn, revoke(chosen, 1))
    review_store.review(
        pg_dsn,
        replace(chosen, request_id=uuid4(), entity_id=another.entity_id, expected_revision=2),
        report=parsed,
    )
    data = review_export.build_resolution(review_snapshot.read_snapshot(pg_dsn, parsed))
    assert data["handle_ambiguity_scope"] == "selected_history_handles"
    assert data["selected_handle_ambiguities"] == [
        {
            "registry_number": "1",
            "entity_ids": sorted([str(chosen.entity_id), str(another.entity_id)]),
        }
    ]


def test_output_bounds_and_tampered_artifact_fail_without_replacing_it(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    output = tmp_path / "exports"
    with monkeypatch.context() as patch:
        patch.setattr("nima.identity.artifacts.MAX_REPORT_BYTES", 1)
        # In-memory report validation uses the same bounded canonical encoder.
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_export.export_resolution(pg_dsn, parsed, output)
    assert not output.exists()
    result = review_export.export_resolution(pg_dsn, parsed, output)
    artifact = output / (str(result["report_sha256"]) + ".json")
    artifact.write_bytes(b"private-sentinel")
    with pytest.raises(ReviewError, match="^review_output$"):
        review_export.export_resolution(pg_dsn, parsed, output)
    assert artifact.read_bytes() == b"private-sentinel"
