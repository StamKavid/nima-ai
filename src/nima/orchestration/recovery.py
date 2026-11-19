"""Explicit same-request child dispatch; policy/source locks span the control RPC."""

from uuid import UUID

from nima.orchestration.config import local_config
from nima.orchestration.dispatch import dispatch_request
from nima.storage.refresh import RefreshStore
from nima.storage.workflows import WorkflowError, source_session


async def recover_child(policy: UUID, request: UUID) -> dict[str, object]:
    config = local_config()
    with RefreshStore(config.dsn).lease(policy) as session:
        if not session.enabled():
            raise WorkflowError("policy_paused")
        row = session.connection.execute(
            "SELECT w.dispatch_state FROM nima.refresh_windows w "
            "JOIN nima.refresh_cycles c USING(cycle_id,policy_id) "
            "WHERE w.policy_id=%s AND w.request_id=%s "
            "AND c.completed_at IS NULL AND w.completed_at IS NULL",
            (policy, request),
        ).fetchone()
        if row is None or row[0] not in {"sending", "accepted"}:
            raise WorkflowError("recovery_child")
        with source_session(config.dsn):
            result = await dispatch_request(request, recovery=True)
            session.dispatch_state(request, "accepted")
        return {"policy_id": str(policy), **result}
