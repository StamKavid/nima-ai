"""Atomic new-budget authorization for a retired policy's fresh paused successor."""

from uuid import UUID

from psycopg.types.json import Jsonb

from nima.intent import IntentError, refresh_intent
from nima.orchestration.refresh import Policy
from nima.storage.connection import Connection
from nima.storage.refresh import configuration_digest, policy_parameters
from nima.storage.refresh_lifecycle import policy_links, retirement
from nima.storage.refresh_lock import policy_session
from nima.storage.workflows import WorkflowError

BUDGET_PROFILE = "nima-refresh-budgets-v1"


def _outgoing(c: Connection, predecessor: UUID) -> dict[str, object] | None:
    return next(
        (r for r in policy_links(c, predecessor) if r["predecessor_id"] == str(predecessor)), None
    )


def supersede(
    dsn: str, predecessor: UUID, successor: UUID, *, authorize_new_budgets: bool
) -> dict[str, object]:
    if not isinstance(predecessor, UUID) or not isinstance(successor, UUID):
        raise WorkflowError("configuration")
    if authorize_new_budgets is not True:
        raise WorkflowError("succession_authorization")
    if predecessor == successor:
        raise WorkflowError("succession_conflict")
    with policy_session(dsn, predecessor) as c, c.transaction():
        c.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        row = c.execute(
            "SELECT configuration,configuration_sha256 FROM nima.refresh_policies "
            "WHERE policy_id=%s FOR UPDATE",
            (predecessor,),
        ).fetchone()
        if row is None:
            raise WorkflowError("policy_unavailable")
        if retirement(c, predecessor) is None:
            raise WorkflowError("succession_not_retired")
        previous = _outgoing(c, predecessor)
        if previous is not None:
            if previous["successor_id"] != str(successor):
                raise WorkflowError("succession_conflict")
            return {"version": "nima-refresh-succession-v1", **previous, "reused": True}
        try:
            saved = refresh_intent(row[0], row[1])
        except IntentError:
            raise WorkflowError("policy_invalid") from None
        try:
            value = policy_parameters(Policy(saved.start, saved.buyers, saved.root))
        except (ValueError, OSError):
            raise WorkflowError("archive_invalid") from None
        digest = configuration_digest(value)
        try:
            refresh_intent(value, digest)
        except IntentError:
            raise WorkflowError("succession_profile") from None
        inserted = c.execute(
            "INSERT INTO nima.refresh_policies "
            "(policy_id,configuration,configuration_sha256,start_date) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING 1",
            (successor, Jsonb(value), digest, saved.start),
        ).fetchone()
        if inserted is None:
            raise WorkflowError("succession_conflict")
        c.execute(
            "INSERT INTO nima.refresh_events(policy_id,state) VALUES (%s,'paused')", (successor,)
        )
        c.execute(
            "INSERT INTO nima.refresh_successions "
            "(predecessor_id,successor_id,new_budgets_authorized,budget_profile) "
            "VALUES (%s,%s,true,%s)",
            (predecessor, successor, BUDGET_PROFILE),
        )
        recorded = _outgoing(c, predecessor)
        if recorded is None:
            raise WorkflowError("policy_unavailable")
        return {"version": "nima-refresh-succession-v1", **recorded, "reused": False}
