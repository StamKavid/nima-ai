"""Bounded single-snapshot catalogue read for the access audit.

Reads only PostgreSQL catalogue functions and views: no application rows, no
control locks, no writes. Effective privileges come from the has_*_privilege
functions, so inherited, column-level and PUBLIC grants are all counted.
"""

import psycopg

from nima.dataops.access_audit import (
    AccessSnapshot,
    RoleFacts,
    SequenceFacts,
    TableFacts,
    TriggerFacts,
)
from nima.dataops.access_contract import SCHEMAS, Priv
from nima.dataops.health import HealthError
from nima.storage.connection import connect
from nima.storage.postgres import MigrationError, validate_schema

MAX_TABLES = 128
MAX_SEQUENCES = 64
SEQUENCE_PRIVILEGES = ("USAGE", "SELECT", "UPDATE")
_TG_BEFORE = 2
_TG_EVENTS = ((4, "INSERT"), (8, "DELETE"), (16, "UPDATE"), (32, "TRUNCATE"))

_ROLE = """
SELECT r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolreplication, r.rolbypassrls,
  (EXISTS (SELECT 1 FROM pg_namespace n
            WHERE n.nspname = ANY(%(schemas)s) AND n.nspowner = r.oid)
   OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = ANY(%(schemas)s) AND c.relowner = r.oid)
   OR EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname = ANY(%(schemas)s) AND p.proowner = r.oid)) AS owns_objects,
  (EXISTS (SELECT 1 FROM pg_namespace n
            WHERE n.nspname = ANY(%(schemas)s) AND n.nspowner <> r.oid
              AND pg_has_role(r.oid, n.nspowner, 'MEMBER'))
   OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = ANY(%(schemas)s) AND c.relowner <> r.oid
                 AND pg_has_role(r.oid, c.relowner, 'MEMBER'))) AS owner_member,
  has_database_privilege(r.oid, current_database(), 'CREATE') AS create_database
FROM pg_roles r WHERE r.rolname = %(role)s
"""

_SCHEMAS = """
SELECT n.nspname,
  has_schema_privilege(r.oid, n.oid, 'USAGE'), has_schema_privilege(r.oid, n.oid, 'CREATE')
FROM pg_namespace n CROSS JOIN pg_roles r
WHERE r.rolname = %(role)s AND n.nspname = ANY(%(schemas)s) ORDER BY 1
"""

_TABLES = """
SELECT c.oid::bigint, n.nspname || '.' || c.relname,
  ARRAY(SELECT p FROM unnest(%(privs)s::text[]) p
         WHERE has_table_privilege(r.oid, c.oid, p) ORDER BY p),
  ARRAY(SELECT a.attname::text FROM pg_attribute a
         WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
           AND has_column_privilege(r.oid, c.oid, a.attnum, 'UPDATE') ORDER BY 1)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace CROSS JOIN pg_roles r
WHERE r.rolname = %(role)s AND n.nspname = ANY(%(schemas)s) AND c.relkind IN ('r', 'p')
ORDER BY 2 LIMIT %(limit)s
"""

_TRIGGERS = """
SELECT t.tgrelid::bigint, t.tgtype::int, t.tgenabled::text
FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal AND n.nspname = ANY(%(schemas)s) ORDER BY 1, t.tgname
"""

_SEQUENCES = """
SELECT n.nspname || '.' || c.relname,
  ARRAY(SELECT p FROM unnest(%(privs)s::text[]) p
         WHERE has_sequence_privilege(r.oid, c.oid, p) ORDER BY p)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace CROSS JOIN pg_roles r
WHERE r.rolname = %(role)s AND n.nspname = ANY(%(schemas)s) AND c.relkind = 'S'
ORDER BY 1 LIMIT %(limit)s
"""


def _trigger(tgtype: int, enabled: str) -> TriggerFacts:
    return TriggerFacts(
        events=frozenset(name for bit, name in _TG_EVENTS if tgtype & bit),
        before=bool(tgtype & _TG_BEFORE),
        enabled=enabled in ("O", "A"),
    )


def collect(c: psycopg.Connection, role: str) -> AccessSnapshot:
    """Read one role's facts on an open connection; the caller owns the transaction."""
    schemas = sorted(SCHEMAS)
    base = {"role": role, "schemas": schemas}
    row = c.execute(_ROLE, base).fetchone()
    if row is None:
        raise HealthError("access_audit_unavailable")
    schema_rows = c.execute(_SCHEMAS, base).fetchall()
    table_rows = c.execute(
        _TABLES, {**base, "privs": [p.value for p in Priv], "limit": MAX_TABLES + 1}
    ).fetchall()
    if len(table_rows) > MAX_TABLES:
        raise HealthError("access_audit_limit")
    seq_rows = c.execute(
        _SEQUENCES, {**base, "privs": list(SEQUENCE_PRIVILEGES), "limit": MAX_SEQUENCES + 1}
    ).fetchall()
    if len(seq_rows) > MAX_SEQUENCES:
        raise HealthError("access_audit_limit")
    by_oid: dict[int, list[TriggerFacts]] = {}
    for oid, tgtype, enabled in c.execute(_TRIGGERS, {"schemas": schemas}).fetchall():
        by_oid.setdefault(oid, []).append(_trigger(tgtype, enabled))
    return AccessSnapshot(
        role=RoleFacts(
            name=role,
            superuser=row[0],
            createrole=row[1],
            createdb=row[2],
            replication=row[3],
            bypassrls=row[4],
            owns_objects=row[5],
            owner_member=row[6],
            create_schemas=frozenset(name for name, _usage, create in schema_rows if create),
            create_database=row[7],
        ),
        schema_usage=frozenset(name for name, usage, _create in schema_rows if usage),
        tables=tuple(
            TableFacts(
                name=name,
                privileges=frozenset(Priv(p) for p in privileges),
                column_updates=frozenset(columns),
                triggers=tuple(by_oid.get(oid, ())),
            )
            for oid, name, privileges, columns in table_rows
        ),
        sequences=tuple(SequenceFacts(name, frozenset(privs)) for name, privs in seq_rows),
    )


def read_snapshot(dsn: str, role: str) -> AccessSnapshot:
    if (
        not isinstance(dsn, str)
        or not dsn.strip()
        or not isinstance(role, str)
        or not 1 <= len(role) <= 63
        or "\x00" in role
    ):
        raise HealthError("access_audit_configuration")
    try:
        with connect(dsn) as c, c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            c.execute("SET LOCAL TIME ZONE 'UTC'")
            c.execute("SET LOCAL statement_timeout = 5000")
            c.execute("SET LOCAL lock_timeout = 2000")
            validate_schema(c)
            return collect(c, role)
    except HealthError:
        raise
    except (psycopg.Error, MigrationError, ValueError):
        raise HealthError("access_audit_unavailable") from None
