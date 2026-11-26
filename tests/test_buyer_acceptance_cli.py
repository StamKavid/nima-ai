"""U3 uses the same fixed acceptance terminal contract, including negative fitness."""

import json
from pathlib import Path

import pytest

from nima.dataops import acceptance_cli, cli
from nima.dataops.buyer_acceptance import (
    BuyerAcceptanceError,
    BuyerAcceptanceExport,
)


@pytest.mark.parametrize(
    "decision,exit_code", [("ready", 0), ("limited", 0), ("blocked", 3), ("not_assessed", 3)]
)
def test_cli_route_private_arguments_and_policy_decisions(
    decision: str,
    exit_code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "PRIVATE_DSN")

    def exported(dsn: str, request: Path, report: Path, output: Path) -> BuyerAcceptanceExport:
        assert (dsn, request, report, output) == (
            "PRIVATE_DSN",
            Path("/PRIVATE/request"),
            Path("/PRIVATE/report"),
            Path("/PRIVATE/output"),
        )
        return BuyerAcceptanceExport("a" * 64, "b" * 64, decision, "c" * 64)

    monkeypatch.setattr(acceptance_cli, "export_buyer_acceptance", exported)
    assert (
        cli.run(
            [
                "assess-buyer",
                "--request",
                "/PRIVATE/request",
                "--report",
                "/PRIVATE/report",
                "--output-dir",
                "/PRIVATE/output",
            ]
        )
        == exit_code
    )
    out = capsys.readouterr()
    assert json.loads(out.out)["decision"] == decision
    assert "PRIVATE" not in out.out + out.err
    assert [json.loads(s)["event"] for s in out.err.splitlines()] == ["started", "completed"]


@pytest.mark.parametrize(
    "reason,code",
    [
        ("acceptance_input", 2),
        ("acceptance_evidence", 1),
        ("acceptance_database", 1),
        ("acceptance_contract", 1),
        ("acceptance_limit", 1),
        ("acceptance_output", 1),
        ("interrupt", 130),
    ],
)
def test_u3_terminal_failure_is_closed(
    reason: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object) -> BuyerAcceptanceExport:
        if reason == "interrupt":
            raise KeyboardInterrupt
        raise BuyerAcceptanceError(reason)

    monkeypatch.setattr(acceptance_cli, "export_buyer_acceptance", fail)
    assert (
        cli.run(
            [
                "assess-buyer",
                "--request",
                "/PRIVATE/request",
                "--report",
                "/PRIVATE/report",
                "--output-dir",
                "/PRIVATE/output",
            ]
        )
        == code
    )
    out = capsys.readouterr()
    assert json.loads(out.out)["status"] == "failed"
    assert "PRIVATE" not in out.out + out.err


def test_help_lists_all_consumers(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run(["--help"]) == 0
    assert "assess-buyer" in capsys.readouterr().out
    assert acceptance_cli.run(["assess-buyer", "--help"]) == 0
    assert "--report" in capsys.readouterr().out


@pytest.mark.parametrize("decision", ["blocked", "not_assessed"])
def test_actual_sidecar_publication_retains_negative_fitness(
    decision: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dataclasses import replace

    from nima.analytics.metric_readout import cohort_hash
    from nima.dataops import buyer_acceptance as adapter
    from nima.identity.artifacts import encode
    from nima.semantics.buyer_concentration import definition
    from tests.buyer_acceptance_samples import observation, producer, request_file
    from tests.test_citation_acceptance import subject

    meta = definition()
    if decision == "not_assessed":
        meta["status"] = "reviewed"
    request, fresh = producer((observation(),), definition=meta)
    if decision == "blocked":
        # Controlled producer frame only: the native verifier refuses real quarantine.
        cohort = json.loads(fresh.cohort_json)
        body = json.loads(fresh.body)
        cohort["runs"][0]["quarantine_count"] = 1
        cohort["pages"][0]["record_count"] = 2
        body["verified_pages"][0]["record_count"] = 2
        body["cohort_sha256"] = cohort_hash(cohort)
        fresh = replace(
            fresh,
            body=encode(body),
            cohort_json=encode(cohort).decode(),
            pages=(replace(fresh.pages[0], record_count=2),),
        )
    monkeypatch.setattr(adapter, "prepare_buyer_result", lambda *_: fresh)
    monkeypatch.setenv("NIMA_DATABASE_URL", "fixture")
    selection = request_file(request, tmp_path / "request.json")
    report = subject(tmp_path / "reports", fresh.body)
    output = tmp_path / "output"
    result = adapter.export_buyer_acceptance("fixture", selection, report, output)
    assert result.decision == decision
    saved = json.loads((output / (result.artifact_sha256 + ".json")).read_bytes())
    assert saved["assessment"]["status"] == decision
    if decision == "blocked":
        assert {c["name"]: c["value"] for c in saved["assessment"]["counts"]}["quarantined"] == 1
    assert (
        cli.run(
            [
                "assess-buyer",
                "--request",
                str(selection),
                "--report",
                str(report),
                "--output-dir",
                str(output),
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().out)["decision"] == decision
