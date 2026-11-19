from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from nima.dataops import access_audit as aa
from nima.dataops import access_contract as ac
from nima.dataops.access_audit import ReasonCode as R

NO_REWRITE_TRIGGER = aa.TriggerFacts(
    events=frozenset({"UPDATE", "DELETE"}), before=True, enabled=True
)
TRUNCATE_TRIGGER = aa.TriggerFacts(events=frozenset({"TRUNCATE"}), before=True, enabled=True)
SAFE_ROLE = aa.RoleFacts(
    name="svc",
    superuser=False,
    createrole=False,
    createdb=False,
    replication=False,
    bypassrls=False,
    owns_objects=False,
    owner_member=False,
    create_schemas=frozenset(),
    create_database=False,
)


def clean(profile_name: str) -> aa.AccessSnapshot:
    """A snapshot where the role holds exactly its ceiling and protections are intact."""
    profile = ac.get_profile(profile_name)
    ceiling = dict(profile.table_privileges)
    tables = []
    for name, rule in ac.table_rules().items():
        triggers: tuple[aa.TriggerFacts, ...] = ()
        if rule.kind is ac.TableKind.EVIDENCE:
            triggers = (NO_REWRITE_TRIGGER,) + (
                (TRUNCATE_TRIGGER,) if rule.truncate_guarded else ()
            )
        tables.append(
            aa.TableFacts(
                name=name,
                privileges=frozenset(ceiling.get(name, frozenset())),
                column_updates=frozenset(c for t, c in profile.column_updates if t == name),
                triggers=triggers,
            )
        )
    sequences = tuple(
        aa.SequenceFacts(
            name=s, privileges=frozenset({"USAGE"} if s in profile.sequence_usage else ())
        )
        for s in ac.SEQUENCES
    )
    return aa.AccessSnapshot(
        role=replace(SAFE_ROLE),
        schema_usage=profile.schemas,
        tables=tuple(tables),
        sequences=sequences,
    )


def with_table(snap: aa.AccessSnapshot, name: str, **changes: Any) -> aa.AccessSnapshot:
    tables = tuple(replace(t, **changes) if t.name == name else t for t in snap.tables)
    return replace(snap, tables=tables)


def codes(result: aa.AuditResult) -> list[tuple[R, str, str]]:
    return [(r.code, r.subject, r.detail) for r in result.reasons]


@pytest.mark.parametrize("profile", sorted(ac.PROFILES))
def test_exact_ceiling_passes_for_every_profile(profile: str) -> None:
    result = aa.assess(clean(profile), profile)
    assert result.reasons == () and result.passed
    assert result.contract_version == ac.CONTRACT_VERSION and result.profile == profile


def test_holding_less_than_the_ceiling_passes() -> None:
    snap = with_table(
        clean("validation-writer"), "nima_validation.outcomes", privileges=frozenset()
    )
    assert aa.assess(snap, "validation-writer").passed


def test_extra_insert_on_control_table_is_excess_but_not_a_rewrite() -> None:
    snap = with_table(
        clean("analytics-reader"),
        "nima.ingest_runs",
        privileges=frozenset({ac.Priv.SELECT, ac.Priv.INSERT}),
    )
    assert codes(aa.assess(snap, "analytics-reader")) == [
        (R.PRIVILEGE_EXCESS, "nima.ingest_runs", "INSERT")
    ]


@pytest.mark.parametrize(
    "priv", [ac.Priv.UPDATE, ac.Priv.DELETE, ac.Priv.TRUNCATE, ac.Priv.TRIGGER]
)
def test_rewrite_privilege_on_evidence_is_flagged_distinctly(priv: ac.Priv) -> None:
    snap = with_table(
        clean("analytics-reader"), "nima.observations", privileges=frozenset({ac.Priv.SELECT, priv})
    )
    assert codes(aa.assess(snap, "analytics-reader")) == [
        (R.EVIDENCE_REWRITE_PRIVILEGE, "nima.observations", priv.value)
    ]


def test_insert_beyond_ceiling_on_evidence_is_plain_excess() -> None:
    snap = with_table(
        clean("analytics-reader"),
        "nima.raw_objects",
        privileges=frozenset({ac.Priv.SELECT, ac.Priv.INSERT}),
    )
    assert codes(aa.assess(snap, "analytics-reader")) == [
        (R.PRIVILEGE_EXCESS, "nima.raw_objects", "INSERT")
    ]


def test_column_update_grants_count_as_update() -> None:
    ok = clean("retirement-operator")
    assert aa.assess(ok, "retirement-operator").passed
    extra = with_table(
        ok, "nima.refresh_policies", column_updates=frozenset({"state", "start_date"})
    )
    assert codes(aa.assess(extra, "retirement-operator")) == [
        (R.PRIVILEGE_EXCESS, "nima.refresh_policies", "UPDATE(start_date)")
    ]
    evidence = with_table(
        clean("analytics-reader"), "nima.observations", column_updates=frozenset({"payload"})
    )
    assert codes(aa.assess(evidence, "analytics-reader")) == [
        (R.EVIDENCE_REWRITE_PRIVILEGE, "nima.observations", "UPDATE(payload)")
    ]


def test_table_level_update_makes_column_detail_irrelevant() -> None:
    snap = with_table(
        clean("retirement-operator"),
        "nima.refresh_policies",
        privileges=frozenset({ac.Priv.SELECT, ac.Priv.UPDATE}),
        column_updates=frozenset({"state"}),
    )
    assert codes(aa.assess(snap, "retirement-operator")) == [
        (R.PRIVILEGE_EXCESS, "nima.refresh_policies", "UPDATE")
    ]


ROLE_CASES: list[tuple[Callable[[aa.RoleFacts], aa.RoleFacts], R]] = [
    (lambda r: replace(r, superuser=True), R.ROLE_SUPERUSER),
    (lambda r: replace(r, createrole=True), R.ROLE_CREATEROLE),
    (lambda r: replace(r, createdb=True), R.ROLE_CREATEDB),
    (lambda r: replace(r, replication=True), R.ROLE_REPLICATION),
    (lambda r: replace(r, bypassrls=True), R.ROLE_BYPASSRLS),
    (lambda r: replace(r, owns_objects=True), R.ROLE_OWNS_OBJECTS),
    (lambda r: replace(r, owner_member=True), R.ROLE_OWNER_MEMBER),
]


@pytest.mark.parametrize(("change", "code"), ROLE_CASES)
def test_dangerous_role_attributes_are_each_flagged(
    change: Callable[[aa.RoleFacts], aa.RoleFacts], code: R
) -> None:
    snap = clean("analytics-reader")
    snap = replace(snap, role=change(snap.role))
    assert codes(aa.assess(snap, "analytics-reader")) == [(code, "svc", "")]


def test_create_rights_and_extra_schema_usage_are_flagged() -> None:
    snap = clean("analytics-reader")
    snap = replace(
        snap,
        role=replace(snap.role, create_schemas=frozenset({"nima"}), create_database=True),
        schema_usage=frozenset({"nima", "nima_validation"}),
    )
    assert codes(aa.assess(snap, "analytics-reader")) == [
        (R.ROLE_DATABASE_CREATE, "svc", ""),
        (R.ROLE_SCHEMA_CREATE, "nima", ""),
        (R.SCHEMA_ACCESS_EXCESS, "nima_validation", ""),
    ]


def test_sequence_privileges_beyond_ceiling_are_flagged() -> None:
    snap = clean("retirement-operator")
    seqs = tuple(
        replace(s, privileges=frozenset({"USAGE", "UPDATE"}))
        if s.name == "nima.refresh_events_event_id_seq"
        else replace(s, privileges=frozenset({"USAGE"}))
        if s.name == "nima.http_attempts_attempt_id_seq"
        else s
        for s in snap.sequences
    )
    result = aa.assess(replace(snap, sequences=seqs), "retirement-operator")
    assert codes(result) == [
        (R.SEQUENCE_PRIVILEGE_EXCESS, "nima.http_attempts_attempt_id_seq", "USAGE"),
        (R.SEQUENCE_PRIVILEGE_EXCESS, "nima.refresh_events_event_id_seq", "UPDATE"),
    ]


def test_missing_or_disabled_evidence_trigger_is_flagged() -> None:
    missing = with_table(clean("analytics-reader"), "nima.quarantine", triggers=(TRUNCATE_TRIGGER,))
    assert codes(aa.assess(missing, "analytics-reader")) == [
        (R.EVIDENCE_TRIGGER_MISSING, "nima.quarantine", "")
    ]
    disabled = with_table(
        clean("analytics-reader"),
        "nima.quarantine",
        triggers=(replace(NO_REWRITE_TRIGGER, enabled=False), TRUNCATE_TRIGGER),
    )
    assert codes(aa.assess(disabled, "analytics-reader")) == [
        (R.EVIDENCE_TRIGGER_DISABLED, "nima.quarantine", "")
    ]


@pytest.mark.parametrize(
    "weak",
    [
        replace(NO_REWRITE_TRIGGER, before=False),
        replace(NO_REWRITE_TRIGGER, events=frozenset({"UPDATE"})),
        replace(NO_REWRITE_TRIGGER, events=frozenset({"DELETE"})),
    ],
)
def test_trigger_that_does_not_block_update_and_delete_before_the_write_is_missing(
    weak: aa.TriggerFacts,
) -> None:
    snap = with_table(
        clean("analytics-reader"), "nima.observations", triggers=(weak, TRUNCATE_TRIGGER)
    )
    assert codes(aa.assess(snap, "analytics-reader")) == [
        (R.EVIDENCE_TRIGGER_MISSING, "nima.observations", "")
    ]


def test_update_and_delete_may_be_guarded_by_two_separate_triggers() -> None:
    triggers = (
        replace(NO_REWRITE_TRIGGER, events=frozenset({"UPDATE"})),
        replace(NO_REWRITE_TRIGGER, events=frozenset({"DELETE"})),
    )
    snap = with_table(
        clean("analytics-reader"), "nima.observations", triggers=(*triggers, TRUNCATE_TRIGGER)
    )
    assert aa.assess(snap, "analytics-reader").passed


def test_guarded_truncate_trigger_that_disappears_is_flagged() -> None:
    snap = with_table(
        clean("validation-reader"), "nima_validation.attempts", triggers=(NO_REWRITE_TRIGGER,)
    )
    assert codes(aa.assess(snap, "validation-reader")) == [
        (R.TRUNCATE_TRIGGER_MISSING, "nima_validation.attempts", "")
    ]


def test_every_evidence_table_is_guarded_so_no_limitations_are_reported() -> None:
    result = aa.assess(clean("analytics-reader"), "analytics-reader")
    assert result.passed and result.limitations == ()


def test_an_unguarded_evidence_table_is_disclosed_as_a_sorted_limitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules = ac.table_rules()
    for name in ("nima.raw_objects", "nima.observations"):
        rules[name] = replace(rules[name], truncate_guarded=False)
    monkeypatch.setattr(aa, "table_rules", lambda: rules)
    result = aa.assess(clean("analytics-reader"), "analytics-reader")
    assert result.passed
    assert result.limitations == (
        "truncate_not_trigger_guarded:nima.observations",
        "truncate_not_trigger_guarded:nima.raw_objects",
    )


def test_unclassified_and_missing_tables_fail_closed() -> None:
    snap = clean("analytics-reader")
    extra = aa.TableFacts(
        name="nima.brand_new", privileges=frozenset(), column_updates=frozenset(), triggers=()
    )
    result = aa.assess(replace(snap, tables=snap.tables + (extra,)), "analytics-reader")
    assert codes(result) == [(R.TABLE_UNCLASSIFIED, "nima.brand_new", "")]
    fewer = replace(snap, tables=tuple(t for t in snap.tables if t.name != "nima.outbox"))
    assert codes(aa.assess(fewer, "analytics-reader")) == [(R.TABLE_MISSING, "nima.outbox", "")]


def test_unknown_profile_and_duplicate_facts_are_errors_not_passes() -> None:
    with pytest.raises(ac.ContractError, match="profile"):
        aa.assess(clean("analytics-reader"), "nobody")
    snap = clean("analytics-reader")
    with pytest.raises(aa.AuditError, match="duplicate"):
        aa.assess(replace(snap, tables=snap.tables + (snap.tables[0],)), "analytics-reader")
    with pytest.raises(aa.AuditError, match="duplicate"):
        aa.assess(
            replace(snap, sequences=snap.sequences + (snap.sequences[0],)), "analytics-reader"
        )


def test_reasons_are_sorted_unique_and_deterministic() -> None:
    snap = clean("analytics-reader")
    snap = with_table(
        snap, "nima.raw_objects", privileges=frozenset({ac.Priv.SELECT, ac.Priv.DELETE})
    )
    snap = with_table(
        snap, "nima.ingest_runs", privileges=frozenset({ac.Priv.SELECT, ac.Priv.INSERT})
    )
    snap = replace(snap, role=replace(snap.role, superuser=True))
    first = aa.assess(snap, "analytics-reader")
    second = aa.assess(replace(snap, tables=tuple(reversed(snap.tables))), "analytics-reader")
    assert first == second
    assert list(first.reasons) == sorted(
        first.reasons, key=lambda r: (r.code.value, r.subject, r.detail)
    )
    assert len(set(first.reasons)) == len(first.reasons) == 3
    assert not first.passed


def test_facts_for_an_unknown_sequence_are_an_error_not_a_pass() -> None:
    snap = clean("analytics-reader")
    extra = aa.SequenceFacts(name="nima.surprise_seq", privileges=frozenset())
    with pytest.raises(aa.AuditError, match="unknown sequence"):
        aa.assess(replace(snap, sequences=snap.sequences + (extra,)), "analytics-reader")
