"""Packaged access contract: table classes and runtime-role privilege ceilings.

One source of truth for what each documented runtime role may hold. The audit
compares live privileges against these ceilings; a later renderer prints grants
from the same data, so documentation, grants and checks cannot drift apart.
Holding less than a ceiling is acceptable; holding more is attention.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

CONTRACT_VERSION = "access-contract-v1"
SCHEMAS = frozenset({"nima", "nima_processing", "nima_validation"})


class ContractError(ValueError):
    """The contract or a requested profile is invalid. Never treated as a pass."""


class Priv(StrEnum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    TRUNCATE = "TRUNCATE"
    REFERENCES = "REFERENCES"
    TRIGGER = "TRIGGER"


class TableKind(StrEnum):
    EVIDENCE = "evidence"
    CONTROL = "control"


# Privileges that let a role change or remove stored evidence or its protections.
REWRITE_PRIVS = frozenset({Priv.UPDATE, Priv.DELETE, Priv.TRUNCATE, Priv.TRIGGER, Priv.REFERENCES})


@dataclass(frozen=True)
class TableRule:
    name: str
    kind: TableKind
    truncate_guarded: bool = False


@dataclass(frozen=True)
class Profile:
    name: str
    schemas: frozenset[str]
    table_privileges: tuple[tuple[str, frozenset[Priv]], ...]
    column_updates: tuple[tuple[str, str], ...] = ()
    sequence_usage: frozenset[str] = frozenset()


def _evidence(*names: str, truncate_guarded: bool = False) -> tuple[TableRule, ...]:
    return tuple(TableRule(n, TableKind.EVIDENCE, truncate_guarded) for n in names)


def _control(*names: str) -> tuple[TableRule, ...]:
    return tuple(TableRule(n, TableKind.CONTROL) for n in names)


# Classification mirrors migrations 0001-0012 plus the runner-created schema_migrations.
# Only the newer evidence tables carry a TRUNCATE-blocking trigger; the older ones
# block UPDATE/DELETE only, so TRUNCATE there is guarded by privilege alone.
_TABLES: tuple[TableRule, ...] = (
    *_evidence(
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
    ),
    *_evidence(
        "nima.refresh_retirements",
        "nima.refresh_successions",
        "nima_processing.replay_batches",
        "nima_processing.replay_results",
        "nima_processing.metadata_snapshots",
        "nima_validation.attempts",
        "nima_validation.outcomes",
        truncate_guarded=True,
    ),
    *_control(
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
    ),
)

SEQUENCES: tuple[str, ...] = (
    "nima.http_attempts_attempt_id_seq",
    "nima.observations_observation_id_seq",
    "nima.refresh_events_event_id_seq",
)

_S = frozenset({Priv.SELECT})
_SI = frozenset({Priv.SELECT, Priv.INSERT})
_I = frozenset({Priv.INSERT})


def _select(*tables: str) -> tuple[tuple[str, frozenset[Priv]], ...]:
    return tuple((f"nima.{t}", _S) for t in tables)


_EVENTS_SEQ = frozenset({"nima.refresh_events_event_id_seq"})

# Grants are exactly those documented in the operator runbooks; none is guessed.
_PROFILES: tuple[Profile, ...] = (
    Profile(
        "analytics-reader",
        frozenset({"nima"}),
        _select(
            "schema_migrations",
            "ingest_runs",
            "run_pages",
            "raw_objects",
            "observations",
            "record_versions",
            "quarantine",
            "projection_contracts",
            "projection_mentions",
            "projection_receipts",
        ),
    ),
    Profile(
        "run-health-reader",
        frozenset({"nima"}),
        _select(
            "schema_migrations",
            "ingest_runs",
            "run_pages",
            "observations",
            "projection_receipts",
            "workflow_requests",
        ),
    ),
    Profile(
        "refresh-health-reader",
        frozenset({"nima"}),
        _select(
            "schema_migrations",
            "refresh_policies",
            "refresh_cycles",
            "refresh_windows",
            "refresh_retirements",
            "workflow_requests",
            "workflow_dispatches",
        ),
    ),
    Profile(
        "validation-writer",
        frozenset({"nima", "nima_validation"}),
        (
            ("nima.schema_migrations", _S),
            ("nima_validation.attempts", _SI),
            ("nima_validation.outcomes", _SI),
        ),
    ),
    Profile(
        "validation-reader",
        frozenset({"nima", "nima_validation"}),
        (
            ("nima.schema_migrations", _S),
            ("nima_validation.attempts", _S),
            ("nima_validation.outcomes", _S),
        ),
    ),
    Profile(
        "retirement-operator",
        frozenset({"nima"}),
        (
            ("nima.schema_migrations", _S),
            ("nima.refresh_policies", _S),
            ("nima.refresh_retirements", _SI),
            ("nima.refresh_events", _I),
        ),
        column_updates=(("nima.refresh_policies", "state"),),
        sequence_usage=_EVENTS_SEQ,
    ),
    Profile(
        "successor-operator",
        frozenset({"nima"}),
        (
            ("nima.schema_migrations", _S),
            ("nima.refresh_policies", _SI),
            ("nima.refresh_retirements", _S),
            ("nima.refresh_successions", _SI),
            ("nima.refresh_events", _SI),
            ("nima.refresh_cycles", _S),
        ),
        column_updates=(("nima.refresh_policies", "state"),),
        sequence_usage=_EVENTS_SEQ,
    ),
)

PROFILES: Mapping[str, Profile] = {p.name: p for p in _PROFILES}


def table_rules() -> dict[str, TableRule]:
    return {t.name: t for t in _TABLES}


def get_profile(name: str) -> Profile:
    profile = PROFILES.get(name)
    if profile is None:
        raise ContractError("unknown access profile")
    return profile


def validate_contract(
    profiles: Mapping[str, Profile] | None = None, tables: tuple[TableRule, ...] | None = None
) -> None:
    """Refuse a contract that is internally inconsistent or lets a profile rewrite evidence."""
    declared = _TABLES if tables is None else tables
    rules = {t.name: t for t in declared}
    if len(rules) != len(declared):
        raise ContractError("duplicate table rule")
    for rule in declared:
        if rule.truncate_guarded and rule.kind is not TableKind.EVIDENCE:
            raise ContractError("only evidence tables can be truncate guarded")
        if rule.name.split(".", 1)[0] not in SCHEMAS:
            raise ContractError("table outside the Nima schemas")
    for profile in (PROFILES if profiles is None else profiles).values():
        if not profile.schemas <= SCHEMAS:
            raise ContractError("profile names a schema outside the Nima schemas")
        for table, privs in profile.table_privileges:
            grant_rule = rules.get(table)
            if grant_rule is None:
                raise ContractError("profile names an unknown table")
            if grant_rule.kind is TableKind.EVIDENCE and privs & REWRITE_PRIVS:
                raise ContractError("profile may rewrite evidence")
            if table.split(".", 1)[0] not in profile.schemas:
                raise ContractError("profile table outside its schemas")
        for table, _column in profile.column_updates:
            column_rule = rules.get(table)
            if column_rule is None:
                raise ContractError("profile names an unknown table")
            if column_rule.kind is TableKind.EVIDENCE:
                raise ContractError("evidence tables take no column UPDATE; column grant refused")
        if not profile.sequence_usage <= set(SEQUENCES):
            raise ContractError("profile names an unknown sequence")
