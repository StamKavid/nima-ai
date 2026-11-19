"""Append-only retirement decisions; no engine, archive or source configuration reads."""

from datetime import datetime
from typing import cast
from uuid import UUID

from nima.storage.connection import Connection
from nima.storage.refresh_lock import policy_session
from nima.storage.workflows import WorkflowError

REASONS = ("budget_exhausted", "processing_incompatible", "operator_stop")


def policy_links(connection: Connection, policy: UUID) -> list[dict[str, object]]:
    """Unique endpoints bound direct lineage to two records; never traverse a chain."""
    rows = connection.execute(
        "SELECT s.predecessor_id,s.successor_id,s.successor_configuration_sha256,"
        "s.budget_profile,s.authorized_at,s.new_budgets_authorized,p.state "
        "FROM nima.refresh_successions s JOIN nima.refresh_policies p "
        "ON p.policy_id=s.successor_id "
        "WHERE s.predecessor_id=%s OR s.successor_id=%s ORDER BY s.predecessor_id",
        (policy, policy),
    ).fetchall()
    return [
        {
            "predecessor_id": str(row[0]),
            "successor_id": str(row[1]),
            "successor_configuration_sha256": row[2],
            "budget_profile": row[3],
            "authorized_at": cast(datetime, row[4]).isoformat(),
            "new_budgets_authorized": row[5],
            "successor_state": row[6],
        }
        for row in rows
    ]


def retirement(connection: Connection, policy: UUID) -> dict[str, object] | None:
    row = connection.execute(
        "SELECT reason,recorded_at FROM nima.refresh_retirements WHERE policy_id=%s", (policy,)
    ).fetchone()
    return (
        None
        if row is None
        else {"reason": row[0], "recorded_at": cast(datetime, row[1]).isoformat()}
    )


def retire(dsn: str, policy: UUID, reason: str) -> dict[str, object]:
    if not isinstance(policy, UUID):
        raise WorkflowError("configuration")
    if not isinstance(reason, str) or reason not in REASONS:
        raise WorkflowError("retirement_reason")
    with policy_session(dsn, policy) as c, c.transaction():
        c.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        row = c.execute(
            "SELECT state FROM nima.refresh_policies WHERE policy_id=%s FOR UPDATE", (policy,)
        ).fetchone()
        if row is None:
            raise WorkflowError("policy_unavailable")
        previous = retirement(c, policy)
        if previous is not None and previous["reason"] != reason:
            raise WorkflowError("retirement_conflict")
        if previous is None:
            c.execute(
                "INSERT INTO nima.refresh_retirements(policy_id,reason) VALUES (%s,%s)",
                (policy, reason),
            )
        recorded = retirement(c, policy)
        state = c.execute(
            "SELECT state FROM nima.refresh_policies WHERE policy_id=%s", (policy,)
        ).fetchone()
        if recorded is None or state is None:
            raise WorkflowError("policy_unavailable")
        return {
            "version": "nima-refresh-retirement-v1",
            "policy_id": str(policy),
            "retired": True,
            **recorded,
            "reused": previous is not None,
            "schedule_reconciliation": "required" if state[0] == "pending" else "last_acknowledged",
        }
