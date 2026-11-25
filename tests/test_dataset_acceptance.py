"""Use-specific fitness of verified internal facts; never publisher certification."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from nima.contracts.acceptance import (
    AcceptanceError,
    CheckResult,
    Count,
    DatasetBinding,
    DatasetFacts,
    RunBinding,
    definition,
    definition_sha256,
    evaluate,
)

CHECKS = (
    "bindings",
    "evidence",
    "keys",
    "membership",
    "page_accounting",
    "capture_completeness",
    "selection",
    "eligibility",
    "comparability",
)
RUN = "00000000-0000-4000-8000-000000000001"
OTHER_RUN = "00000000-0000-4000-8000-000000000002"


def facts(use: str = "U1") -> DatasetFacts:
    profile = cast(dict[str, dict[str, str]], definition()["uses"])[use]
    runs: tuple[RunBinding, ...] = (
        RunBinding("kimdis", RUN, "kimdis-contract-v1", "kimdis-normalized-v1"),
    )
    if use == "citations":
        runs += (
            RunBinding(
                "diavgeia", OTHER_RUN, "diavgeia-commitment-search-v1", "diavgeia-commitment-v1"
            ),
        )
    return DatasetFacts(
        DatasetBinding(
            use,
            "a" * 64,
            "b" * 64,
            datetime(2026, 1, 1, tzinfo=UTC),
            runs,
            profile["definition_sha256"],
            profile["sql_sha256"],
        ),
        "no_observed_citations"
        if use == "citations"
        else "no_observed_change"
        if use == "U4"
        else "empty_capture",
        tuple(CheckResult(c, "passed", "ok") for c in CHECKS),
        (
            Count("observations", "observation", 0),
            Count("pages", "page", 1),
            Count("page_records", "reported_record", 0),
            Count("quarantined", "quarantined_record", 0),
            Count("selected_records", "source_record", 0),
            Count("ambiguous_records", "source_record", 0),
        ),
    )


def checked(data: DatasetFacts, check: str, status: str, reason: str) -> DatasetFacts:
    return replace(
        data,
        checks=tuple(
            CheckResult(check, status, reason) if c.check_id == check else c for c in data.checks
        ),
    )


def counted(data: DatasetFacts, name: str, grain: str, value: int) -> DatasetFacts:
    return replace(
        data, counts=tuple(c for c in data.counts if c.name != name) + (Count(name, grain, value),)
    )


@pytest.mark.parametrize("use", ["U1", "U2", "U3", "U4", "citations"])
def test_complete_empty_is_ready_for_data_only_with_status_preserved(use: str) -> None:
    data = facts(use)
    result = evaluate(data)
    assert result.status == "ready"
    assert result.provider_status == data.provider_status
    assert result.policy_sha256 == definition_sha256()
    assert result.amount_eligibility == "not_applicable"
    assert result.limitations == ()
    assert len(result.checks) == 9
    with pytest.raises(FrozenInstanceError):
        result.status = "certified"  # type: ignore[misc]


@pytest.mark.parametrize("use", ["U1", "U2", "U3", "U4", "citations"])
def test_honest_partial_capture_is_limited_only_for_citation_inspection(use: str) -> None:
    data = checked(facts(use), "capture_completeness", "failed", "incomplete_capture")
    result = evaluate(data)
    assert result.status == ("limited" if use == "citations" else "blocked")
    assert result.limitations == (("partial_capture",) if use == "citations" else ())


@pytest.mark.parametrize("check", CHECKS[:-1])
def test_missing_required_proof_never_passes(check: str) -> None:
    data = facts()
    result = evaluate(replace(data, checks=tuple(c for c in data.checks if c.check_id != check)))
    assert result.status == "not_assessed"
    missing = next(c for c in result.checks if c.check_id == check)
    assert (missing.status, missing.reason) == ("not_assessed", "not_checked")


def test_failure_outranks_missing_evidence_and_keeps_all_checks() -> None:
    data = checked(facts(), "evidence", "not_assessed", "proof_unavailable")
    data = checked(data, "keys", "failed", "duplicate_identity")
    result = evaluate(data)
    assert result.status == "blocked"
    assert [(c.status, c.reason) for c in result.checks if c.check_id in {"evidence", "keys"}] == [
        ("not_assessed", "proof_unavailable"),
        ("failed", "duplicate_identity"),
    ]


def test_unsupported_definition_does_not_erase_a_known_binding_disagreement() -> None:
    data = checked(facts(), "bindings", "failed", "bindings_disagreement")
    result = evaluate(replace(data, binding=replace(data.binding, definition_sha256="c" * 64)))
    assert result.status == "blocked"
    assert result.checks[0] == CheckResult("bindings", "failed", "bindings_disagreement")


def test_records_without_an_admitted_page_are_a_membership_failure() -> None:
    data = counted(facts(), "pages", "page", 0)
    data = counted(data, "observations", "observation", 1)
    data = counted(data, "page_records", "reported_record", 1)
    result = evaluate(data)
    assert result.status == "blocked"
    assert (
        next(c for c in result.checks if c.check_id == "membership").reason
        == "membership_disagreement"
    )


@pytest.mark.parametrize(
    "use,size,expected",
    [("U1", 10, "ready"), ("citations", 10, "ready"), ("citations", 11, "input_error")],
)
def test_run_profile_bounds_are_the_existing_use_bounds(use: str, size: int, expected: str) -> None:
    data = facts(use)
    runs = data.binding.runs + tuple(
        replace(data.binding.runs[0], run_id=f"00000000-0000-4000-8000-{n:012x}")
        for n in range(3, size + 3 - len(data.binding.runs))
    )
    assert len(runs) == size
    changed = replace(data, binding=replace(data.binding, runs=runs))
    if expected == "input_error":
        with pytest.raises(AcceptanceError, match="^acceptance_input$"):
            evaluate(changed)
    else:
        assert evaluate(changed).status == expected


def test_unknown_capture_completeness_limits_inspection_without_becoming_a_pass() -> None:
    data = checked(facts("citations"), "capture_completeness", "not_assessed", "not_checked")
    result = evaluate(data)
    assert result.status == "limited"
    assert result.limitations == ("capture_completeness_unknown",)


@pytest.mark.parametrize(
    "check,reason",
    [
        ("bindings", "bindings_disagreement"),
        ("evidence", "evidence_disagreement"),
        ("keys", "inconsistent_version"),
        ("membership", "membership_disagreement"),
        ("page_accounting", "page_accounting_disagreement"),
        ("selection", "selection_disagreement"),
        ("eligibility", "eligibility_disagreement"),
    ],
)
@pytest.mark.parametrize("use", ["U1", "citations"])
def test_known_integrity_failures_block_even_citation_inspection(
    use: str, check: str, reason: str
) -> None:
    assert evaluate(checked(facts(use), check, "failed", reason)).status == "blocked"


def test_citation_inspection_needs_both_source_namespaces() -> None:
    data = facts("citations")
    assert (
        evaluate(replace(data, binding=replace(data.binding, runs=data.binding.runs[:1]))).status
        == "not_assessed"
    )


@pytest.mark.parametrize(
    "connector,normalizer",
    [
        ("diavgeia-search-v1", "diavgeia-decision-v1"),
        ("diavgeia-commitment-search-v1", "diavgeia-commitment-v1"),
    ],
)
def test_both_existing_diavgeia_profiles_remain_supported(connector: str, normalizer: str) -> None:
    data = facts("citations")
    source, target = data.binding.runs
    target = replace(target, connector_version=connector, normalizer_version=normalizer)
    assert (
        evaluate(replace(data, binding=replace(data.binding, runs=(source, target)))).status
        == "ready"
    )


def test_unknown_date_limits_only_u2_and_ignores_overlapping_cells() -> None:
    for use in ["U1", "U2", "U3"]:
        data = counted(facts(use), "observations", "observation", 2)
        data = counted(data, "page_records", "reported_record", 2)
        data = counted(data, "selected_records", "source_record", 2)
        data = counted(data, "unknown_dates", "source_record", 1)
        data = counted(data, "cpv_cells", "cell", 9)
        result = evaluate(data)
        assert result.status == ("limited" if use == "U2" else "ready")
        assert result.limitations == (("unknown_dates",) if use == "U2" else ())


def test_untrusted_json_is_not_a_verified_internal_fact() -> None:
    with pytest.raises(AcceptanceError, match="^acceptance_input$"):
        evaluate({"verified": True, "checks": "passed"})  # type: ignore[arg-type]


def test_policy_definition_cannot_be_changed_by_its_caller() -> None:
    original = definition_sha256()
    metadata = definition()
    cast(dict[str, str], metadata["count_grains"])["observations"] = "euros"
    assert definition_sha256() == original
    assert evaluate(facts()).policy_sha256 == original


def test_v1_policy_identity_and_the_exact_reviewed_rule_table_are_stable() -> None:
    result = evaluate(facts())
    assert result.policy_id == definition()["id"] == "nima.dataset-acceptance"
    assert result.policy_version == definition()["version"] == "1.0.0"
    assert definition_sha256() == "06975d8b0ae0ee3eca0368c39a9008c6a75ff439c3c01eef4e3549b7926bafa6"


@pytest.mark.parametrize("use", ["U1", "U2", "U3", "U4", "citations"])
def test_quarantine_counts_cannot_be_overridden_by_a_success_flag(use: str) -> None:
    data = counted(facts(use), "quarantined", "quarantined_record", 1)
    data = counted(data, "page_records", "reported_record", 1)
    result = evaluate(data)
    assert result.status == ("limited" if use == "citations" else "blocked")
    assert (
        next(c for c in result.checks if c.check_id == "capture_completeness").reason
        == "quarantined_records"
    )


@pytest.mark.parametrize("use", ["U1", "citations"])
def test_zero_pages_is_not_complete_empty(use: str) -> None:
    result = evaluate(counted(facts(use), "pages", "page", 0))
    assert result.status == ("limited" if use == "citations" else "blocked")


def test_incomparable_provider_result_cannot_be_ready_even_with_all_pass_flags() -> None:
    assert evaluate(replace(facts("U4"), provider_status="incomparable")).status == "blocked"


@pytest.mark.parametrize(
    "reason", ["no_runs", "not_later", "quarantined_records", "query_mismatch", "run_incomplete"]
)
def test_u4_abstention_reasons_block_even_without_a_verified_cohort(reason: str) -> None:
    data = facts("U4")
    data = replace(
        data, binding=replace(data.binding, cohort_sha256=None), provider_status="incomparable"
    )
    data = checked(data, "comparability", "failed", reason)
    result = evaluate(data)
    assert result.status == "blocked"
    assert result.provider_status == "incomparable"
    assert next(c for c in result.checks if c.check_id == "comparability").reason == reason


def test_a_provider_status_unknown_to_the_policy_is_not_echoed_or_accepted() -> None:
    result = evaluate(replace(facts(), provider_status="UNTRUSTED_SOURCE_VALUE"))
    assert result.status == "not_assessed"
    assert result.provider_status == "not_assessed"
    assert "UNTRUSTED" not in repr(result)


def test_closed_profiles_match_the_actual_five_providers_without_promoting_them() -> None:
    from nima.analytics.metric_readout import definition_hash
    from nima.semantics.catalogue import entries
    from nima.semantics.citations import definition as citation_definition

    uses = cast(dict[str, dict[str, str]], definition()["uses"])
    for e in entries():
        assert uses[e.scenario] == {
            "metric_id": e.metric_id,
            "definition_sha256": e.definition_sha256,
            "sql_sha256": e.sql_sha256,
        }
        assert e.status == "draft"
    p = citation_definition()
    assert uses["citations"] == {
        "metric_id": p["model"],
        "definition_sha256": definition_hash(p),
        "sql_sha256": p["sql_sha256"],
    }
    assert p["status"] == "draft"


def test_input_and_output_identity_ignore_only_ordering() -> None:
    data = facts("citations")
    changed = replace(
        data,
        binding=replace(data.binding, runs=tuple(reversed(data.binding.runs))),
        checks=tuple(reversed(data.checks)),
        counts=tuple(reversed(data.counts)),
    )
    assert evaluate(changed) == evaluate(data)
    assert (
        evaluate(
            replace(
                data,
                binding=replace(data.binding, cutoff=data.binding.cutoff + timedelta(seconds=1)),
            )
        ).facts_sha256
        != evaluate(data).facts_sha256
    )
    assert (
        evaluate(replace(data, binding=replace(data.binding, request_sha256="c" * 64))).facts_sha256
        != evaluate(data).facts_sha256
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("definition_sha256", "c" * 64),
        ("sql_sha256", "c" * 64),
        ("cohort_sha256", None),
        ("runs", ()),
    ],
)
def test_missing_or_unsupported_binding_never_passes(field: str, value: Any) -> None:
    data = facts()
    assert (
        evaluate(replace(data, binding=replace(data.binding, **{field: value}))).status
        == "not_assessed"
    )


def test_unsupported_use_does_not_guess_a_policy_or_echo_the_use() -> None:
    data = facts()
    result = evaluate(replace(data, binding=replace(data.binding, use="FUTURE_SOURCE_LABEL")))
    assert result.status == "not_assessed"
    assert result.use == "unsupported"
    assert "FUTURE_SOURCE" not in repr(result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "new_source"),
        ("source", "diavgeia"),
        ("connector_version", "kimdis-contract-v2"),
        ("normalizer_version", "kimdis-normalized-v2"),
    ],
)
def test_source_and_version_profiles_are_closed(field: str, value: str) -> None:
    data = facts()
    run = replace(data.binding.runs[0], **{field: value})
    assert (
        evaluate(replace(data, binding=replace(data.binding, runs=(run,)))).status == "not_assessed"
    )


@pytest.mark.parametrize("check", CHECKS[:-1])
def test_not_applicable_cannot_skip_a_required_check(check: str) -> None:
    assert (
        evaluate(checked(facts(), check, "not_applicable", "not_required_for_use")).status
        == "not_assessed"
    )


def test_missing_core_counts_and_record_partition_errors_have_precise_results() -> None:
    data = facts()
    assert evaluate(replace(data, counts=())).status == "not_assessed"
    for name, grain, expected in [
        ("page_records", "reported_record", "page_accounting"),
        ("selected_records", "source_record", "eligibility"),
        ("unknown_dates", "source_record", "eligibility"),
    ]:
        result = evaluate(counted(data, name, grain, 1))
        assert result.status == "blocked"
        assert next(c for c in result.checks if c.check_id == expected).status == "failed"


def test_u3_joint_participation_overlaps_but_resolved_denominator_does_not() -> None:
    data = facts("U3")
    for name, grain, value in [
        ("observations", "observation", 3),
        ("page_records", "reported_record", 3),
        ("selected_records", "source_record", 3),
        ("buyer_records", "source_record", 3),
        ("resolved_records", "source_record", 2),
        ("unresolved_suppliers", "source_record", 1),
        ("joint_records", "source_record", 2),
        ("supplier_participations", "participation", 4),
    ]:
        data = counted(data, name, grain, value)
    assert evaluate(data).status == "limited"
    assert evaluate(data).limitations == ("unresolved_suppliers",)
    assert evaluate(counted(data, "resolved_records", "source_record", 3)).status == "blocked"


@pytest.mark.parametrize(
    "target,value",
    [
        ("binding", None),
        ("provider_status", "source with spaces"),
        ("checks", []),
        ("counts", []),
        ("checks", (CheckResult("keys", "passed", "bad_reason"),)),
        ("checks", (CheckResult("keys", "failed", "private error"),)),
        ("checks", (CheckResult("new", "passed", "ok"),)),
        ("checks", (CheckResult("keys", "passed", "ok"),) * 2),
        ("checks", (None,)),
        ("checks", (CheckResult(cast(Any, []), "passed", "ok"),)),
        ("counts", (None,)),
        ("counts", (Count(cast(Any, []), "page", 1),)),
        ("counts", (Count("new", "page", 1),)),
        ("counts", (Count("pages", "money", 1),)),
        ("counts", (Count("pages", "page", True),)),
        ("counts", (Count("pages", "page", -1),)),
        ("counts", (Count("pages", "page", 2**63),)),
        ("counts", (Count("pages", "page", 1),) * 2),
        ("checks", (CheckResult("keys", "passed", "ok"),) * 10),
        ("counts", (Count("pages", "page", 1),) * 28),
    ],
)
def test_malformed_internal_inputs_fail_with_one_private_code(target: str, value: Any) -> None:
    with pytest.raises(AcceptanceError, match="^acceptance_input$"):
        evaluate(replace(facts(), **{target: value}))


@pytest.mark.parametrize(
    "target,value",
    [
        ("use", []),
        ("request_sha256", "X" * 64),
        ("definition_sha256", None),
        ("cohort_sha256", "path/private"),
        ("sql_sha256", "x"),
        ("cutoff", "2026-01-01"),
        ("cutoff", datetime(2026, 1, 1)),
        ("cutoff", datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))),
        ("runs", []),
        ("runs", (None,)),
        ("runs", (RunBinding("kimdis", RUN, "v1", "v1"),) * 101),
        ("runs", (RunBinding("kimdis", "INVALID_UUID", "v1", "v1"),)),
        ("runs", (RunBinding("kimdis", "{00000000-0000-4000-8000-000000000001}", "v1", "v1"),)),
        ("runs", (RunBinding("kimdis", cast(Any, None), "v1", "v1"),)),
        ("runs", (RunBinding("kimdis", RUN, "v1", "v1"),) * 2),
        ("runs", (RunBinding("source with space", RUN, "v1", "v1"),)),
    ],
)
def test_malformed_bindings_are_not_verification_outcomes(target: str, value: Any) -> None:
    data = facts()
    with pytest.raises(AcceptanceError, match="^acceptance_input$"):
        evaluate(replace(data, binding=replace(data.binding, **{target: value})))


@pytest.mark.parametrize(
    "name,grain",
    [
        ("unresolved_citations", "citation"),
        ("ambiguous_targets", "citation"),
        ("unknown_target_types", "citation"),
        ("mismatched_target_types", "citation"),
        ("revoked_targets", "citation"),
        ("unknown_reference_lists", "source_record"),
        ("unknown_cancellations", "source_record"),
        ("cancelled_records", "source_record"),
    ],
)
def test_each_citation_limitation_remains_disclosed(name: str, grain: str) -> None:
    data = facts("citations")
    for counter, counter_grain in [
        ("observations", "observation"),
        ("page_records", "reported_record"),
        ("selected_records", "source_record"),
    ]:
        data = counted(data, counter, counter_grain, 1)
    result = evaluate(counted(data, name, grain, 1))
    assert result.status == "limited"
    assert result.limitations == (name,)
