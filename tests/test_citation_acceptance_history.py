"""Native source reconstruction, durable refusal and explicitly historical reuse."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from nima.analytics.citation_readout import prepare_citation_readout
from nima.contracts import acceptance as policy
from nima.contracts.acceptance_history import HistoryError
from nima.dataops import citation_acceptance_history as recorder
from nima.dataops.citation_acceptance import prepare_citation_acceptance
from nima.storage.acceptance_history import show_acceptance
from tests.test_acceptance_history_store import journal_role
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_acceptance import subject
from tests.test_citation_acceptance_native import request_file
from tests.test_citation_cohort import seed
from tests.test_graph_pilot_archive import state as archive_state


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("History recording must not request live sources")

    monkeypatch.setattr(httpx.Client, "send", forbidden)


@pytest.mark.parametrize("partial", [False, True])
def test_real_assessment_cached_reuse_and_new_id_reverify(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, partial: bool
) -> None:
    request = seed(pg_dsn, tmp_path / "raw", partial=partial)
    path = request_file(tmp_path, request)
    with (
        reader(pg_dsn) as (source, _),
        journal_role(pg_dsn) as writer,
        journal_role(pg_dsn, write=False) as inspector,
    ):
        parent, _ = prepare_citation_readout(source, request)
        report = subject(tmp_path / "reports", parent)
        before, originals = state(pg_dsn), archive_state(tmp_path)
        attempt = uuid4()
        calls = 0
        prepare = prepare_citation_acceptance

        def counted(*args: Any) -> Any:
            nonlocal calls
            calls += 1
            assert show_acceptance(inspector, attempt).execution_state == "pending"
            return prepare(*args)

        monkeypatch.setattr(recorder, "prepare_citation_acceptance", counted)
        result = recorder.record_citation_acceptance(source, writer, attempt, path, report)
        stored = show_acceptance(inspector, attempt)
        assert calls == 1
        assert result == stored.payload(reused=False)
        assert stored.outcome is not None and stored.body is not None
        assert stored.outcome.data_fitness == ("limited" if partial else "ready")
        assert stored.outcome.data_fitness == json.loads(stored.body)["assessment"]["status"]
        assert archive_state(tmp_path) == originals and state(pg_dsn) == before
        monkeypatch.setattr(recorder, "prepare_citation_acceptance", prepare)
        equal = recorder.record_citation_acceptance(source, writer, uuid4(), path, report)
        assert equal["outcome_sha256"] == result["outcome_sha256"]
        next((tmp_path / "raw").rglob("*.body")).unlink()

        def forbidden(*args: Any) -> Any:
            pytest.fail("Historical reuse consulted current policy or source")

        with monkeypatch.context() as patch:
            patch.setattr(recorder, "current_intent", forbidden)
            patch.setattr(recorder, "prepare_citation_acceptance", forbidden)
            reused = recorder.record_citation_acceptance(source, writer, attempt, path, report)
            assert reused == stored.payload()
            assert reused["verification_scope"] == "recorded_acceptance_history_only"
        fresh = recorder.record_citation_acceptance(source, writer, uuid4(), path, report)
        assert fresh["execution_state"] == "refused"
        terminal = fresh["outcome"]
        assert isinstance(terminal, dict) and terminal["data_fitness"] is None
        assert state(pg_dsn) == before


def test_invalid_input_has_no_attempt_and_unknown_failure_stays_pending(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = seed(pg_dsn, tmp_path / "raw")
    path = request_file(tmp_path, request)
    attempt = uuid4()
    with journal_role(pg_dsn) as writer, journal_role(pg_dsn, write=False) as inspector:
        with pytest.raises(HistoryError, match="acceptance_history_configuration"):
            recorder.record_citation_acceptance("source", writer, attempt, path, Path("bad"))
        with pytest.raises(HistoryError, match="acceptance_history_unknown"):
            show_acceptance(inspector, attempt)

        def failed(*args: Any) -> Any:
            raise RuntimeError("PRIVATE DSN")

        monkeypatch.setattr(recorder, "prepare_citation_acceptance", failed)
        with pytest.raises(HistoryError, match="^acceptance_history_integrity$"):
            recorder.record_citation_acceptance(
                "source", writer, attempt, path, tmp_path / ("a" * 64 + ".json")
            )
        assert show_acceptance(inspector, attempt).execution_state == "pending"


@pytest.mark.parametrize(
    "fault",
    [
        "request",
        "policy",
        "conflict_request",
        "conflict_report",
        "unsupported",
        "interrupt",
        "prepared_type",
        "prepared_parent",
        "prepared_assessment",
        "journal_write",
    ],
)
def test_recording_failure_never_invents_a_fitness(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import psycopg

    from nima.contracts.acceptance_history import Intent
    from nima.dataops.acceptance_files import AcceptanceError
    from nima.storage.acceptance_history import Journal, JournalSession

    request = seed(pg_dsn, tmp_path / "raw")
    path = request_file(tmp_path, request)
    attempt = uuid4()
    with (
        reader(pg_dsn) as (source, _),
        journal_role(pg_dsn) as writer,
        journal_role(pg_dsn, write=False) as inspector,
    ):
        parent, _ = prepare_citation_readout(source, request)
        report = subject(tmp_path / "reports", parent)
        prepared = prepare_citation_acceptance(source, request, report)
        if fault == "request":
            path.write_bytes(b"{}")
        elif fault == "policy":
            monkeypatch.setattr(policy, "definition", lambda: {})
        elif fault.startswith("conflict") or fault == "unsupported":
            intent = Intent(request.request_sha256, report.stem)
            if fault == "conflict_request":
                intent = replace(intent, request_sha256="f" * 64)
            if fault == "conflict_report":
                intent = replace(intent, subject_sha256="f" * 64)
            if fault == "unsupported":
                intent = replace(intent, policy_version="2.0.0")
            with Journal(writer, attempt).session() as session:
                session.register(intent)
        elif fault == "journal_write":

            def fail(*args: Any) -> Any:
                raise psycopg.OperationalError("PRIVATE")

            monkeypatch.setattr(JournalSession, "finish", fail)
        else:
            if fault == "interrupt":

                def interrupted(*args: Any) -> Any:
                    raise AcceptanceError("acceptance_interrupted")

                monkeypatch.setattr(recorder, "prepare_citation_acceptance", interrupted)
            else:
                malformed: Any = (
                    None
                    if fault == "prepared_type"
                    else replace(prepared, subject_sha256="f" * 64)
                    if fault == "prepared_parent"
                    else replace(
                        prepared, assessment=replace(prepared.assessment, status="blocked")
                    )
                )
                monkeypatch.setattr(recorder, "prepare_citation_acceptance", lambda *_: malformed)
        if fault == "unsupported":

            def forbidden(*args: Any) -> Any:
                pytest.fail("Unsupported pending profile executed")

            monkeypatch.setattr(recorder, "prepare_citation_acceptance", forbidden)
            result = recorder.record_citation_acceptance(source, writer, attempt, path, report)
            outcome = result["outcome"]
            assert isinstance(outcome, dict) and outcome["refusal_code"] == "acceptance_contract"
            assert show_acceptance(inspector, attempt).body is None
        else:
            expected = KeyboardInterrupt if fault == "interrupt" else HistoryError
            with pytest.raises(expected):
                recorder.record_citation_acceptance(source, writer, attempt, path, report)
            if fault in {"request", "policy"}:
                with pytest.raises(HistoryError, match="acceptance_history_unknown"):
                    show_acceptance(inspector, attempt)
            else:
                assert show_acceptance(inspector, attempt).execution_state == "pending"


@pytest.mark.parametrize("code", ["input", "limit", "evidence", "database", "contract", "output"])
def test_closed_preparer_refusal_is_recorded_without_sidecar(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    from nima.dataops.acceptance_files import AcceptanceError

    request = seed(pg_dsn, tmp_path / "raw")
    path = request_file(tmp_path, request)

    def refused(*args: Any) -> Any:
        raise AcceptanceError("acceptance_" + code)

    monkeypatch.setattr(recorder, "prepare_citation_acceptance", refused)
    with journal_role(pg_dsn) as writer, journal_role(pg_dsn, write=False) as inspector:
        attempt = uuid4()
        result = recorder.record_citation_acceptance(
            "source", writer, attempt, path, tmp_path / ("a" * 64 + ".json")
        )
        row = show_acceptance(inspector, attempt)
        assert result["execution_state"] == "refused" and row.body is None
        assert row.outcome is not None
        assert row.outcome.data_fitness is None and row.outcome.acceptance_sha256 is None
        assert row.outcome.refusal_code == "acceptance_" + code


@pytest.mark.parametrize("case,decision", [("blocked", "blocked"), ("definition", "not_assessed")])
def test_actual_negative_policy_results_are_assessments_not_refusals(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    decision: str,
) -> None:
    # Controlled producer frames exercise actual policy decisions; they are not
    # claimed as a real-source or real-cohort assessment.
    from nima.analytics.metric_readout import definition_hash
    from nima.dataops import citation_acceptance as adapter
    from nima.identity.artifacts import encode
    from nima.storage.postgres import migrate
    from tests.citation_acceptance_samples import producer
    from tests.test_source_citations import contract
    from tests.test_source_citations import decision as target

    request, frame, result = producer((contract(1),), (target(),))
    model = frame["model"]
    assert isinstance(model, dict)
    if case == "blocked":
        result = replace(result, records=3)
        model["result"] = result.payload()
    else:
        definition = model["definition"]
        assert isinstance(definition, dict)
        definition["status"] = "reviewed"
        model["definition_sha256"] = definition_hash(definition)
    body = encode(frame)
    report = subject(tmp_path / "reports", body)
    path = request_file(tmp_path, request)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (body, result))
    migrate(pg_dsn)
    with journal_role(pg_dsn) as writer, journal_role(pg_dsn, write=False) as inspector:
        attempt = uuid4()
        recorder.record_citation_acceptance("controlled", writer, attempt, path, report)
        record = show_acceptance(inspector, attempt)
        assert record.execution_state == "assessed" and record.outcome is not None
        assert record.outcome.data_fitness == decision and record.body is not None


def test_native_cli_record_and_inspection_separate_source_and_journal(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nima.dataops.cli import run

    request = seed(pg_dsn, tmp_path / "raw")
    path = request_file(tmp_path, request)
    with (
        reader(pg_dsn) as (source, _),
        journal_role(pg_dsn) as writer,
        journal_role(pg_dsn, write=False) as inspector,
    ):
        body, _ = prepare_citation_readout(source, request)
        report = subject(tmp_path / "reports", body)
        attempt = uuid4()
        monkeypatch.setenv("NIMA_DATABASE_URL", source)
        monkeypatch.setenv("NIMA_ACCEPTANCE_DATABASE_URL", writer)
        args = [
            "record-citation-acceptance",
            "--attempt-id",
            str(attempt),
            "--request",
            str(path),
            "--report",
            str(report),
        ]
        assert run(args) == 0
        output = capsys.readouterr()
        first = json.loads(output.out)
        assert first["execution_state"] == "assessed" and len(output.out.encode()) <= 16384
        assert str(tmp_path) not in output.out + output.err
        report.unlink()
        assert run(args) == 0
        assert json.loads(capsys.readouterr().out)["reused"] is True
        negative = uuid4()
        args[2] = str(negative)
        assert run(args) == 3
        assert json.loads(capsys.readouterr().out)["execution_state"] == "refused"
        monkeypatch.delenv("NIMA_DATABASE_URL")
        monkeypatch.setenv("NIMA_ACCEPTANCE_DATABASE_URL", inspector)
        assert run(["acceptance-show", "--attempt-id", str(negative)]) == 0
        assert json.loads(capsys.readouterr().out)["outcome"]["data_fitness"] is None
        assert run(["acceptance-show", "--attempt-id", str(attempt)]) == 0
        inspected = json.loads(capsys.readouterr().out)
        assert inspected == {
            **first,
            "reused": True,
            "verification_scope": "recorded_acceptance_history_only",
        }
