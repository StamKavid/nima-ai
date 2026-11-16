"""Private raw-to-count readout, real PostgreSQL and synthetic original evidence."""

import hashlib
import json
import socket
import stat
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Never
from uuid import uuid4

import psycopg
import pytest

from nima.analytics.export import export_readout
from nima.analytics.reconcile import ReconciledReadout, reconcile
from nima.analytics.request import ReadoutRequest
from nima.analytics.result import ReadoutError
from nima.analytics.snapshot import ReadoutSnapshot
from nima.graph.pilot_archive import ArchiveBinding
from nima.identity.artifacts import encode, publish
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.projections.worker import drain
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.test_analytics_reconcile import body_path, captured, seed_cohort
from tests.test_analytics_snapshot import reader, seed, state
from tests.test_collection import QUERY, body
from tests.test_semantics import CUTOFF, TAX


def request_file(request: ReadoutRequest, path: Path) -> Path:
    path.write_bytes(
        encode(
            {
                **request.semantic_payload(),
                "archive_bindings": [
                    {"run_id": str(binding.run_id), "root": str(binding.root)}
                    for binding in request.archive_bindings
                ],
            }
        )
    )
    path.chmod(0o600)
    return path


def test_known_answer_has_every_citation_and_keeps_inputs_unchanged(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = seed_cohort(pg_dsn, tmp_path / "originals")
    selection = request_file(request, tmp_path / "request.json")
    output = tmp_path / "reports"
    before = state(pg_dsn)
    originals = {path: path.read_bytes() for path in (tmp_path / "originals").rglob("*.body")}
    with reader(pg_dsn) as (dsn, _):
        summary = export_readout(dsn, selection, output)
        assert export_readout(dsn, selection, output) == summary
    final = output / (summary.artifact_sha256 + ".json")
    raw = final.read_bytes()
    result = json.loads(raw)
    metric = result["metric"]["result"]
    assert metric["total"] == summary.record_count == 5
    assert {row["buyer_key"]: row["record_count"] for row in metric["buyers"]} == {
        "kimdis.buyer-key:B1": 3,
        "kimdis.buyer-key:B2": 1,
    }
    assert metric["cancelled_count"] == metric["unknown_cancellation_count"] == 1
    assert metric["unassigned_source_ids"] == ["kimdis:E"]
    assert metric["ambiguous_source_ids"] == ["kimdis:G"]
    assert metric["unassessed_source_ids"] == ["kimdis:F"]
    assert {row["buyer_key"]: row["source_ids"] for row in metric["buyers"]} == {
        "kimdis.buyer-key:B1": ["kimdis:A", "kimdis:C", "kimdis:H"],
        "kimdis.buyer-key:B2": ["kimdis:D"],
    }
    decisions = {row["source_id"]: row for row in metric["records"]}
    assert decisions["kimdis:C"]["matching_ordinals"] == [0, 2]
    assert decisions["kimdis:B"]["matching_ordinals"] == []
    assert summary.buyer_count == 2
    assert summary.outcome == "observed_participation"
    assert len(result["evidence"]) == result["coverage"]["observation_count"] == 11
    assert result["coverage"]["source_record_count"] == 8
    assert result["coverage"]["version_count"] == 10
    assert len(result["coverage"]["pages"]) == 4
    assert result["coverage"]["first_page_observed_at"] == "2026-01-01T00:00:00+00:00"
    assert result["coverage"]["last_page_observed_at"] == "2026-01-03T00:00:00+00:00"
    assert result["metric"]["definition"]["status"] == "draft"
    assert result["request_sha256"] == request.request_sha256
    assert result["quality"]["identity"] == "reported_identifier_only"
    assert result["quality"]["source_current"] == "not_established"
    assert {row["selection"] for row in result["evidence"]} >= {
        "earlier_observation",
        "contributing",
        "ambiguous_revision",
        "unassessed_selection",
    }
    for row in result["evidence"]:
        assert row["json_pointer"] == "/content/" + str(row["record_index"])
        assert len(row["raw_sha256"]) == len(row["projection_sha256"]) == 64
        assert row["normalized"]["title"] == "Συνθετική δημοσίευση"
    assert encode(result) == raw
    assert hashlib.sha256(raw).hexdigest() == summary.artifact_sha256
    assert str(tmp_path) not in raw.decode() and dsn not in raw.decode()
    assert TAX not in repr(summary)
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE(final.stat().st_mode) == 0o600
    assert (output / ".gitignore").read_bytes() == b"*\n"
    assert state(pg_dsn) == before
    assert {path: path.read_bytes() for path in originals} == originals


def test_relocated_originals_produce_identical_result(pg_dsn: str, tmp_path: Path) -> None:
    request, _ = captured(pg_dsn, tmp_path / "original")
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        first = export_readout(dsn, selection, tmp_path / "one")
        moved = tmp_path / "relocated"
        request.archive_bindings[0].root.rename(moved)
        request_file(
            replace(request, archive_bindings=(replace(request.archive_bindings[0], root=moved),)),
            selection,
        )
        second = export_readout(dsn, selection, tmp_path / "two")
    assert first == second
    filename = first.artifact_sha256 + ".json"
    assert (tmp_path / "one" / filename).read_bytes() == (tmp_path / "two" / filename).read_bytes()
    result = json.loads((tmp_path / "one" / filename).read_bytes())
    assert result["evidence"][0]["normalized"]["net_amount"] == "1E+2"


def custom_capture(dsn: str, root: Path, **fields: object) -> ReadoutRequest:
    migrate(dsn)
    run = uuid4()
    store = RunStore(dsn, Archive(root), run, Limits())
    envelope = json.loads(body(total=1))
    envelope["content"][0].update(fields)
    with store.lease():
        store.begin(QUERY)
        store.commit_page(
            run,
            json.dumps(envelope).encode(),
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            owner=store.owner,
        )
        store.finish(Summary(status="complete"))
    drain(dsn, run_id=run)
    return ReadoutRequest((run,), CUTOFF, TAX, (ArchiveBinding("kimdis", run, root),))


@pytest.mark.parametrize(
    ("case", "outcome", "selection"),
    [
        ("empty", "empty_capture", None),
        ("late", "no_observations_before_cutoff", "after_cutoff"),
        ("no_match", "no_observed_participation", "no_eligible_reported_match"),
        ("unassessed", "selection_unresolved", "unassessed_selection"),
    ],
)
def test_nonparticipation_states_are_distinct_and_still_cited(
    pg_dsn: str, tmp_path: Path, case: str, outcome: str, selection: str | None
) -> None:
    if case == "unassessed":
        request = custom_capture(
            pg_dsn,
            tmp_path / "archive",
            contractingDataDetails={"contractingMembersDataList": [{"vatNumber": TAX}]},
        )
    else:
        request, _ = captured(pg_dsn, tmp_path / "archive", empty=case == "empty")
        if case == "late":
            request = replace(request, observation_cutoff=datetime(2025, 1, 1, tzinfo=UTC))
        elif case == "no_match":
            request = replace(request, supplier_tax_id="987654321")
    with reader(pg_dsn) as (dsn, _):
        summary = export_readout(
            dsn, request_file(request, tmp_path / "request.json"), tmp_path / "out"
        )
    assert summary.outcome == outcome and summary.record_count == 0
    result = json.loads((tmp_path / "out" / (summary.artifact_sha256 + ".json")).read_bytes())
    assert len(result["coverage"]["pages"]) == 1
    assert result["coverage"]["raw_object_count"] == 1
    if selection is None:
        assert result["evidence"] == []
    else:
        assert result["evidence"][0]["selection"] == selection


@pytest.mark.parametrize("failure", ["missing", "corrupt", "projection"])
def test_invalid_evidence_never_creates_output_or_changes_prior_artifact(
    pg_dsn: str, tmp_path: Path, failure: str
) -> None:
    request, snapshot = captured(pg_dsn, tmp_path / "archive")
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        summary = export_readout(dsn, selection, tmp_path / "prior")
        prior = tmp_path / "prior" / (summary.artifact_sha256 + ".json")
        preserved = prior.read_bytes()
        if failure == "projection":
            root = tmp_path / "unprojected"
            run = seed(pg_dsn, root, project=False)
            request_file(
                replace(
                    request, run_ids=(run,), archive_bindings=(ArchiveBinding("kimdis", run, root),)
                ),
                selection,
            )
        elif failure == "missing":
            body_path(request, snapshot).unlink()
        else:
            path = body_path(request, snapshot)
            path.write_bytes(path.read_bytes() + b" ")
        before = state(pg_dsn)
        with pytest.raises(ReadoutError) as error:
            export_readout(dsn, selection, tmp_path / "never-created")
        assert error.value.reason in {"analytics_archive", "analytics_projection"}
        assert str(error.value) == error.value.reason
        assert not (tmp_path / "never-created").exists()
        assert prior.read_bytes() == preserved
        assert state(pg_dsn) == before


@pytest.mark.parametrize("failure", ["conflict", "public_directory", "symlink"])
def test_unsafe_output_fails_without_overwrite(pg_dsn: str, tmp_path: Path, failure: str) -> None:
    request, _ = captured(pg_dsn, tmp_path / "archive")
    selection = request_file(request, tmp_path / "request.json")
    output = tmp_path / "out"
    with reader(pg_dsn) as (dsn, _):
        summary = export_readout(dsn, selection, output)
        final = output / (summary.artifact_sha256 + ".json")
        if failure == "conflict":
            final.write_bytes(b"conflicting bytes")
        elif failure == "public_directory":
            output.chmod(0o755)
        else:
            output = tmp_path / "link"
            output.symlink_to(tmp_path / "out", target_is_directory=True)
        expected = final.read_bytes()
        with pytest.raises(ReadoutError, match="^analytics_output$"):
            export_readout(dsn, selection, output)
        assert final.read_bytes() == expected


def test_result_byte_limit_fails_before_publication(pg_dsn: str, tmp_path: Path) -> None:
    request = custom_capture(pg_dsn, tmp_path / "archive", title="Ω" * 600_000)
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_limit$"):
        export_readout(dsn, selection, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_input_and_role_failures_are_fixed_and_do_not_publish(pg_dsn: str, tmp_path: Path) -> None:
    selection = tmp_path / "request.json"
    selection.write_bytes(b'{"password":"private"}')
    selection.chmod(0o600)
    with pytest.raises(ReadoutError, match="^analytics_input$"):
        export_readout(pg_dsn, selection, tmp_path / "out")
    request, _ = captured(pg_dsn, tmp_path / "archive")
    request_file(request, selection)
    with pytest.raises(ReadoutError, match="^analytics_role$"):
        export_readout(pg_dsn, selection, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_sql_is_closed_before_originals_and_publication_and_no_source_socket(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.analytics import export, snapshot
    from nima.storage.connection import connect

    request, _ = captured(pg_dsn, tmp_path / "archive")
    selection = request_file(request, tmp_path / "request.json")
    connections: list[psycopg.Connection[tuple[object, ...]]] = []

    def tracked(dsn: str) -> psycopg.Connection[tuple[object, ...]]:
        connection = connect(dsn)
        connections.append(connection)
        return connection

    def verify(*args: object, **kwargs: object) -> Never:
        raise AssertionError("Unexpected Python socket/source access")

    def after_close(snapshot: ReadoutSnapshot, request: ReadoutRequest) -> ReconciledReadout:
        assert len(connections) == 1 and connections[0].closed
        return reconcile(snapshot, request)

    def publish_after_close(directory: Path, body: bytes) -> str:
        assert len(connections) == 1 and connections[0].closed
        return publish(directory, body)

    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setattr(snapshot, "connect", tracked)
        monkeypatch.setattr(export, "reconcile", after_close)
        monkeypatch.setattr(export, "publish", publish_after_close)
        monkeypatch.setattr(socket, "socket", verify)
        assert export_readout(dsn, selection, tmp_path / "out").record_count == 1


def test_logical_original_counts_do_not_depend_on_physical_deduplication(
    pg_dsn: str, tmp_path: Path
) -> None:
    first, _ = captured(pg_dsn, tmp_path / "first")
    second, _ = captured(pg_dsn, tmp_path / "second")
    request = replace(
        first,
        run_ids=tuple(sorted(first.run_ids + second.run_ids)),
        archive_bindings=tuple(
            sorted(first.archive_bindings + second.archive_bindings, key=lambda b: b.run_id)
        ),
    )
    selection = request_file(request, tmp_path / "request.json")
    with reader(pg_dsn) as (dsn, _):
        original = export_readout(dsn, selection, tmp_path / "one")
        request_file(
            replace(
                request,
                archive_bindings=tuple(
                    replace(binding, root=first.archive_bindings[0].root)
                    for binding in request.archive_bindings
                ),
            ),
            selection,
        )
        deduplicated = export_readout(dsn, selection, tmp_path / "two")
    assert original == deduplicated
    report = json.loads((tmp_path / "one" / (original.artifact_sha256 + ".json")).read_bytes())
    assert report["coverage"]["raw_object_count"] == 1
    assert len(report["coverage"]["pages"]) == len(report["evidence"]) == 2
    assert original.record_count == 1
