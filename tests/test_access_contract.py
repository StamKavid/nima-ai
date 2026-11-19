from dataclasses import replace

import pytest

from nima.dataops import access_contract as ac

EXPECTED_EVIDENCE = {
    "nima.raw_objects",
    "nima.run_pages",
    "nima.record_versions",
    "nima.observations",
    "nima.quarantine",
    "nima.projection_contracts",
    "nima.projection_mentions",
    "nima.projection_receipts",
    "nima.gemi_imports",
    "nima.gemi_responses",
    "nima.gemi_profile_versions",
    "nima.gemi_observations",
    "nima.refresh_events",
    "nima.identity_entities",
    "nima.identity_review_events",
    "nima.refresh_retirements",
    "nima.refresh_successions",
    "nima_processing.replay_batches",
    "nima_processing.replay_results",
    "nima_processing.metadata_snapshots",
    "nima_validation.attempts",
    "nima_validation.outcomes",
}
EXPECTED_CONTROL = {
    "nima.schema_migrations",
    "nima.ingest_runs",
    "nima.source_records",
    "nima.outbox",
    "nima.http_attempts",
    "nima.workflow_requests",
    "nima.workflow_dispatches",
    "nima.refresh_policies",
    "nima.refresh_cycles",
    "nima.refresh_windows",
    "nima.identity_review_heads",
}
EXPECTED_TRUNCATE_GUARDED = EXPECTED_EVIDENCE  # 0013 guarded the fifteen older tables
REWRITE = {ac.Priv.UPDATE, ac.Priv.DELETE, ac.Priv.TRUNCATE, ac.Priv.TRIGGER, ac.Priv.REFERENCES}


def test_classification_is_pinned_explicitly() -> None:
    rules = ac.table_rules()
    assert {n for n, r in rules.items() if r.kind is ac.TableKind.EVIDENCE} == EXPECTED_EVIDENCE
    assert {n for n, r in rules.items() if r.kind is ac.TableKind.CONTROL} == EXPECTED_CONTROL
    assert len(rules) == 33
    assert {n for n, r in rules.items() if r.truncate_guarded} == EXPECTED_TRUNCATE_GUARDED


def test_only_evidence_tables_can_be_truncate_guarded() -> None:
    for rule in ac.table_rules().values():
        assert not rule.truncate_guarded or rule.kind is ac.TableKind.EVIDENCE


def test_documented_and_proven_profiles_exist() -> None:
    assert set(ac.PROFILES) == {
        "projector",
        "analytics-reader",
        "run-health-reader",
        "refresh-health-reader",
        "validation-writer",
        "validation-reader",
        "retirement-operator",
        "successor-operator",
    }
    assert ac.CONTRACT_VERSION == "access-contract-v1"


def test_no_profile_can_rewrite_evidence() -> None:
    rules = ac.table_rules()
    for profile in ac.PROFILES.values():
        for table, privs in profile.table_privileges:
            if rules[table].kind is ac.TableKind.EVIDENCE:
                assert not privs & REWRITE, (profile.name, table)
        for table, _column in profile.column_updates:
            assert rules[table].kind is ac.TableKind.CONTROL, (profile.name, table)


def test_readers_are_select_only_with_no_sequences() -> None:
    for name in ("analytics-reader", "run-health-reader", "refresh-health-reader"):
        profile = ac.PROFILES[name]
        assert all(privs == {ac.Priv.SELECT} for _t, privs in profile.table_privileges)
        assert not profile.column_updates and not profile.sequence_usage


def test_documented_operator_ceilings_match_the_runbooks() -> None:
    retire = ac.PROFILES["retirement-operator"]
    assert dict(retire.table_privileges)["nima.refresh_retirements"] == {
        ac.Priv.SELECT,
        ac.Priv.INSERT,
    }
    assert dict(retire.table_privileges)["nima.refresh_events"] == {ac.Priv.INSERT}
    assert retire.column_updates == (("nima.refresh_policies", "state"),)
    assert retire.sequence_usage == frozenset({"nima.refresh_events_event_id_seq"})
    succ = ac.PROFILES["successor-operator"]
    assert dict(succ.table_privileges)["nima.refresh_policies"] == {
        ac.Priv.SELECT,
        ac.Priv.INSERT,
    }
    assert dict(succ.table_privileges)["nima.refresh_successions"] == {
        ac.Priv.SELECT,
        ac.Priv.INSERT,
    }


def test_shipped_contract_validates() -> None:
    ac.validate_contract()


def test_validation_rejects_evidence_rewrite_and_unknown_objects() -> None:
    good = ac.PROFILES["validation-writer"]
    bad = replace(
        good,
        table_privileges=good.table_privileges
        + (("nima_validation.attempts", frozenset({ac.Priv.UPDATE})),),
    )
    with pytest.raises(ac.ContractError, match="evidence"):
        ac.validate_contract({"p": bad})
    unknown = replace(good, table_privileges=(("nima.no_such_table", frozenset({ac.Priv.SELECT})),))
    with pytest.raises(ac.ContractError, match="unknown table"):
        ac.validate_contract({"p": unknown})
    seq = replace(good, sequence_usage=frozenset({"nima.no_such_seq"}))
    with pytest.raises(ac.ContractError, match="unknown sequence"):
        ac.validate_contract({"p": seq})
    schema = replace(good, schemas=frozenset({"public"}))
    with pytest.raises(ac.ContractError, match="schema"):
        ac.validate_contract({"p": schema})
    column = replace(good, column_updates=(("nima_validation.attempts", "x"),))
    with pytest.raises(ac.ContractError, match="column"):
        ac.validate_contract({"p": column})


def test_profile_lookup_is_exact_and_fails_closed() -> None:
    assert ac.get_profile("analytics-reader").name == "analytics-reader"
    for name in ("", "Analytics-Reader", "owner", "analytics-reader "):
        with pytest.raises(ac.ContractError, match="profile"):
            ac.get_profile(name)


def test_validation_refuses_bad_table_rules_and_misplaced_profile_tables() -> None:
    ev = ac.TableRule("nima.a", ac.TableKind.EVIDENCE)
    with pytest.raises(ac.ContractError, match="duplicate"):
        ac.validate_contract({}, (ev, ev))
    with pytest.raises(ac.ContractError, match="truncate guarded"):
        ac.validate_contract({}, (ac.TableRule("nima.a", ac.TableKind.CONTROL, True),))
    with pytest.raises(ac.ContractError, match="outside the Nima schemas"):
        ac.validate_contract({}, (ac.TableRule("public.a", ac.TableKind.CONTROL),))
    good = ac.PROFILES["validation-reader"]
    outside = replace(good, schemas=frozenset({"nima"}))
    with pytest.raises(ac.ContractError, match="outside its schemas"):
        ac.validate_contract({"p": outside})
    unknown_column_table = replace(good, column_updates=(("nima.no_such_table", "state"),))
    with pytest.raises(ac.ContractError, match="unknown table"):
        ac.validate_contract({"p": unknown_column_table})
