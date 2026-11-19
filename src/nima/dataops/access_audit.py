"""Pure assessment of one role's catalogue facts against the access contract.

Takes already-collected facts, so it never touches a database, a secret or row
data. Output is deterministic: fixed reason codes, sorted and de-duplicated.
"""

from dataclasses import dataclass
from enum import StrEnum

from nima.dataops.access_contract import (
    CONTRACT_VERSION,
    REWRITE_PRIVS,
    SCHEMAS,
    SEQUENCES,
    Priv,
    TableKind,
    get_profile,
    table_rules,
)


class AuditError(ValueError):
    """Facts are inconsistent, so no verdict is possible. Never treated as a pass."""


class ReasonCode(StrEnum):
    ROLE_SUPERUSER = "role_superuser"
    ROLE_CREATEROLE = "role_createrole"
    ROLE_CREATEDB = "role_createdb"
    ROLE_REPLICATION = "role_replication"
    ROLE_BYPASSRLS = "role_bypassrls"
    ROLE_OWNS_OBJECTS = "role_owns_objects"
    ROLE_OWNER_MEMBER = "role_owner_member"
    ROLE_DATABASE_CREATE = "role_database_create"
    ROLE_SCHEMA_CREATE = "role_schema_create"
    SCHEMA_ACCESS_EXCESS = "schema_access_excess"
    PRIVILEGE_EXCESS = "privilege_excess"
    EVIDENCE_REWRITE_PRIVILEGE = "evidence_rewrite_privilege"
    SEQUENCE_PRIVILEGE_EXCESS = "sequence_privilege_excess"
    EVIDENCE_TRIGGER_MISSING = "evidence_trigger_missing"
    EVIDENCE_TRIGGER_DISABLED = "evidence_trigger_disabled"
    TRUNCATE_TRIGGER_MISSING = "truncate_trigger_missing"
    TABLE_UNCLASSIFIED = "table_unclassified"
    TABLE_MISSING = "table_missing"


@dataclass(frozen=True)
class RoleFacts:
    name: str
    superuser: bool
    createrole: bool
    createdb: bool
    replication: bool
    bypassrls: bool
    owns_objects: bool
    owner_member: bool
    create_schemas: frozenset[str]
    create_database: bool


@dataclass(frozen=True)
class TriggerFacts:
    events: frozenset[str]  # subset of INSERT, UPDATE, DELETE, TRUNCATE
    before: bool
    enabled: bool  # fires for ordinary sessions (tgenabled O or A)


@dataclass(frozen=True)
class TableFacts:
    name: str
    privileges: frozenset[Priv]  # effective: direct, inherited and PUBLIC
    column_updates: frozenset[str]
    triggers: tuple[TriggerFacts, ...]


@dataclass(frozen=True)
class SequenceFacts:
    name: str
    privileges: frozenset[str]  # USAGE, SELECT, UPDATE


@dataclass(frozen=True)
class AccessSnapshot:
    role: RoleFacts
    schema_usage: frozenset[str]
    tables: tuple[TableFacts, ...]
    sequences: tuple[SequenceFacts, ...]


@dataclass(frozen=True, order=True)
class Reason:
    code: ReasonCode
    subject: str
    detail: str = ""


@dataclass(frozen=True)
class AuditResult:
    contract_version: str
    profile: str
    role: str
    reasons: tuple[Reason, ...]
    limitations: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """True only when the selected recorded checks found nothing; not a security claim."""
        return not self.reasons


_ROLE_FLAGS = (
    ("superuser", ReasonCode.ROLE_SUPERUSER),
    ("createrole", ReasonCode.ROLE_CREATEROLE),
    ("createdb", ReasonCode.ROLE_CREATEDB),
    ("replication", ReasonCode.ROLE_REPLICATION),
    ("bypassrls", ReasonCode.ROLE_BYPASSRLS),
    ("owns_objects", ReasonCode.ROLE_OWNS_OBJECTS),
    ("owner_member", ReasonCode.ROLE_OWNER_MEMBER),
)


def _unique(names: list[str], what: str) -> None:
    if len(set(names)) != len(names):
        raise AuditError(f"duplicate {what} facts")


def _assess_role(role: RoleFacts, usage: frozenset[str], allowed: frozenset[str]) -> list[Reason]:
    out = [Reason(code, role.name) for attr, code in _ROLE_FLAGS if getattr(role, attr)]
    if role.create_database:
        out.append(Reason(ReasonCode.ROLE_DATABASE_CREATE, role.name))
    out += [Reason(ReasonCode.ROLE_SCHEMA_CREATE, s) for s in role.create_schemas & SCHEMAS]
    out += [Reason(ReasonCode.SCHEMA_ACCESS_EXCESS, s) for s in (usage & SCHEMAS) - allowed]
    return out


def _has_guard(table: TableFacts, events: frozenset[str]) -> bool | None:
    """True if an enabled BEFORE guard covers events; None if only disabled ones do."""
    covered = frozenset().union(*(t.events for t in table.triggers if t.before and t.enabled))
    if events <= covered:
        return True
    covered_any = frozenset().union(*(t.events for t in table.triggers if t.before))
    return None if events <= covered_any else False


def _assess_table(
    table: TableFacts,
    kind: TableKind,
    guarded: bool,
    ceiling: frozenset[Priv],
    columns: frozenset[str],
) -> list[Reason]:
    out: list[Reason] = []
    evidence = kind is TableKind.EVIDENCE

    def code_for(priv: Priv | None) -> ReasonCode:
        rewrite = priv is None or priv in REWRITE_PRIVS
        return (
            ReasonCode.EVIDENCE_REWRITE_PRIVILEGE
            if evidence and rewrite
            else ReasonCode.PRIVILEGE_EXCESS
        )

    out += [Reason(code_for(p), table.name, p.value) for p in table.privileges - ceiling]
    if Priv.UPDATE not in table.privileges:
        out += [
            Reason(code_for(None), table.name, f"UPDATE({c})")
            for c in table.column_updates - columns
        ]
    if evidence:
        update_delete = frozenset({"UPDATE", "DELETE"})
        state = _has_guard(table, update_delete)
        if state is None:
            out.append(Reason(ReasonCode.EVIDENCE_TRIGGER_DISABLED, table.name))
        elif not state:
            out.append(Reason(ReasonCode.EVIDENCE_TRIGGER_MISSING, table.name))
        if guarded and _has_guard(table, frozenset({"TRUNCATE"})) is not True:
            out.append(Reason(ReasonCode.TRUNCATE_TRIGGER_MISSING, table.name))
    return out


def assess(snapshot: AccessSnapshot, profile_name: str) -> AuditResult:
    profile = get_profile(profile_name)
    rules = table_rules()
    _unique([t.name for t in snapshot.tables], "table")
    _unique([s.name for s in snapshot.sequences], "sequence")
    ceilings = dict(profile.table_privileges)
    reasons = _assess_role(snapshot.role, snapshot.schema_usage, profile.schemas)
    seen = {t.name for t in snapshot.tables}
    reasons += [Reason(ReasonCode.TABLE_MISSING, n) for n in rules if n not in seen]
    for table in snapshot.tables:
        rule = rules.get(table.name)
        if rule is None:
            reasons.append(Reason(ReasonCode.TABLE_UNCLASSIFIED, table.name))
            continue
        columns = frozenset(c for t, c in profile.column_updates if t == table.name)
        reasons += _assess_table(
            table, rule.kind, rule.truncate_guarded, ceilings.get(table.name, frozenset()), columns
        )
    sequence_names = set(SEQUENCES)
    for seq in snapshot.sequences:
        if seq.name not in sequence_names:
            raise AuditError("unknown sequence facts")
        allowed = frozenset({"USAGE"}) if seq.name in profile.sequence_usage else frozenset()
        reasons += [
            Reason(ReasonCode.SEQUENCE_PRIVILEGE_EXCESS, seq.name, p)
            for p in seq.privileges - allowed
        ]
    limitations = tuple(
        sorted(
            f"truncate_not_trigger_guarded:{n}"
            for n, r in rules.items()
            if r.kind is TableKind.EVIDENCE and not r.truncate_guarded
        )
    )
    ordered = tuple(sorted(set(reasons), key=lambda r: (r.code.value, r.subject, r.detail)))
    return AuditResult(CONTRACT_VERSION, profile.name, snapshot.role.name, ordered, limitations)
