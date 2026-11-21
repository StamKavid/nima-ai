"""Observed-change readout: stored captures, counters decide comparability, originals verified."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.analytics import change_readout, commands, metric_readout
from nima.analytics.change_readout import export_change_readout, prepare_change_readout
from nima.analytics.change_request import (
    ChangeRequest,
    decode_change_request,
    read_change_request,
)
from nima.analytics.request import RequestError
from nima.analytics.result import ReadoutError
from nima.identity import AssessmentError
from nima.semantics.participation import SemanticError
from nima.storage.connection import Connection
from nima.storage.postgres import migrate
from tests.test_analytics_snapshot import reader, state
from tests.test_cpv_readout import record, seed

FAKE_SQL = "SELECT '{}'::jsonb FROM (SELECT %s::jsonb, %s::jsonb) x"


def row(reference: str, title: str = "Synthetic") -> dict[str, Any]:
    return {**record(reference, "2026-03-05T10:00:00.000000", ["45000000-7"]), "title": title}


def day(number: int) -> datetime:
    return datetime(2026, 1, number, tzinfo=UTC)


def capture(
    dsn: str, root: Path, name: str, rows: list[dict[str, Any]], observed: datetime
) -> tuple[UUID, Path]:
    archive = root / name
    return seed(dsn, archive, rows, observed), archive


def request_for(
    earlier: list[tuple[UUID, Path]], later: list[tuple[UUID, Path]], **overrides: object
) -> ChangeRequest:
    payload: dict[str, object] = {
        "version": "nima-observed-change-request-v1",
        "source": "kimdis.contract",
        "earlier_run_ids": [str(run) for run, _ in earlier],
        "later_run_ids": [str(run) for run, _ in later],
        "archive_bindings": [
            {"run_id": str(run), "root": str(path)} for run, path in (*earlier, *later)
        ],
        **overrides,
    }
    return decode_change_request(json.dumps(payload).encode())


def two_captures(dsn: str, root: Path) -> ChangeRequest:
    first = capture(dsn, root, "first", [row("X"), row("Y"), row("Z")], day(1))
    second = capture(
        dsn, root, "second", [row("X"), row("Y", "Revised"), row("W"), row("V")], day(2)
    )
    return request_for([first], [second])


def admin(dsn: str, statement: str, *parameters: object) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(statement, parameters)


def test_known_answer_from_two_complete_captures_leaves_the_database_unchanged(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = two_captures(pg_dsn, tmp_path)
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_change_readout(dsn, request)
    assert state(pg_dsn) == before
    assert result.status == "observed_changes"
    assert [row.source_id for row in result.added] == ["kimdis:V", "kimdis:W"]
    assert [row.source_id for row in result.changed] == ["kimdis:Y"]
    assert [row.source_id for row in result.missing_from_later_capture] == ["kimdis:Z"]
    assert result.unchanged == ("kimdis:X",)
    document = json.loads(body)
    assert document["version"] == "nima-observed-change-v1"
    assert document["request_sha256"] == request.request_sha256
    assert document["metric"]["result"] == result.payload()
    assert document["quality"]["raw_bytes"] == "verified_against_archived_bytes"
    assert document["cohort_sha256"] is not None
    assert len(document["verified_pages"]) == 2
    assert {row["capture"] for row in document["evidence"]} == {"earlier", "later"}
    assert len(document["evidence"]) == 7
    assert len(document["run_facts"]["earlier"]) == 1
    assert all(f["collection_complete"] for f in document["run_facts"]["earlier"])


def test_identical_captures_report_no_observed_change(pg_dsn: str, tmp_path: Path) -> None:
    first = capture(pg_dsn, tmp_path, "first", [row("X")], day(1))
    second = capture(pg_dsn, tmp_path, "second", [row("X")], day(2))
    with reader(pg_dsn) as (dsn, _):
        _, result = prepare_change_readout(dsn, request_for([first], [second]))
    assert result.status == "no_observed_change"
    assert result.counts.unchanged == 1


def test_several_runs_form_one_capture(pg_dsn: str, tmp_path: Path) -> None:
    a = capture(pg_dsn, tmp_path, "a", [row("X")], day(1))
    b = capture(pg_dsn, tmp_path, "b", [row("Y")], day(1))
    c = capture(pg_dsn, tmp_path, "c", [row("X"), row("Y")], day(2))
    with reader(pg_dsn) as (dsn, _):
        _, result = prepare_change_readout(dsn, request_for([a, b], [c]))
    assert result.status == "no_observed_change"
    assert result.earlier.records == 2 and result.later.records == 2


def test_a_run_that_did_not_finish_makes_the_metric_abstain_without_reading_archives(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = two_captures(pg_dsn, tmp_path)
    admin(
        pg_dsn,
        "UPDATE nima.ingest_runs SET status='failed' WHERE run_id=%s",
        request.later_run_ids[0],
    )
    for path in tmp_path.rglob("*.body"):
        path.unlink()
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_change_readout(dsn, request)
    assert (result.status, result.reasons) == ("incomparable", ("run_incomplete",))
    assert result.counts.added == result.counts.changed == 0
    document = json.loads(body)
    assert document["cohort_sha256"] is None
    assert document["quality"]["raw_bytes"] == "not_performed_incomparable"
    assert document["evidence"] == [] and document["verified_pages"] == []


def test_a_quarantined_record_makes_the_metric_abstain(pg_dsn: str, tmp_path: Path) -> None:
    request = two_captures(pg_dsn, tmp_path)
    admin(
        pg_dsn,
        "INSERT INTO nima.quarantine (run_id, page_number, record_index, reason)"
        " VALUES (%s, 0, 99, 'synthetic')",
        request.earlier_run_ids[0],
    )
    with reader(pg_dsn) as (dsn, _):
        _, result = prepare_change_readout(dsn, request)
    assert result.status == "incomparable"
    assert set(result.reasons) >= {"quarantined_records"}


def test_different_queries_make_the_metric_abstain(pg_dsn: str, tmp_path: Path) -> None:
    request = two_captures(pg_dsn, tmp_path)
    admin(
        pg_dsn,
        "UPDATE nima.ingest_runs SET query = query || '{\"dateTo\": \"2026-11-07\"}'::jsonb"
        " WHERE run_id=%s",
        request.later_run_ids[0],
    )
    with reader(pg_dsn) as (dsn, _):
        _, result = prepare_change_readout(dsn, request)
    assert (result.status, result.reasons) == ("incomparable", ("query_mismatch",))


def test_captures_that_are_not_strictly_ordered_make_the_metric_abstain(
    pg_dsn: str, tmp_path: Path
) -> None:
    first = capture(pg_dsn, tmp_path, "first", [row("X")], day(2))
    second = capture(pg_dsn, tmp_path, "second", [row("X")], day(1))
    with reader(pg_dsn) as (dsn, _):
        _, result = prepare_change_readout(dsn, request_for([first], [second]))
    assert (result.status, result.reasons) == ("incomparable", ("not_later",))


def test_a_changed_or_missing_original_is_refused_and_never_repaired(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = two_captures(pg_dsn, tmp_path)
    bodies = sorted(tmp_path.rglob("*.body"))
    original = bodies[0].read_bytes()
    bodies[0].write_bytes(original + b" ")
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_archive$"):
        prepare_change_readout(dsn, request)
    assert bodies[0].read_bytes() == original + b" "
    bodies[0].unlink()
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_archive$"):
        prepare_change_readout(dsn, request)


def test_a_capture_without_runs_abstains_as_no_runs(pg_dsn: str, tmp_path: Path) -> None:
    only = capture(pg_dsn, tmp_path, "only", [row("X")], day(1))
    request = request_for([], [only])
    with reader(pg_dsn) as (dsn, _):
        _, result = prepare_change_readout(dsn, request)
    assert (result.status, result.reasons) == ("incomparable", ("no_runs",))


def test_an_unknown_run_gives_a_fixed_reason(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    request = request_for([(uuid4(), tmp_path / "a")], [(uuid4(), tmp_path / "b")])
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_coverage$"):
        prepare_change_readout(dsn, request)


def test_a_sql_result_that_differs_from_the_provider_is_refused(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = two_captures(pg_dsn, tmp_path)
    monkeypatch.setattr(change_readout, "reference_sql", lambda: FAKE_SQL)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_metric$"):
        prepare_change_readout(dsn, request)


def test_the_size_limit_is_inclusive_and_encoding_failures_are_fixed(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = two_captures(pg_dsn, tmp_path)
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_change_readout(dsn, request)
        monkeypatch.setattr(metric_readout, "MAX_RESULT_BYTES", len(body))
        assert prepare_change_readout(dsn, request)[0] == body
        monkeypatch.setattr(metric_readout, "MAX_RESULT_BYTES", len(body) - 1)
        with pytest.raises(ReadoutError, match="^analytics_limit$"):
            prepare_change_readout(dsn, request)
        monkeypatch.undo()

        def refuse(value: object) -> bytes:
            raise AssessmentError("assessment_limit")

        monkeypatch.setattr(metric_readout, "encode", refuse)
        with pytest.raises(ReadoutError, match="^analytics_limit$"):
            prepare_change_readout(dsn, request)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (SemanticError("semantic_input"), "analytics_input"),
        (KeyError("private"), "analytics_evidence"),
        (OSError("private"), "analytics_output"),
    ],
)
def test_unexpected_failures_become_one_fixed_reason_without_details(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    reason: str,
) -> None:
    request = two_captures(pg_dsn, tmp_path)

    def fail(*args: object, **kwargs: object) -> Never:
        raise error

    monkeypatch.setattr(change_readout, "sql_rows", fail)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError) as caught:
        prepare_change_readout(dsn, request)
    assert caught.value.reason == reason
    assert "private" not in str(caught.value)


def test_export_publishes_one_content_addressed_private_artifact(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = two_captures(pg_dsn, tmp_path)
    request_dir = tmp_path / "request"
    request_dir.mkdir(mode=0o700)
    request_file = request_dir / "request.json"
    request_file.write_text(
        json.dumps(
            {
                **request.semantic_payload(),
                "archive_bindings": [
                    {"run_id": str(b.run_id), "root": str(b.root)} for b in request.archive_bindings
                ],
            }
        )
    )
    os.chmod(request_file, 0o600)
    with reader(pg_dsn) as (dsn, _):
        result = export_change_readout(dsn, request_file, tmp_path / "out")
    assert (result.added, result.changed, result.missing_from_later_capture, result.unchanged) == (
        2,
        1,
        1,
        1,
    )
    assert result.outcome == "observed_changes"
    published = tmp_path / "out" / f"{result.artifact_sha256}.json"
    assert json.loads(published.read_text())["request_sha256"] == request.request_sha256
    assert read_change_request(request_file) == request


def test_export_failures_are_fixed_reasons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ReadoutError, match="^analytics_input_file$"):
        export_change_readout("x", tmp_path / "missing.json", tmp_path / "out")
    request = request_for([(uuid4(), tmp_path / "a")], [(uuid4(), tmp_path / "b")])

    class Counts:
        added = changed = missing_from_later_capture = unchanged = 0

    class Result:
        status = "x"
        counts = Counts()

    monkeypatch.setattr(change_readout, "read_change_request", lambda path: request)
    monkeypatch.setattr(
        change_readout, "prepare_change_readout", lambda dsn, req: (b"{}", Result())
    )
    for raised, reason in (
        (AssessmentError("assessment_limit"), "analytics_limit"),
        (AssessmentError("output_io"), "analytics_output"),
        (OSError("private"), "analytics_output"),
    ):

        def fail(directory: Path, body: bytes, error: Exception = raised) -> Never:
            raise error

        monkeypatch.setattr(change_readout, "publish", fail)
        with pytest.raises(ReadoutError) as caught:
            export_change_readout("x", tmp_path / "r.json", tmp_path / "out")
        assert caught.value.reason == reason


def test_cli_routes_observed_change_and_prints_only_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[str, Path, Path]] = []

    def fake(dsn: str, request: Path, output: Path) -> change_readout.ChangeExport:
        seen.append((dsn, request, output))
        return change_readout.ChangeExport("a" * 64, "observed_changes", 1, 2, 3, 4)

    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    monkeypatch.setattr(commands, "export_change_readout", fake)
    code = commands.run(["observed-change", "--request", "/r.json", "--output-dir", "/o"])
    assert code == 0
    assert seen == [("private-sentinel", Path("/r.json"), Path("/o"))]
    assert json.loads(capsys.readouterr().out) == {
        "status": "complete",
        "artifact_sha256": "a" * 64,
        "outcome": "observed_changes",
        "added": 1,
        "changed": 2,
        "missing_from_later_capture": 3,
        "unchanged": 4,
    }


def valid_payload() -> dict[str, Any]:
    earlier, later = str(uuid4()), str(uuid4())
    return {
        "version": "nima-observed-change-request-v1",
        "source": "kimdis.contract",
        "earlier_run_ids": [earlier],
        "later_run_ids": [later],
        "archive_bindings": [
            {"run_id": earlier, "root": "/archive/a"},
            {"run_id": later, "root": "/archive/b"},
        ],
    }


def test_request_hash_ignores_archive_paths_and_covers_both_captures() -> None:
    first = valid_payload()
    moved = {
        **first,
        "archive_bindings": [{**b, "root": "/elsewhere"} for b in first["archive_bindings"]],
    }
    swapped = {
        **first,
        "earlier_run_ids": first["later_run_ids"],
        "later_run_ids": first["earlier_run_ids"],
    }
    hashes = [
        decode_change_request(json.dumps(item).encode()).request_sha256
        for item in (first, moved, swapped)
    ]
    assert hashes[0] == hashes[1] != hashes[2]


@pytest.mark.parametrize(
    "change",
    [
        {"version": "other"},
        {"source": "other"},
        {"earlier_run_ids": "x"},
        {"later_run_ids": None},
        {"extra": 1},
    ],
)
def test_request_rejects_invalid_fields_with_one_fixed_reason(change: dict[str, Any]) -> None:
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_change_request(json.dumps({**valid_payload(), **change}).encode())


def test_request_rejects_overlap_duplicates_bindings_and_bounds() -> None:
    base = valid_payload()
    shared = {**base, "later_run_ids": base["earlier_run_ids"]}
    shared["archive_bindings"] = base["archive_bindings"][:1]
    unbound = {**base, "archive_bindings": base["archive_bindings"][:1]}
    many = [str(uuid4()) for _ in range(11)]
    too_many = {
        **base,
        "earlier_run_ids": many[:6],
        "later_run_ids": many[6:],
        "archive_bindings": [{"run_id": run, "root": "/a"} for run in many],
    }
    for body in (shared, unbound, too_many):
        with pytest.raises(RequestError, match="^analytics_input$"):
            decode_change_request(json.dumps(body).encode())


def test_request_accepts_ten_runs_and_rejects_bad_bytes() -> None:
    runs = [str(uuid4()) for _ in range(10)]
    body = {
        **valid_payload(),
        "earlier_run_ids": runs[:5],
        "later_run_ids": runs[5:],
        "archive_bindings": [{"run_id": run, "root": "/a"} for run in runs],
    }
    assert len(decode_change_request(json.dumps(body).encode()).run_ids) == 10
    for broken in (b"{", b"\xff", b"[]", b'{"version": 1, "version": 2}'):
        with pytest.raises(RequestError, match="^analytics_input$"):
            decode_change_request(broken)
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_change_request("text")  # type: ignore[arg-type]
    with pytest.raises(RequestError, match="^analytics_limit$"):
        decode_change_request(b" " * (16 * 1024 + 1))


def test_a_cohort_read_on_a_held_snapshot_refuses_an_unsorted_or_repeated_selection(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.analytics.snapshot import SnapshotError, connected, read_cohort_in

    migrate(pg_dsn)
    run = uuid4()
    with reader(pg_dsn) as (dsn, _):
        for selection in ((), (run, run)):

            def read(connection: Connection, chosen: tuple[UUID, ...] = selection) -> object:
                return read_cohort_in(connection, chosen)

            with pytest.raises(SnapshotError, match="^analytics_input$"):
                connected(dsn, read)
