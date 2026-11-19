"""Print reviewed GRANT statements for one access profile; never executes anything.

Statements come only from the packaged contract, so they cannot exceed the
ceiling that the audit checks. The role name is the only caller input and is
restricted to a plain lowercase identifier before it is quoted.
"""

import re

from nima.dataops.access_contract import CONTRACT_VERSION, Priv, get_profile

_ROLE = re.compile(r"[a-z_][a-z0-9_]{0,62}")
_RESERVED_NAMES = frozenset({"public", "none", "current_user", "session_user", "current_role"})


class GrantError(ValueError):
    """The role name is unsafe or reserved. Nothing is rendered."""


def _role(name: str) -> str:
    if not _ROLE.fullmatch(name) or name.startswith("pg_") or name in _RESERVED_NAMES:
        raise GrantError("invalid role name")
    return f'"{name}"'


def render_grants(profile_name: str, role: str) -> str:
    profile = get_profile(profile_name)
    quoted = _role(role)
    lines = [
        f"-- {CONTRACT_VERSION}: profile {profile.name}, role {quoted}",
        "-- Nima only prints these statements. Review them, then run them yourself as an",
        "-- authorised database administrator; nothing here is executed by Nima.",
        "-- Database CONNECT is granted separately and is not part of this contract.",
        f"GRANT USAGE ON SCHEMA {', '.join(sorted(profile.schemas))} TO {quoted};",
    ]
    groups: dict[tuple[Priv, ...], list[str]] = {}
    for table, privs in profile.table_privileges:
        groups.setdefault(tuple(sorted(privs)), []).append(table)
    for ordered, tables in sorted(groups.items()):
        names = ", ".join(sorted(tables))
        lines.append(f"GRANT {', '.join(p.value for p in ordered)} ON {names} TO {quoted};")
    for table, column in sorted(profile.column_updates):
        lines.append(f"GRANT UPDATE ({column}) ON {table} TO {quoted};")
    if profile.sequence_usage:
        names = ", ".join(sorted(profile.sequence_usage))
        lines.append(f"GRANT USAGE ON SEQUENCE {names} TO {quoted};")
    return "\n".join(lines) + "\n"
