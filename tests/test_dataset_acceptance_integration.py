"""Test-only bridges from actual verified readers; no product adapter or attestation."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from nima.analytics.citation_readout import prepare_citation_readout
from nima.analytics.citation_request import CitationRequest
from nima.analytics.export import prepare_readout
from nima.analytics.result import ReadoutError
from nima.contracts import acceptance as policy
from tests.test_analytics_reconcile import seed_cohort
from tests.test_analytics_snapshot import reader, state
from tests.test_citation_cohort import seed, tamper
from tests.test_dataset_acceptance import checked, counted, facts
from tests.test_graph_pilot_archive import state as archive_state


def verified_citation_facts(dsn: str, request: CitationRequest) -> policy.DatasetFacts:
    # Input is a request, never artifact JSON with a self-declared success flag.
    body, result = prepare_citation_readout(dsn, request)
    data = json.loads(body)
    captures, pages = data["captures"], data["verified_pages"]
    selected = [s.versions[0] for s in result.sources if len(s.versions) == 1]
    base = facts("citations")
    data_facts = replace(
        base,
        binding=policy.DatasetBinding(
            "citations",
            request.request_sha256,
            data["cohort_sha256"],
            request.observation_cutoff,
            tuple(
                policy.RunBinding(
                    c["source"], c["run_id"], c["connector_version"], c["normalizer_version"]
                )
                for c in captures
            ),
            data["model"]["definition_sha256"],
            data["model"]["definition"]["sql_sha256"],
        ),
        provider_status=result.status,
    )
    if data["quality"]["coverage"] != "selected_complete_captures":
        data_facts = checked(data_facts, "capture_completeness", "failed", "incomplete_capture")
    for name, grain, value in [
        ("observations", "observation", len(data["evidence"])),
        ("pages", "page", len(pages)),
        ("page_records", "reported_record", sum(p["record_count"] for p in pages)),
        ("quarantined", "quarantined_record", sum(c["quarantined_count"] for c in captures)),
        ("selected_records", "source_record", result.records - len(result.source_ambiguous_ids)),
        ("ambiguous_records", "source_record", len(result.source_ambiguous_ids)),
        ("unknown_reference_lists", "source_record", len(result.unknown_reference_ids)),
        ("unresolved_citations", "citation", result.outcome_counts["unresolved"]),
        ("ambiguous_targets", "citation", result.outcome_counts["target_ambiguous"]),
        ("unknown_target_types", "citation", result.outcome_counts["target_type_unknown"]),
        ("mismatched_target_types", "citation", result.outcome_counts["target_type_mismatch"]),
        ("unknown_cancellations", "source_record", sum(v.cancelled is None for v in selected)),
        ("cancelled_records", "source_record", sum(v.cancelled is True for v in selected)),
        (
            "revoked_targets",
            "citation",
            sum(
                len(e.target_versions) == 1 and e.target_versions[0].decision_status == "REVOKED"
                for e in result.edges
            ),
        ),
    ]:
        data_facts = counted(data_facts, name, grain, value)
    return data_facts


@pytest.mark.parametrize(
    "options,expected",
    [
        ({}, "ready"),
        ({"partial": True}, "limited"),
        ({"quarantined": True}, "limited"),
        ({"no_pages": True}, "limited"),
        ({"kind": None}, "limited"),
        ({"kind": "Δ.2.2"}, "limited"),
        ({"source_cites": False}, "ready"),
        ({"empty": True}, "limited"),
        ({"source_no_pages": True, "no_pages": True}, "limited"),
    ],
)
def test_restricted_two_source_reader_supplies_verified_policy_facts_without_writes(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    options: dict[str, Any],
    expected: str,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Acceptance must make no source request")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    request = seed(pg_dsn, tmp_path, **options)
    sql_before, files_before = state(pg_dsn), archive_state(tmp_path)
    with reader(pg_dsn) as (dsn, _):
        data = verified_citation_facts(dsn, request)
        assessment = policy.evaluate(data)
        assert policy.evaluate(verified_citation_facts(dsn, request)) == assessment
    assert assessment.status == expected
    assert assessment.policy_version == "1.0.0"
    assert assessment.definition_sha256 == data.binding.definition_sha256
    if options.get("quarantined"):
        assert (
            next(c for c in assessment.checks if c.check_id == "capture_completeness").reason
            == "quarantined_records"
        )
    assert state(pg_dsn) == sql_before
    assert archive_state(tmp_path) == files_before


@pytest.mark.parametrize("fault", ["raw", "missing", "sql", "membership", "omitted"])
def test_source_disagreement_never_reaches_a_successful_policy_evaluation(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    request = seed(pg_dsn, tmp_path)
    target = next((tmp_path / "diavgeia" / "objects").rglob("*.body"))
    if fault == "raw":
        target.write_bytes(b"CORRUPT")
    elif fault == "missing":
        target.unlink()
    else:
        statement = {
            "sql": """UPDATE nima.record_versions
                      SET normalized=jsonb_set(normalized,'{status}','"REVOKED"')
                      WHERE source_id='diavgeia:ADA-1'""",
            "membership": """UPDATE nima.observations SET record_index=9
                             WHERE source_id='diavgeia:ADA-1'""",
            "omitted": "DELETE FROM nima.observations WHERE source_id='diavgeia:ADA-1'",
        }[fault]
        # Only the owned disposable fixture bypasses immutability to inject damage.
        tamper(pg_dsn, statement)
    sql_before, files_before = state(pg_dsn), archive_state(tmp_path)
    calls = 0

    def no_assessment(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        pytest.fail("Failed reconstruction cannot produce successful policy facts")

    monkeypatch.setattr(policy, "evaluate", no_assessment)
    with reader(pg_dsn) as (dsn, _), pytest.raises(ReadoutError, match="^citation_evidence$"):
        policy.evaluate(verified_citation_facts(dsn, request))
    assert calls == 0
    assert state(pg_dsn) == sql_before
    assert archive_state(tmp_path) == files_before


def test_existing_u1_preparation_preserves_numeric_rules_and_draft_definition(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    request = seed_cohort(pg_dsn, tmp_path)
    before, originals = state(pg_dsn), archive_state(tmp_path)
    with reader(pg_dsn) as (dsn, _):
        prepared = prepare_readout(dsn, request)
        assert prepare_readout(dsn, request).body == prepared.body
    document = json.loads(prepared.snapshot.document_json)
    artifact = json.loads(prepared.body)
    metric = prepared.snapshot.metric
    base = facts()
    data = replace(
        base,
        binding=policy.DatasetBinding(
            "U1",
            request.request_sha256,
            prepared.snapshot.input_sha256,
            request.observation_cutoff,
            tuple(
                policy.RunBinding(
                    "kimdis", r["run_id"], r["connector_version"], r["normalizer_version"]
                )
                for r in document["runs"]
            ),
            artifact["metric"]["definition_sha256"],
            artifact["metric"]["definition"]["sql_sha256"],
        ),
        provider_status=metric.status,
    )
    for name, grain, value in [
        ("observations", "observation", len(prepared.snapshot.observations)),
        ("pages", "page", len(document["pages"])),
        ("page_records", "reported_record", sum(p["record_count"] for p in document["pages"])),
        (
            "selected_records",
            "source_record",
            len(metric.records) - len(metric.ambiguous_source_ids),
        ),
        ("ambiguous_records", "source_record", len(metric.ambiguous_source_ids)),
        ("unknown_suppliers", "source_record", len(metric.unknown_supplier_source_ids)),
        ("unknown_cancellations", "source_record", metric.unknown_cancellation_count),
        ("cancelled_records", "source_record", metric.cancelled_count),
        ("unassigned_buyers", "source_record", len(metric.unassigned_source_ids)),
        ("invalid_supplier_occurrences", "supplier_occurrence", metric.invalid_supplier_count),
    ]:
        data = counted(data, name, grain, value)
    result = policy.evaluate(data)
    assert metric.total == 5
    assert result.status == "limited"
    assert result.provider_status == metric.status
    assert artifact["metric"]["definition"]["status"] == "draft"
    assert state(pg_dsn) == before
    assert archive_state(tmp_path) == originals
