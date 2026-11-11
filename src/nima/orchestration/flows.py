"""Prefect tasks carry domain request IDs and redacted summaries only.

https://docs.prefect.io/v3/how-to-guides/workflows/retries
https://docs.prefect.io/v3/how-to-guides/deployment_infra/run-flows-in-local-processes
"""

from collections.abc import Callable
from functools import partial
from uuid import UUID

import httpx
import psycopg
from prefect import flow, task
from prefect.cache_policies import NO_CACHE
from prefect.client.schemas.objects import State

from nima.ingestion.archive import ArchiveError
from nima.orchestration.config import local_config
from nima.orchestration.pipeline import (
    collect_request,
    finalize_request,
    prepare_request,
    project_request,
)
from nima.storage.postgres import CheckpointError, MigrationError
from nima.storage.workflows import WorkflowError


def _retry(task: object, task_run: object, state: object) -> bool:
    if not isinstance(state, State):
        return False
    error = state.result(raise_on_failure=False)
    return isinstance(error, WorkflowError) and error.retryable


def _safe(action: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        return action()
    except psycopg.Error:
        raise WorkflowError("database", True) from None
    except (CheckpointError, MigrationError):
        raise WorkflowError("run_unavailable") from None
    except (OSError, ArchiveError):
        raise WorkflowError("archive_invalid") from None


def _id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise WorkflowError("request_invalid") from None


@task(
    name="prepare-request",
    retries=3,
    retry_delay_seconds=2,
    retry_condition_fn=_retry,
    persist_result=False,
    cache_policy=NO_CACHE,
    log_prints=False,
)
def prepare_task(request_id: str) -> dict[str, object]:
    return _safe(partial(prepare_request, local_config().dsn, _id(request_id)))


@task(
    name="collect-or-resume",
    retries=3,
    retry_delay_seconds=2,
    retry_condition_fn=_retry,
    persist_result=False,
    cache_policy=NO_CACHE,
    log_prints=False,
)
def collect_task(request_id: str) -> dict[str, object]:
    with httpx.Client() as client:
        return _safe(partial(collect_request, local_config().dsn, _id(request_id), client=client))


@task(
    name="project-request",
    retries=3,
    retry_delay_seconds=2,
    retry_condition_fn=_retry,
    persist_result=False,
    cache_policy=NO_CACHE,
    log_prints=False,
)
def project_task(request_id: str) -> dict[str, object]:
    return _safe(partial(project_request, local_config().dsn, _id(request_id)))


@task(
    name="reconcile-request",
    retries=3,
    retry_delay_seconds=2,
    retry_condition_fn=_retry,
    persist_result=False,
    cache_policy=NO_CACHE,
    log_prints=False,
)
def reconcile_task(request_id: str) -> dict[str, object]:
    return _safe(partial(finalize_request, local_config().dsn, _id(request_id)))


@flow(
    name="nima-kimdis",
    version="nima-kimdis-flow-v1",
    retries=0,
    persist_result=False,
    log_prints=False,
)
def kimdis_flow(request_id: str) -> dict[str, object]:
    prepare_task(request_id)
    collect_task(request_id)
    for batch in range(100):
        result = project_task.with_options(name=f"project-batch-{batch:03d}")(request_id)
        if result["remaining_events"] == 0:
            break
    else:
        raise WorkflowError("projection_budget")
    return reconcile_task(request_id)
