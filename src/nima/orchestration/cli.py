"""Operator-only submission and redacted inspection; delivery acceptance is not completion."""

import asyncio
import json
import os
from datetime import date
from uuid import UUID

from nima.ingestion.config import Query
from nima.orchestration.config import local_config
from nima.orchestration.dispatch import dispatch_request
from nima.storage.workflows import RequestStore, WorkflowError


def run(
    operation: str,
    request: UUID,
    *,
    start: date | None = None,
    end: date | None = None,
    buyers: tuple[str, ...] = (),
) -> int:
    try:
        if operation == "show":
            dsn = os.environ.get("NIMA_DATABASE_URL", "")
            if not dsn.strip():
                raise WorkflowError("configuration")
            result = RequestStore(dsn).show(request)
        else:
            config = local_config()
            if operation == "submit":
                if start is None or end is None:
                    raise WorkflowError("configuration")
                RequestStore(config.dsn).submit(
                    request, Query(start, end, buyers), config.archive_root
                )
            result = asyncio.run(dispatch_request(request))
    except WorkflowError as exc:
        print(json.dumps({"status": "failed", "request_id": str(request), "failure": exc.reason}))
        return 2 if exc.reason == "configuration" else 1
    except ValueError:
        print(json.dumps({"status": "failed", "failure": "configuration"}))
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted", "request_id": str(request)}))
        return 130
    print(json.dumps(result, allow_nan=False))
    return 0
