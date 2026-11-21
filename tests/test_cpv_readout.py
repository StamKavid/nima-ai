"""CPV-by-period readout: stored runs, verified originals, SQL parity and private publication."""

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never
from uuid import UUID, uuid4

import pytest

from nima.analytics import commands, cpv_readout
from nima.analytics.cpv_readout import export_cpv_readout, prepare_cpv_readout
from nima.analytics.cpv_request import CpvRequest, decode_cpv_request, read_cpv_request
from nima.analytics.request import RequestError
from nima.analytics.result import ReadoutError
from nima.ingestion.archive import Archive
from nima.ingestion.config import Limits, Summary
from nima.metadata import extract
from nima.identity import AssessmentError
from nima.metadata.extract import MetadataError
from nima.semantics.cpv_period import SemanticError
from nima.projections.worker import drain
from nima.storage.postgres import migrate
from nima.storage.runs import RunStore
from tests.test_analytics_snapshot import reader, state
from tests.test_collection import QUERY

CUTOFF = "2026-06-01T00:00:00+00:00"
FAKE_SQL = (
    "SELECT '{}'::jsonb FROM "
    "(SELECT %s::jsonb, %s::timestamptz, %s::text, %s::text, %s::text) x"
)


def record(reference: str, submitted: str | None, cpvs: list[str] | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "referenceNumber": reference,
        "title": "Synthetic",
        "organization": {"key": "B1", "value": "Synthetic buyer"},
        "contractingDataDetails": {
            "contractingMembersDataList": [
                {"name": "Synthetic", "vatNumber": "012345678", "country": {"key": "EL"}}
            ]
        },
        "submissionDate": submitted,
    }
    if cpvs is not None:
        row["objectDetailsList"] = [{"cpvs": [{"key": code, "value": "Reported"} for code in cpvs]}]
    return row


RECORDS = [
    record("A", "2026-03-05T10:00:00.000000", ["45000000-7", "45100000-8"]),
    record("B", "2026-03-20T09:00:00.5", ["45000000-7"]),
    record("C", "2026-04-01T00:00:00.000000", None),
]


def seed(
    dsn: str,
    root: Path,
    rows: list[dict[str, Any]] | None = None,
    observed: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> UUID:
    migrate(dsn)
    content = RECORDS if rows is None else rows
    run = uuid4()
    store = RunStore(dsn, Archive(root), run, Limits())
    raw = json.dumps(
        {
            "content": content,
            "number": 0,
            "size": len(content),
            "totalElements": len(content),
            "totalPages": 1,
            "last": True,
        }
    ).encode()
    with store.lease():
        store.begin(QUERY)
        store.commit_page(
            run, raw, observed_at=observed, owner=store.owner
        )
        store.finish(Summary(status="complete"))
    drain(dsn, run_id=run)
    return run


def request_for(run: UUID, root: Path, **overrides: object) -> CpvRequest:
    payload: dict[str, object] = {
        "version": "nima-cpv-period-request-v1",
        "source": "kimdis.contract",
        "run_ids": [str(run)],
        "observation_cutoff": CUTOFF,
        "cpv_base_code": None,
        "period_from": None,
        "period_to": None,
        "archive_bindings": [{"run_id": str(run), "root": str(root)}],
        **overrides,
    }
    return decode_cpv_request(json.dumps(payload).encode())


def body_path(request: CpvRequest, dsn: str) -> Path:
    import psycopg

    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            "SELECT raw_sha256 FROM nima.run_pages WHERE run_id=%s", (request.run_ids[0],)
        ).fetchone()
    assert row is not None
    digest = str(row[0])
    return request.archive_bindings[0].root / "objects" / digest[:2] / (digest + ".body")


def test_known_answer_comes_from_original_bytes_and_leaves_the_database_unchanged(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    request = request_for(run, tmp_path / "archive")
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_cpv_readout(dsn, request)
    assert state(pg_dsn) == before
    assert result.status == "observed_activity"
    assert [(c.cpv_base_code, c.period, c.record_count) for c in result.cells] == [
        ("45000000", "2026-03", 2),
        ("45100000", "2026-03", 1),
        (None, "2026-04", 1),
    ]
    assert [(t.period, t.record_count) for t in result.period_totals] == [
        ("2026-03", 2),
        ("2026-04", 1),
    ]
    document = json.loads(body)
    assert document["version"] == "nima-cpv-period-v1"
    assert document["request_sha256"] == request.request_sha256
    assert document["metric"]["result"] == result.payload()
    assert re.fullmatch(r"[0-9a-f]{64}", document["cohort_sha256"])
    assert {row["selection"] for row in document["evidence"]} == {"selected"}
    cited = {row["source_id"]: row["cpv_assertions"] for row in document["evidence"]}
    assert [a["code"] for a in cited["kimdis:A"]] == ["45000000-7", "45100000-8"]
    assert cited["kimdis:C"][0]["status"] == "missing"
    assert cited["kimdis:A"][0]["json_pointer"] == "/content/0/objectDetailsList/0/cpvs/0"


def test_filters_select_one_code_and_a_period_window(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _):
        _, by_code = prepare_cpv_readout(
            dsn, request_for(run, tmp_path / "archive", cpv_base_code="45100000")
        )
        _, by_window = prepare_cpv_readout(
            dsn,
            request_for(run, tmp_path / "archive", period_from="2026-04", period_to="2026-04"),
        )
    assert [(c.cpv_base_code, c.record_count) for c in by_code.cells] == [("45100000", 1)]
    assert [(c.cpv_base_code, c.period) for c in by_window.cells] == [(None, "2026-04")]


def test_a_changed_original_is_refused_and_never_repaired(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    request = request_for(run, tmp_path / "archive")
    path = body_path(request, pg_dsn)
    original = path.read_bytes()
    path.write_bytes(original.replace(b"45100000-8", b"45100000-9"))
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_archive$"):
        prepare_cpv_readout(dsn, request)
    assert path.read_bytes() != original


def test_missing_original_is_refused(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    request = request_for(run, tmp_path / "archive")
    body_path(request, pg_dsn).unlink()
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_archive$"):
        prepare_cpv_readout(dsn, request)


def test_metadata_that_disagrees_with_the_stored_record_is_refused(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    real = extract.kimdis_metadata

    def altered(raw: bytes) -> Any:
        rows = list(real(raw))
        rows[0] = {**rows[0], "content_sha256": "0" * 64}
        return tuple(rows)

    monkeypatch.setattr("nima.analytics.cpv_readout.kimdis_metadata", altered)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_evidence$"):
        prepare_cpv_readout(dsn, request_for(run, tmp_path / "archive"))


def test_a_sql_result_that_differs_from_the_provider_is_refused(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    monkeypatch.setattr(
        cpv_readout,
        "reference_sql",
        lambda: FAKE_SQL,
    )
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_metric$"):
        prepare_cpv_readout(dsn, request_for(run, tmp_path / "archive"))


def test_unprojected_or_unknown_runs_give_fixed_reasons(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    request = request_for(uuid4(), tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_coverage$"):
        prepare_cpv_readout(dsn, request)


def test_export_publishes_one_content_addressed_private_artifact(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    request_dir = tmp_path / "request"
    request_dir.mkdir(mode=0o700)
    payload = {
        "version": "nima-cpv-period-request-v1",
        "source": "kimdis.contract",
        "run_ids": [str(run)],
        "observation_cutoff": CUTOFF,
        "cpv_base_code": "45000000",
        "period_from": None,
        "period_to": None,
        "archive_bindings": [{"run_id": str(run), "root": str(tmp_path / "archive")}],
    }
    request_file = request_dir / "request.json"
    request_file.write_text(json.dumps(payload))
    os.chmod(request_file, 0o600)
    output = tmp_path / "out"
    with reader(pg_dsn) as (dsn, _):
        result = export_cpv_readout(dsn, request_file, output)
    assert result.outcome == "observed_activity"
    assert result.record_count == 3
    assert result.cell_count == 1
    published = output / f"{result.artifact_sha256}.json"
    assert json.loads(published.read_text())["request"]["cpv_base_code"] == "45000000"
    assert read_cpv_request(request_file).cpv_base_code == "45000000"


def test_cli_routes_cpv_period_and_prints_only_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[str, Path, Path]] = []

    def fake(dsn: str, request: Path, output: Path) -> cpv_readout.CpvExport:
        seen.append((dsn, request, output))
        return cpv_readout.CpvExport("a" * 64, 3, 2, "observed_activity")

    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    monkeypatch.setattr(commands, "export_cpv_readout", fake)
    code = commands.run(["cpv-period", "--request", "/r.json", "--output-dir", "/o"])
    assert code == 0
    assert seen == [("private-sentinel", Path("/r.json"), Path("/o"))]
    assert json.loads(capsys.readouterr().out) == {
        "status": "complete",
        "artifact_sha256": "a" * 64,
        "record_count": 3,
        "cell_count": 2,
        "outcome": "observed_activity",
    }


def valid_payload() -> dict[str, Any]:
    run = uuid4()
    return {
        "version": "nima-cpv-period-request-v1",
        "source": "kimdis.contract",
        "run_ids": [str(run)],
        "observation_cutoff": CUTOFF,
        "cpv_base_code": None,
        "period_from": None,
        "period_to": None,
        "archive_bindings": [{"run_id": str(run), "root": "/archive"}],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"version": "other"},
        {"source": "other"},
        {"cpv_base_code": "4500000"},
        {"cpv_base_code": "450000001"},
        {"period_from": "2026-031"},
        {"cpv_base_code": 45000000},
        {"period_from": "2026-13"},
        {"period_from": "2026-05", "period_to": "2026-04"},
        {"observation_cutoff": "2026-06-01"},
        {"run_ids": []},
        {"extra": 1},
    ],
)
def test_request_rejects_each_invalid_field_with_one_fixed_reason(change: dict[str, Any]) -> None:
    payload = {**valid_payload(), **change}
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_cpv_request(json.dumps(payload).encode())


def test_request_rejects_missing_field_duplicate_key_and_non_bytes() -> None:
    payload = valid_payload()
    del payload["period_to"]
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_cpv_request(json.dumps(payload).encode())
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_cpv_request(b'{"version": 1, "version": 2}')
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_cpv_request("text")  # type: ignore[arg-type]
    with pytest.raises(RequestError, match="^analytics_limit$"):
        decode_cpv_request(b" " * (16 * 1024 + 1))


def test_request_hash_ignores_archive_paths_and_covers_filters() -> None:
    first = valid_payload()
    second = {**first, "archive_bindings": [{**first["archive_bindings"][0], "root": "/other"}]}
    third = {**first, "cpv_base_code": "45000000"}
    hashes = [
        decode_cpv_request(json.dumps(item).encode()).request_sha256
        for item in (first, second, third)
    ]
    assert hashes[0] == hashes[1]
    assert hashes[0] != hashes[2]


def multi_request(pairs: list[tuple[UUID, Path]], cutoff: str) -> CpvRequest:
    payload = {
        **valid_payload(),
        "observation_cutoff": cutoff,
        "run_ids": [str(run) for run, _ in pairs],
        "archive_bindings": [{"run_id": str(run), "root": str(root)} for run, root in pairs],
    }
    return decode_cpv_request(json.dumps(payload).encode())


def test_each_stored_observation_is_labelled_by_how_it_was_selected(
    pg_dsn: str, tmp_path: Path
) -> None:
    def day(number: int) -> datetime:
        return datetime(2026, 1, number, tzinfo=UTC)

    a1 = record("A", "2026-03-05T10:00:00.000000", ["45000000-7"])
    a2 = record("A", "2026-03-05T10:00:00.000000", ["45100000-8"])
    d = record("D", "2026-03-05T10:00:00.000000", ["45000000-7"])
    runs = []
    for index, (rows, observed) in enumerate(
        [([a1], day(1)), ([a2], day(2)), ([record("E", None, None)], day(3)), ([d], day(9))]
    ):
        root = tmp_path / f"archive{index}"
        runs.append((seed(pg_dsn, root, rows, observed), root))
    # Two different versions of one record at the same instant cannot be ordered.
    for index, rows in enumerate([[record("G", None, ["45000000-7"])], [record("G", None, None)]]):
        root = tmp_path / f"tie{index}"
        runs.append((seed(pg_dsn, root, rows, day(4)), root))
    request = multi_request(runs, "2026-01-05T00:00:00+00:00")
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_cpv_readout(dsn, request)
    labels = {
        (row["source_id"], row["selection"]) for row in json.loads(body)["evidence"]
    }
    assert labels == {
        ("kimdis:A", "earlier_observation"),
        ("kimdis:A", "selected"),
        ("kimdis:E", "selected"),
        ("kimdis:D", "after_cutoff"),
        ("kimdis:G", "ambiguous_revision"),
    }
    assert result.ambiguous_source_ids == ("kimdis:G",)


def test_output_limits_and_encoding_failures_have_fixed_reasons(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    request = request_for(run, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _):
        monkeypatch.setattr(cpv_readout, "MAX_RESULT_BYTES", 10)
        with pytest.raises(ReadoutError, match="^analytics_limit$"):
            prepare_cpv_readout(dsn, request)
        monkeypatch.undo()

        def refuse(value: object) -> bytes:
            raise AssessmentError("assessment_limit")

        monkeypatch.setattr(cpv_readout, "encode", refuse)
        with pytest.raises(ReadoutError, match="^analytics_limit$"):
            prepare_cpv_readout(dsn, request)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (MetadataError("metadata_limit"), "analytics_evidence"),
        (SemanticError("semantic_input"), "analytics_input"),
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
    run = seed(pg_dsn, tmp_path / "archive")

    def fail(*args: object, **kwargs: object) -> Never:
        raise error

    target = "kimdis_metadata" if isinstance(error, MetadataError) else "evaluate"
    if isinstance(error, OSError):
        target = "read_cohort"
    monkeypatch.setattr(cpv_readout, target, fail)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError) as caught:
        prepare_cpv_readout(dsn, request_for(run, tmp_path / "archive"))
    assert caught.value.reason == reason
    assert "private" not in str(caught.value)


def test_export_failures_are_fixed_reasons(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ReadoutError, match="^analytics_input_file$"):
        export_cpv_readout("x", tmp_path / "missing.json", tmp_path / "out")
    request = request_for(uuid4(), tmp_path / "archive")
    monkeypatch.setattr(cpv_readout, "read_cpv_request", lambda path: request)
    monkeypatch.setattr(cpv_readout, "prepare_cpv_readout", lambda dsn, req: (b"{}", None))
    for raised, reason in (
        (AssessmentError("assessment_limit"), "analytics_limit"),
        (AssessmentError("output_io"), "analytics_output"),
        (OSError("private"), "analytics_output"),
    ):

        def fail(directory: Path, body: bytes, error: Exception = raised) -> Never:
            raise error

        monkeypatch.setattr(cpv_readout, "publish", fail)
        with pytest.raises(ReadoutError) as caught:
            export_cpv_readout("x", tmp_path / "r.json", tmp_path / "out")
        assert caught.value.reason == reason


@pytest.mark.parametrize(
    "change",
    [
        lambda p: {
            "run_ids": [p["run_ids"][0], p["run_ids"][0]],
            "archive_bindings": p["archive_bindings"] * 2,
        },
        lambda p: {"archive_bindings": []},
        lambda p: {"archive_bindings": ["x"]},
        lambda p: {"archive_bindings": [{"run_id": p["run_ids"][0]}]},
        lambda p: {"archive_bindings": [{"run_id": str(uuid4()), "root": "/archive"}]},
        lambda p: {"archive_bindings": [{"run_id": p["run_ids"][0], "root": "relative"}]},
        lambda p: {"run_ids": ["not-a-uuid"]},
        lambda p: {"run_ids": "x"},
    ],
)
def test_request_rejects_bad_run_and_archive_bindings(change: Any) -> None:
    payload = valid_payload()
    payload.update(change(payload))
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_cpv_request(json.dumps(payload).encode())


def test_an_invalid_reported_code_stays_unclassified_and_is_cited(
    pg_dsn: str, tmp_path: Path
) -> None:
    rows = [record("A", "2026-03-05T10:00:00.000000", ["not-a-code"])]
    run = seed(pg_dsn, tmp_path / "archive", rows)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_cpv_readout(dsn, request_for(run, tmp_path / "archive"))
    assert result.coverage.unclassified_no_reported_code == 1
    assert [(c.cpv_base_code, c.record_count) for c in result.cells] == [(None, 1)]
    cited = json.loads(body)["evidence"][0]["cpv_assertions"]
    assert [(a["status"], a["code"]) for a in cited] == [("invalid", "not-a-code")]


def test_a_window_with_two_months_keeps_both_ends(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    request = request_for(run, tmp_path / "archive", period_from="2026-03", period_to="2026-04")
    with reader(pg_dsn) as (dsn, _):
        _, result = prepare_cpv_readout(dsn, request)
    assert {c.period for c in result.cells} == {"2026-03", "2026-04"}


def test_the_result_size_limit_is_inclusive(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path / "archive")
    request = request_for(run, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_cpv_readout(dsn, request)
        monkeypatch.setattr(cpv_readout, "MAX_RESULT_BYTES", len(body))
        assert prepare_cpv_readout(dsn, request)[0] == body
        monkeypatch.setattr(cpv_readout, "MAX_RESULT_BYTES", len(body) - 1)
        with pytest.raises(ReadoutError, match="^analytics_limit$"):
            prepare_cpv_readout(dsn, request)
