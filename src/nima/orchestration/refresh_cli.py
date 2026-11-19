"""Operator refresh controls; SQL-only inspection never imports the workflow SDK."""

import asyncio
import json
import os
from datetime import UTC, date, datetime
from uuid import UUID

from nima.orchestration.config import local_config
from nima.orchestration.refresh import Policy, business_date
from nima.storage.refresh import RefreshStore
from nima.storage.refresh_progress import show
from nima.storage.workflows import WorkflowError


def run(
    operation: str,
    policy_id: UUID,
    *,
    start: date | None = None,
    buyers: tuple[str, ...] = (),
    as_of: date | None = None,
    request: UUID | None = None,
    reason: str | None = None,
    successor: UUID | None = None,
    authorize_new_budgets: bool = False,
) -> int:
    try:
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if not dsn.strip():
            raise WorkflowError("configuration")
        store = RefreshStore(dsn)
        day = business_date(datetime.now(UTC))
        if operation == "create":
            config = local_config()
            if start is None:
                raise WorkflowError("configuration")
            store.create(policy_id, Policy(start, buyers, config.archive_root))
        elif operation == "plan":
            print(json.dumps(store.plan(policy_id, as_of or day), allow_nan=False))
            return 0
        elif operation == "supersede":
            from nima.storage.refresh_succession import supersede

            if successor is None:
                raise WorkflowError("configuration")
            result = supersede(
                dsn, policy_id, successor, authorize_new_budgets=authorize_new_budgets
            )
            print(json.dumps(result, allow_nan=False))
            return 0
        elif operation == "retire":
            from nima.storage.refresh_lifecycle import retire

            if reason is None:
                raise WorkflowError("configuration")
            print(json.dumps(retire(dsn, policy_id, reason), allow_nan=False))
            return 0
        elif operation == "recover":
            from nima.orchestration.recovery import recover_child

            if request is None:
                raise WorkflowError("configuration")
            print(json.dumps(asyncio.run(recover_child(policy_id, request)), allow_nan=False))
            return 0
        elif operation in {"enable", "pause", "tick"}:
            from nima.orchestration.refresh_control import change_schedule, tick

            if operation == "tick":
                result = asyncio.run(tick(policy_id, day))
                print(json.dumps(result, allow_nan=False))
                return 0
            asyncio.run(change_schedule(policy_id, enabled=operation == "enable"))
        elif operation != "show":
            raise WorkflowError("configuration")
        result = show(store, policy_id, day)
    except WorkflowError as exc:
        print(json.dumps({"policy_id": str(policy_id), "status": "failed", "failure": exc.reason}))
        return 2 if exc.reason == "configuration" else 1
    except (ValueError, OSError):
        print(json.dumps({"status": "failed", "failure": "configuration"}))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"policy_id": str(policy_id), "status": "interrupted"}))
        return 130
    print(json.dumps(result, allow_nan=False))
    return 0
