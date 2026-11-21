"""Buyer-concentration readout: stored runs, verified originals, SQL parity, private publication."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.analytics import buyer_readout, commands, metric_readout
from nima.analytics.buyer_readout import export_buyer_readout, prepare_buyer_readout
from nima.analytics.buyer_request import BuyerRequest, decode_buyer_request, read_buyer_request
from nima.analytics.request import RequestError
from nima.analytics.result import ReadoutError
from nima.identity import AssessmentError
from nima.semantics.participation import SemanticError
from nima.storage.postgres import migrate
from tests.test_analytics_snapshot import reader, state
from tests.test_cpv_readout import seed

CUTOFF = "2026-06-01T00:00:00+00:00"
S1, S2 = "012345678", "987654321"
FAKE_SQL = (
    "SELECT '{}'::jsonb FROM (SELECT %s::jsonb, %s::timestamptz, %s::text) x"
)


def record(reference: str, buyer: str, suppliers: list[str] | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "referenceNumber": reference,
        "title": "Synthetic",
        "organization": {"key": buyer, "value": "Synthetic buyer"},
    }
    if suppliers is not None:
        row["contractingDataDetails"] = {
            "contractingMembersDataList": [
                {"name": "Synthetic", "vatNumber": tax, "country": {"key": "EL"}}
                for tax in suppliers
            ]
        }
    return row


RECORDS = [
    record("A", "B1", [S1]),
    record("B", "B1", [S1, S2]),
    record("C", "B1", []),
    record("D", "B2", [S1]),
]


def request_for(run: UUID, root: Path, **overrides: object) -> BuyerRequest:
    payload: dict[str, object] = {
        "version": "nima-buyer-concentration-request-v1",
        "source": "kimdis.contract",
        "run_ids": [str(run)],
        "observation_cutoff": CUTOFF,
        "buyer": "B1",
        "archive_bindings": [{"run_id": str(run), "root": str(root)}],
        **overrides,
    }
    return decode_buyer_request(json.dumps(payload).encode())


def body_path(request: BuyerRequest, dsn: str) -> Path:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            "SELECT raw_sha256 FROM nima.run_pages WHERE run_id=%s", (request.run_ids[0],)
        ).fetchone()
    assert row is not None
    digest = str(row[0])
    return request.archive_bindings[0].root / "objects" / digest[:2] / (digest + ".body")


def test_known_answer_is_verified_against_originals_and_leaves_the_database_unchanged(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path / "archive", RECORDS)
    request = request_for(run, tmp_path / "archive")
    before = state(pg_dsn)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_buyer_readout(dsn, request)
    assert state(pg_dsn) == before
    assert result.status == "observed_concentration"
    assert (result.buyer_records, result.resolved_records, result.unresolved_records) == (3, 2, 1)
    assert [(s.supplier_key, s.record_count) for s in result.suppliers] == [
        (f"GR:{S1}", 2),
        (f"GR:{S2}", 1),
    ]
    assert (result.participation_total, result.joint_records) == (3, 1)
    assert result.top_supplier_keys == (f"GR:{S1}",)
    assert (result.unresolved_share.numerator, result.unresolved_share.denominator) == (1, 3)  # type: ignore[union-attr]
    document = json.loads(body)
    assert document["version"] == "nima-buyer-concentration-v1"
    assert document["request_sha256"] == request.request_sha256
    assert document["metric"]["result"] == result.payload()
    sources = {row["source_id"] for row in document["evidence"]}
    assert sources == {"kimdis:A", "kimdis:B", "kimdis:C"}
    cited = {row["source_id"]: row for row in document["evidence"]}
    assert cited["kimdis:C"]["resolution"] == "empty_suppliers"
    assert cited["kimdis:B"]["reported_suppliers"] == [
        {"ordinal": 0, "tax_id": S1, "country_code": "EL"},
        {"ordinal": 1, "tax_id": S2, "country_code": "EL"},
    ]
    assert cited["kimdis:A"]["json_pointer"] == "/content/0"
    assert {row["selection"] for row in document["evidence"]} == {"selected"}


def test_a_buyer_without_captured_records_is_reported_not_guessed(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path / "archive", RECORDS)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_buyer_readout(
            dsn, request_for(run, tmp_path / "archive", buyer="B9")
        )
    assert result.status == "no_observed_buyer_records"
    assert json.loads(body)["evidence"] == []


def test_a_changed_or_missing_original_is_refused_and_never_repaired(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path / "archive", RECORDS)
    request = request_for(run, tmp_path / "archive")
    path = body_path(request, pg_dsn)
    original = path.read_bytes()
    path.write_bytes(original.replace(S2.encode(), b"987654322"))
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_archive$"):
        prepare_buyer_readout(dsn, request)
    assert path.read_bytes() != original
    path.unlink()
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_archive$"):
        prepare_buyer_readout(dsn, request)


def test_a_sql_result_that_differs_from_the_provider_is_refused(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path / "archive", RECORDS)
    monkeypatch.setattr(buyer_readout, "reference_sql", lambda: FAKE_SQL)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_metric$"):
        prepare_buyer_readout(dsn, request_for(run, tmp_path / "archive"))


def test_unknown_runs_give_a_fixed_reason(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^analytics_coverage$"):
        prepare_buyer_readout(dsn, request_for(uuid4(), tmp_path / "archive"))


def multi_request(pairs: list[tuple[UUID, Path]], cutoff: str) -> BuyerRequest:
    return request_for(
        pairs[0][0],
        pairs[0][1],
        run_ids=[str(run) for run, _ in pairs],
        archive_bindings=[{"run_id": str(run), "root": str(root)} for run, root in pairs],
        observation_cutoff=cutoff,
    )


def test_each_stored_observation_is_labelled_by_how_it_was_selected(
    pg_dsn: str, tmp_path: Path
) -> None:
    def day(number: int) -> datetime:
        return datetime(2026, 1, number, tzinfo=UTC)

    plan = [
        ([record("A", "B1", [S1])], day(1)),
        ([record("A", "B1", [S2])], day(2)),
        ([record("D", "B2", [S1])], day(3)),
        ([record("G", "B1", [S1])], day(4)),
        ([record("G", "B1", [S2])], day(4)),
    ]
    runs = []
    for index, (rows, observed) in enumerate(plan):
        root = tmp_path / f"archive{index}"
        runs.append((seed(pg_dsn, root, rows, observed), root))
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_buyer_readout(
            dsn, multi_request(runs, "2026-01-05T00:00:00+00:00")
        )
    labels = {(row["source_id"], row["selection"]) for row in json.loads(body)["evidence"]}
    assert labels == {
        ("kimdis:A", "earlier_observation"),
        ("kimdis:A", "selected"),
        ("kimdis:G", "ambiguous_source"),
    }
    assert result.ambiguous_source_ids == ("kimdis:G",)
    assert [(s.supplier_key, s.record_count) for s in result.suppliers] == [(f"GR:{S2}", 1)]


def test_output_limits_and_encoding_failures_have_fixed_reasons(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path / "archive", RECORDS)
    request = request_for(run, tmp_path / "archive")
    with reader(pg_dsn) as (dsn, _):
        body, _ = prepare_buyer_readout(dsn, request)
        monkeypatch.setattr(metric_readout, "MAX_RESULT_BYTES", len(body))
        assert prepare_buyer_readout(dsn, request)[0] == body
        monkeypatch.setattr(metric_readout, "MAX_RESULT_BYTES", len(body) - 1)
        with pytest.raises(ReadoutError, match="^analytics_limit$"):
            prepare_buyer_readout(dsn, request)
        monkeypatch.undo()

        def refuse(value: object) -> bytes:
            raise AssessmentError("assessment_limit")

        monkeypatch.setattr(metric_readout, "encode", refuse)
        with pytest.raises(ReadoutError, match="^analytics_limit$"):
            prepare_buyer_readout(dsn, request)


@pytest.mark.parametrize(
    ("target", "error", "reason"),
    [
        ("evaluate", SemanticError("semantic_input"), "analytics_input"),
        ("evaluate", KeyError("private"), "analytics_evidence"),
        ("read_cohort", OSError("private"), "analytics_output"),
    ],
)
def test_unexpected_failures_become_one_fixed_reason_without_details(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    error: Exception,
    reason: str,
) -> None:
    run = seed(pg_dsn, tmp_path / "archive", RECORDS)

    def fail(*args: object, **kwargs: object) -> Never:
        raise error

    monkeypatch.setattr(buyer_readout, target, fail)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError) as caught:
        prepare_buyer_readout(dsn, request_for(run, tmp_path / "archive"))
    assert caught.value.reason == reason
    assert "private" not in str(caught.value)


def test_export_publishes_one_content_addressed_private_artifact(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path / "archive", RECORDS)
    request_dir = tmp_path / "request"
    request_dir.mkdir(mode=0o700)
    request_file = request_dir / "request.json"
    request_file.write_text(
        json.dumps(
            {
                "version": "nima-buyer-concentration-request-v1",
                "source": "kimdis.contract",
                "run_ids": [str(run)],
                "observation_cutoff": CUTOFF,
                "buyer": "B1",
                "archive_bindings": [{"run_id": str(run), "root": str(tmp_path / "archive")}],
            }
        )
    )
    os.chmod(request_file, 0o600)
    with reader(pg_dsn) as (dsn, _):
        result = export_buyer_readout(dsn, request_file, tmp_path / "out")
    assert (result.buyer_record_count, result.supplier_count) == (3, 2)
    assert result.outcome == "observed_concentration"
    published = tmp_path / "out" / f"{result.artifact_sha256}.json"
    assert json.loads(published.read_text())["request"]["buyer"] == "B1"
    assert read_buyer_request(request_file).buyer == "B1"


def test_export_failures_are_fixed_reasons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ReadoutError, match="^analytics_input_file$"):
        export_buyer_readout("x", tmp_path / "missing.json", tmp_path / "out")
    request = request_for(uuid4(), tmp_path / "archive")

    class Result:
        buyer_records = 0
        distinct_suppliers = 0
        status = "x"

    monkeypatch.setattr(buyer_readout, "read_buyer_request", lambda path: request)
    monkeypatch.setattr(buyer_readout, "prepare_buyer_readout", lambda dsn, req: (b"{}", Result()))
    for raised, reason in (
        (AssessmentError("assessment_limit"), "analytics_limit"),
        (AssessmentError("output_io"), "analytics_output"),
        (OSError("private"), "analytics_output"),
    ):

        def fail(directory: Path, body: bytes, error: Exception = raised) -> Never:
            raise error

        monkeypatch.setattr(buyer_readout, "publish", fail)
        with pytest.raises(ReadoutError) as caught:
            export_buyer_readout("x", tmp_path / "r.json", tmp_path / "out")
        assert caught.value.reason == reason


def test_cli_routes_buyer_concentration_and_prints_only_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[str, Path, Path]] = []

    def fake(dsn: str, request: Path, output: Path) -> buyer_readout.BuyerExport:
        seen.append((dsn, request, output))
        return buyer_readout.BuyerExport("a" * 64, 3, 2, "observed_concentration")

    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    monkeypatch.setattr(commands, "export_buyer_readout", fake)
    code = commands.run(["buyer-concentration", "--request", "/r.json", "--output-dir", "/o"])
    assert code == 0
    assert seen == [("private-sentinel", Path("/r.json"), Path("/o"))]
    assert json.loads(capsys.readouterr().out) == {
        "status": "complete",
        "artifact_sha256": "a" * 64,
        "buyer_record_count": 3,
        "supplier_count": 2,
        "outcome": "observed_concentration",
    }


def valid_payload() -> dict[str, Any]:
    run = uuid4()
    return {
        "version": "nima-buyer-concentration-request-v1",
        "source": "kimdis.contract",
        "run_ids": [str(run)],
        "observation_cutoff": CUTOFF,
        "buyer": "B1",
        "archive_bindings": [{"run_id": str(run), "root": "/archive"}],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"version": "other"},
        {"source": "other"},
        {"buyer": ""},
        {"buyer": " B1"},
        {"buyer": "B 1"},
        {"buyer": "B" * 65},
        {"buyer": 1},
        {"buyer": None},
        {"observation_cutoff": "2026-06-01"},
        {"run_ids": []},
        {"extra": 1},
    ],
)
def test_request_rejects_each_invalid_field_with_one_fixed_reason(change: dict[str, Any]) -> None:
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_buyer_request(json.dumps({**valid_payload(), **change}).encode())


def test_request_accepts_the_longest_buyer_and_hashes_selection_not_paths() -> None:
    first = {**valid_payload(), "buyer": "B" * 64}
    second = {**first, "archive_bindings": [{**first["archive_bindings"][0], "root": "/other"}]}
    third = {**first, "buyer": "B" * 63}
    hashes = [
        decode_buyer_request(json.dumps(item).encode()).request_sha256
        for item in (first, second, third)
    ]
    assert hashes[0] == hashes[1]
    assert hashes[0] != hashes[2]


def test_request_rejects_missing_field_duplicate_key_non_bytes_and_oversize() -> None:
    payload = valid_payload()
    del payload["buyer"]
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_buyer_request(json.dumps(payload).encode())
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_buyer_request(b'{"version": 1, "version": 2}')
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_buyer_request("text")  # type: ignore[arg-type]
    for broken in (b"{", b"\xff", b"[]"):
        with pytest.raises(RequestError, match="^analytics_input$"):
            decode_buyer_request(broken)
    with pytest.raises(RequestError, match="^analytics_limit$"):
        decode_buyer_request(b" " * (16 * 1024 + 1))
