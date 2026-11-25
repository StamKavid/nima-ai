"""Reject damaged evidence, unsupported processing identities and boundary failures."""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Never, cast
from uuid import uuid4

import psycopg
import pytest

from nima.analytics import citation_cohort as cohort_module
from nima.analytics import citation_readout as readout
from nima.analytics import citation_snapshot as snapshot
from nima.analytics import commands
from nima.analytics.citation_readout import prepare_citation_readout
from nima.analytics.result import ReadoutError
from nima.graph.pilot_archive import ArchiveBinding, PilotArchiveError
from nima.identity import AssessmentError
from nima.semantics.citations import CitationError
from nima.semantics.citations import evaluate as evaluate_citations
from nima.semantics.citations import reference_sql as citation_sql
from nima.sources.base import SourcePageError
from nima.sources.registry import adapter_from_run
from tests.test_analytics_snapshot import reader
from tests.test_citation_cohort import OBSERVED, add_run, seed, tamper


@pytest.mark.parametrize(
    ("statement", "reason"),
    [
        ("UPDATE nima.ingest_runs SET connector_version='unsupported'", "citation_contract"),
        ("UPDATE nima.ingest_runs SET normalizer_version='unsupported'", "citation_contract"),
        ("UPDATE nima.ingest_runs SET query='{}'::jsonb", "citation_contract"),
        ("UPDATE nima.ingest_runs SET next_page=0", "citation_evidence"),
        ("UPDATE nima.run_pages SET quarantined_count=1", "citation_evidence"),
        (
            """INSERT INTO nima.observations
        (run_id,page_number,record_index,source_id,normalizer_version,content_sha256)
        SELECT run_id,99,0,'kimdis:ORPHAN','kimdis-normalized-v1',repeat('0',64)
        FROM nima.ingest_runs WHERE connector_version='kimdis-contract-v1'""",
            "citation_evidence",
        ),
        (
            """INSERT INTO nima.quarantine SELECT run_id,99,0,'orphan'
        FROM nima.ingest_runs WHERE connector_version='kimdis-contract-v1'""",
            "citation_evidence",
        ),
    ],
)
def test_inconsistent_ledger_is_never_published(
    pg_dsn: str, tmp_path: Path, statement: str, reason: str
) -> None:
    request = seed(pg_dsn, tmp_path)
    tamper(pg_dsn, statement)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match=f"^{reason}$"):
        prepare_citation_readout(dsn, request)


def test_missing_run_and_wrong_source_group_are_contract_failures(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = seed(pg_dsn, tmp_path)
    missing = uuid4()
    missing_request = replace(
        request,
        kimdis_run_ids=(missing,),
        archive_bindings=tuple(
            sorted(
                (
                    replace(b, run_id=missing) if b.source == "kimdis" else b
                    for b in request.archive_bindings
                ),
                key=lambda b: b.run_id,
            )
        ),
    )
    swapped = replace(
        request,
        kimdis_run_ids=request.diavgeia_run_ids,
        diavgeia_run_ids=request.kimdis_run_ids,
        archive_bindings=tuple(
            replace(b, source="diavgeia" if b.source == "kimdis" else "kimdis")
            for b in request.archive_bindings
        ),
    )
    for selected in (missing_request, swapped):
        with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^citation_contract$"):
            prepare_citation_readout(dsn, selected)


def test_no_pages_and_unknown_fields_are_explicit(pg_dsn: str, tmp_path: Path) -> None:
    request = seed(pg_dsn, tmp_path, source_cites=False, kind=None)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_citation_readout(dsn, request)
    assert not result.edges
    entries = json.loads(body)["evidence"]
    by_source = {e["source"]: e for e in entries}
    assert by_source["kimdis"]["field_locations"]["diavgeiaADA"]["value_status"] == "not_reported"
    assert by_source["diavgeia"]["field_locations"]["decisionTypeId"]["value_status"] == "unknown"


def test_both_sources_without_pages_remain_partial(pg_dsn: str, tmp_path: Path) -> None:
    request = seed(pg_dsn, tmp_path, source_no_pages=True, no_pages=True)
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_citation_readout(dsn, request)
    assert result.status == "empty_capture"
    assert json.loads(body)["verified_pages"] == []
    assert json.loads(body)["quality"]["raw_bytes"] == "no_admitted_pages"
    assert all(c["source_attribution"]["statements"] == [] for c in json.loads(body)["captures"])
    assert json.loads(body)["quality"]["coverage"] == "partial_capture"


def test_award_profile_and_conflicting_targets_do_not_become_commitments(
    pg_dsn: str, tmp_path: Path
) -> None:
    request = seed(pg_dsn, tmp_path / "first")
    award_root = tmp_path / "award"
    award_run = add_run(pg_dsn, award_root, "diavgeia", kind="Δ.2.2")
    bindings = [b for b in request.archive_bindings if b.source == "kimdis"]
    bindings.append(ArchiveBinding("diavgeia", award_run, award_root))
    award_request = replace(
        request,
        diavgeia_run_ids=(award_run,),
        archive_bindings=tuple(sorted(bindings, key=lambda b: b.run_id)),
    )
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_citation_readout(dsn, award_request)
    assert result.edges[0].outcome == "target_type_mismatch"
    assert str(request.diavgeia_run_ids[0]) not in body.decode()
    conflict_root = tmp_path / "conflict"
    conflict = add_run(pg_dsn, conflict_root, "diavgeia-commitment", kind=None)
    conflicting = replace(
        request,
        diavgeia_run_ids=tuple(sorted((*request.diavgeia_run_ids, conflict))),
        archive_bindings=tuple(
            sorted(
                (*request.archive_bindings, ArchiveBinding("diavgeia", conflict, conflict_root)),
                key=lambda b: b.run_id,
            )
        ),
    )
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_citation_readout(dsn, conflicting)
    assert result.edges[0].outcome == "target_ambiguous"
    assert sum(e["selection"] == "ambiguous_candidate" for e in json.loads(body)["evidence"]) == 2


def test_later_content_and_cutoff_get_distinct_evidence_labels(pg_dsn: str, tmp_path: Path) -> None:
    request = seed(pg_dsn, tmp_path / "first")
    root = tmp_path / "later"
    run = add_run(pg_dsn, root, "kimdis", cites=False, observed=OBSERVED + timedelta(days=1))
    request = replace(
        request,
        kimdis_run_ids=tuple(sorted((*request.kimdis_run_ids, run))),
        archive_bindings=tuple(
            sorted(
                (*request.archive_bindings, ArchiveBinding("kimdis", run, root)),
                key=lambda b: b.run_id,
            )
        ),
    )
    with reader(pg_dsn) as (dsn, _):
        body, result = prepare_citation_readout(dsn, request)
        early, _ = prepare_citation_readout(
            dsn, replace(request, observation_cutoff=OBSERVED - timedelta(days=1))
        )
    assert not result.edges
    assert "earlier_content" in {e["selection"] for e in json.loads(body)["evidence"]}
    assert {e["selection"] for e in json.loads(early)["evidence"]} == {"after_cutoff"}


@pytest.mark.parametrize("fault", ["parser", "pointer", "adapter"])
def test_adapter_failures_and_false_locators_fail_closed(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    request = seed(pg_dsn, tmp_path)
    original = adapter_from_run

    def adapter(*args: Any, **kwargs: Any) -> Any:
        value = original(*args, **kwargs)
        normalize = value.normalize_page

        def parsed(*args: Any, **kwargs: Any) -> Any:
            if fault == "parser":
                raise SourcePageError("private detail")
            page = normalize(*args, **kwargs)
            return replace(page, records=(replace(page.records[0], evidence_pointer="/false"),))

        if fault == "adapter":
            monkeypatch.setattr(value, "name", "wrong")
        else:
            monkeypatch.setattr(value, "normalize_page", parsed)
        return value

    monkeypatch.setattr(snapshot, "adapter_from_run", adapter)
    reason = "citation_contract" if fault == "adapter" else "citation_evidence"
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match=f"^{reason}$"):
        prepare_citation_readout(dsn, request)


@pytest.mark.parametrize(
    "failure",
    ["archive_limit", "input_size", "snapshot_encoding", "output_size", "definition", "parity"],
)
def test_bounds_and_parity_refuse_publication(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    request = seed(pg_dsn, tmp_path)

    def limit(*args: Any, **kwargs: Any) -> Never:
        raise PilotArchiveError("pilot_limit")

    def encoding(*args: Any, **kwargs: Any) -> Never:
        raise AssessmentError("assessment_limit")

    original = evaluate_citations
    if failure == "archive_limit":
        monkeypatch.setattr(cohort_module, "recover", limit)
    elif failure == "input_size":
        monkeypatch.setattr(snapshot, "MAX_INPUT_BYTES", 1)

        def no_materialization(*args: Any, **kwargs: Any) -> Never:
            pytest.fail("Oversized SQL facts were materialized")

        monkeypatch.setattr(snapshot, "encode", no_materialization)
    elif failure == "snapshot_encoding":
        monkeypatch.setattr(snapshot, "encode", encoding)
    elif failure == "output_size":
        monkeypatch.setattr(readout, "MAX_OUTPUT_BYTES", 1)
    elif failure == "definition":
        sql = citation_sql()
        monkeypatch.setattr(readout, "reference_sql", lambda: sql + "\n-- changed\n")
    else:
        monkeypatch.setattr(
            readout, "evaluate", lambda *a, **kw: replace(original(*a, **kw), records=999)
        )
    reason = "citation_contract" if failure in {"definition", "parity"} else "citation_limit"
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match=f"^{reason}$"):
        prepare_citation_readout(dsn, request)


@pytest.mark.parametrize("reason", ["citation_input", "citation_limit"])
def test_model_rejections_are_private_safe(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    request = seed(pg_dsn, tmp_path)

    def failed(*args: Any, **kwargs: Any) -> Never:
        raise CitationError(reason)

    monkeypatch.setattr(readout, "evaluate", failed)
    expected = "citation_limit" if reason == "citation_limit" else "citation_contract"
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match=f"^{expected}$"):
        prepare_citation_readout(dsn, request)


def test_bad_programmatic_selection_never_opens_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from nima.analytics.citation_request import decode_citation_request
    from tests.test_citation_request import selection

    request = decode_citation_request(json.dumps(selection()).encode())

    def no_sql(*args: Any, **kwargs: Any) -> Never:
        pytest.fail("Invalid request reached SQL")

    monkeypatch.setattr(readout, "connected", no_sql)
    for invalid in [
        None,
        replace(request, archive_bindings=tuple(reversed(request.archive_bindings))),
        replace(request, observation_cutoff=cast(datetime, "bad")),
    ]:
        with pytest.raises(ReadoutError, match="^citation_input$"):
            prepare_citation_readout("", cast(Any, invalid))


@pytest.mark.parametrize(
    ("error", "reason", "code"),
    [
        (psycopg.OperationalError("private"), "citation_database", 1),
        (OSError("private"), "citation_output", 1),
        (ValueError("private"), "citation_input", 2),
        (KeyboardInterrupt(), "citation_output", 130),
    ],
)
def test_cli_uses_only_closed_failure_reasons(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: BaseException,
    reason: str,
    code: int,
) -> None:
    def failed(*args: Any, **kwargs: Any) -> Never:
        raise error

    monkeypatch.setattr(commands, "export_citation_readout", failed)
    monkeypatch.setenv("NIMA_DATABASE_URL", "private")
    assert (
        commands.run(["source-citations", "--request", "private", "--output-dir", "private"])
        == code
    )
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "failure": reason}


def test_unexpected_boundary_error_is_private_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    from nima.analytics.citation_request import decode_citation_request
    from tests.test_citation_request import selection

    request = decode_citation_request(json.dumps(selection()).encode())

    def failed(*args: Any, **kwargs: Any) -> Never:
        raise OSError("private detail")

    monkeypatch.setattr(readout, "connected", failed)
    with pytest.raises(ReadoutError, match="^citation_evidence$"):
        prepare_citation_readout("", request)


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (AssessmentError("assessment_limit"), "citation_limit"),
        (AssessmentError("output_path"), "citation_output"),
        (OSError("private"), "citation_output"),
    ],
)
def test_export_failure_cannot_report_a_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    from nima.analytics.citation_request import decode_citation_request
    from tests.test_citation_request import selection

    file = tmp_path / "request.json"
    file.write_text(json.dumps(selection()))
    file.chmod(0o600)
    request = decode_citation_request(file.read_bytes())
    result = evaluate_citations((), (), cutoff=request.observation_cutoff)
    body = b'{"quality":{"coverage":"partial_capture"}}'
    monkeypatch.setattr(readout, "prepare_citation_readout", lambda *a: (body, result))

    def failed(*args: Any, **kwargs: Any) -> Never:
        raise error

    monkeypatch.setattr(readout, "publish", failed)
    with pytest.raises(ReadoutError, match=f"^{reason}$"):
        readout.export_citation_readout("", file, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_export_missing_request_is_input_failure(tmp_path: Path) -> None:
    with pytest.raises(ReadoutError, match="^citation_input$"):
        readout.export_citation_readout("", tmp_path / "missing", tmp_path / "output")


@pytest.mark.parametrize(
    "statement",
    [
        """INSERT INTO nima.observations
    (run_id,page_number,record_index,source_id,normalizer_version,content_sha256)
    SELECT r.run_id,0,n,'kimdis:COUNT-'||n,'kimdis-normalized-v1',repeat('0',64)
    FROM nima.ingest_runs r CROSS JOIN generate_series(1,5000) n
    WHERE r.connector_version='kimdis-contract-v1'""",
        """INSERT INTO nima.quarantine
    SELECT r.run_id,0,n,'count' FROM nima.ingest_runs r CROSS JOIN generate_series(1,5001) n
    WHERE r.connector_version='kimdis-contract-v1'""",
        """INSERT INTO nima.run_pages
    (run_id,page_number,raw_sha256,observed_at,record_count,quarantined_count,source_ids)
    SELECT r.run_id,n,p.raw_sha256,p.observed_at,0,0,'{}'::text[]
    FROM nima.ingest_runs r JOIN nima.run_pages p USING(run_id)
    CROSS JOIN generate_series(1,500) n WHERE r.connector_version='kimdis-contract-v1'""",
    ],
)
def test_ledger_count_limits_precede_fetching_normalized_facts(
    pg_dsn: str, tmp_path: Path, statement: str
) -> None:
    from nima.analytics.snapshot import SnapshotError, connected

    request = seed(pg_dsn, tmp_path)
    tamper(pg_dsn, statement)
    with reader(pg_dsn) as (dsn, _), pytest.raises(SnapshotError, match="^citation_limit$"):
        connected(dsn, lambda c: snapshot.read_citation_snapshot(c, request))


def test_new_registry_connector_is_not_implicitly_admitted(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = seed(pg_dsn, tmp_path)
    tamper(pg_dsn, "UPDATE nima.ingest_runs SET connector_version='future'")

    def future(connector: str, payload: dict[str, object]) -> Any:
        known = "kimdis-contract-v1" if "dateFrom" in payload else "diavgeia-commitment-search-v1"
        adapter = adapter_from_run(known, payload)
        monkeypatch.setattr(adapter, "connector_version", connector)
        return adapter

    monkeypatch.setattr(snapshot, "adapter_from_run", future)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^citation_contract$"):
        prepare_citation_readout(dsn, request)


def test_quarantine_reasons_are_rederived_from_originals(pg_dsn: str, tmp_path: Path) -> None:
    request = seed(pg_dsn, tmp_path, quarantined=True)
    tamper(pg_dsn, "UPDATE nima.quarantine SET reason='altered'")
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^citation_evidence$"):
        prepare_citation_readout(dsn, request)
