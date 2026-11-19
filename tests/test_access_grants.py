import re
from dataclasses import replace

import pytest

from nima.dataops import access_audit as aa
from nima.dataops import access_contract as ac
from nima.dataops import access_grants as ag
from tests.test_access_audit import clean

PRIVS = r"(?P<privs>[A-Z]+(?:, [A-Z]+)*)"
TABLE_RE = re.compile(
    rf"^GRANT {PRIVS} ON (?P<objs>[a-z_.]+(?:, [a-z_.]+)*) TO \"(?P<role>[^\"]+)\";$"
)
COLUMN_RE = re.compile(
    r"^GRANT UPDATE \((?P<col>[a-z_]+)\) ON (?P<table>[a-z_.]+) TO \"(?P<role>[^\"]+)\";$"
)
SCHEMA_RE = re.compile(
    r"^GRANT USAGE ON SCHEMA (?P<objs>[a-z_]+(?:, [a-z_]+)*) TO \"(?P<role>[^\"]+)\";$"
)
SEQ_RE = re.compile(
    r"^GRANT USAGE ON SEQUENCE (?P<objs>[a-z_.]+(?:, [a-z_.]+)*) TO \"(?P<role>[^\"]+)\";$"
)


def statements(text: str) -> list[str]:
    return [line for line in text.splitlines() if line and not line.startswith("--")]


def parse(
    text: str, role: str
) -> tuple[frozenset[str], dict[str, frozenset[ac.Priv]], set[tuple[str, str]], frozenset[str]]:
    schemas: frozenset[str] = frozenset()
    tables: dict[str, frozenset[ac.Priv]] = {}
    columns: set[tuple[str, str]] = set()
    seqs: frozenset[str] = frozenset()
    for line in statements(text):
        if m := SCHEMA_RE.match(line):
            assert m["role"] == role
            schemas |= frozenset(m["objs"].split(", "))
        elif m := COLUMN_RE.match(line):
            assert m["role"] == role
            columns.add((m["table"], m["col"]))
        elif m := SEQ_RE.match(line):
            assert m["role"] == role
            seqs |= frozenset(m["objs"].split(", "))
        elif m := TABLE_RE.match(line):
            assert m["role"] == role
            privs = frozenset(ac.Priv(p) for p in m["privs"].split(", "))
            for table in m["objs"].split(", "):
                tables[table] = tables.get(table, frozenset()) | privs
        else:
            pytest.fail(f"unrecognised statement: {line}")
    return schemas, tables, columns, seqs


@pytest.mark.parametrize("profile", sorted(ac.PROFILES))
def test_printed_grants_equal_the_profile_ceiling_exactly(profile: str) -> None:
    text = ag.render_grants(profile, "svc_role")
    schemas, tables, columns, seqs = parse(text, "svc_role")
    spec = ac.PROFILES[profile]
    assert schemas == spec.schemas
    assert tables == dict(spec.table_privileges)
    assert columns == set(spec.column_updates)
    assert seqs == spec.sequence_usage


@pytest.mark.parametrize("profile", sorted(ac.PROFILES))
def test_applying_the_printed_grants_passes_the_audit(profile: str) -> None:
    """Simulated application: facts built only from the printed text must audit clean."""
    _schemas_unused, tables, columns, seqs = parse(
        ag.render_grants(profile, "svc_role"), "svc_role"
    )
    base = clean(profile)
    snapshot = replace(
        base,
        schema_usage=parse(ag.render_grants(profile, "svc_role"), "svc_role")[0],
        tables=tuple(
            replace(
                t,
                privileges=tables.get(t.name, frozenset()),
                column_updates=frozenset(c for tbl, c in columns if tbl == t.name),
            )
            for t in base.tables
        ),
        sequences=tuple(
            aa.SequenceFacts(s.name, frozenset({"USAGE"}) if s.name in seqs else frozenset())
            for s in base.sequences
        ),
    )
    assert aa.assess(snapshot, profile).passed


def test_output_is_deterministic_and_states_it_only_prints() -> None:
    first = ag.render_grants("validation-writer", "svc_role")
    assert first == ag.render_grants("validation-writer", "svc_role")
    assert first.endswith("\n")
    head = [line for line in first.splitlines() if line.startswith("--")]
    joined = " ".join(head)
    assert ac.CONTRACT_VERSION in joined and "validation-writer" in joined
    assert "prints" in joined.lower() and "CONNECT" in joined


def test_statements_group_tables_by_identical_privileges() -> None:
    lines = statements(ag.render_grants("validation-writer", "svc_role"))
    assert 'GRANT SELECT ON nima.schema_migrations TO "svc_role";' in lines
    assert (
        'GRANT INSERT, SELECT ON nima_validation.attempts, nima_validation.outcomes TO "svc_role";'
        in lines
    )
    assert 'GRANT USAGE ON SCHEMA nima, nima_validation TO "svc_role";' in lines


def test_column_and_sequence_grants_are_explicit() -> None:
    lines = statements(ag.render_grants("retirement-operator", "svc_role"))
    assert 'GRANT UPDATE (state) ON nima.refresh_policies TO "svc_role";' in lines
    assert 'GRANT USAGE ON SEQUENCE nima.refresh_events_event_id_seq TO "svc_role";' in lines
    assert not any("ALL" in line or "PUBLIC" in line for line in lines)


@pytest.mark.parametrize(
    "role",
    [
        "",
        "Svc",
        "1svc",
        "svc role",
        'svc"; DROP TABLE x; --',
        "svc;",
        "a" * 64,
        "pg_monitor",
        "public",
        "né",
    ],
)
def test_unsafe_or_reserved_role_names_are_refused(role: str) -> None:
    with pytest.raises(ag.GrantError, match="role"):
        ag.render_grants("analytics-reader", role)


def test_role_name_of_63_characters_is_accepted() -> None:
    assert '"' + "a" * 63 + '"' in ag.render_grants("analytics-reader", "a" * 63)


def test_unknown_profile_is_refused_not_rendered() -> None:
    with pytest.raises(ac.ContractError, match="profile"):
        ag.render_grants("owner", "svc_role")


def test_only_contract_identifiers_are_ever_interpolated() -> None:
    safe = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")
    names = [n for n in ac.table_rules()] + list(ac.SEQUENCES)
    assert all(safe.match(n) for n in names)
    assert all(safe.match(c) for p in ac.PROFILES.values() for _t, c in p.column_updates)
