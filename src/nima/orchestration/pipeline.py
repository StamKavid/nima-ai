"""Repeat-safe domain stages with no workflow SDK dependency or public endpoint."""

from dataclasses import asdict
from typing import cast
from uuid import UUID

import httpx

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.collector import RunError
from nima.ingestion.resume import resume
from nima.ingestion.transport import Clock, SystemClock
from nima.orchestration.events import StageEvents, workflow_stage
from nima.projections.worker import PROJECTION_VERSION, ProjectionFailure, drain
from nima.storage.runs import RunStore, inspect_run, load_run_options
from nima.storage.workflows import RequestStore, WorkflowError, _db


def _run(store: RequestStore, request: UUID, events: StageEvents) -> UUID:
    run = store.show(request)["run_id"]
    if not isinstance(run, str):
        raise WorkflowError("request_unprepared")
    selected = UUID(run)
    events.bind_run(selected)
    return selected


def prepare_request(dsn: str, request: UUID) -> dict[str, object]:
    with workflow_stage("prepare", request) as events:
        store = RequestStore(dsn)
        query, limits, root = store.options(request)
        with store.source_lease(request):
            status = store.show(request)
            existing = status["run_id"]
            if isinstance(existing, str):
                run = UUID(existing)
                saved = load_run_options(dsn, run)
                if (saved.payload, saved.limits, saved.archive_root) != (
                    query.payload(),
                    limits,
                    root,
                ):
                    raise WorkflowError("request_conflict")
            else:
                try:
                    archive = Archive(root)
                    path = archive.start_run(
                        {
                            "format_version": 1,
                            "request_version": status["format_version"],
                            "request_id": str(request),
                            "status": "prepared",
                            "query": query.payload(),
                            "limits": asdict(limits),
                        }
                    )
                    run = UUID(path.name)
                    writer = RunStore(dsn, archive, run, limits)
                    with writer.lease():
                        writer.begin(query)
                    store.bind(request, run)  # Mapping is durable before any source call.
                except (OSError, ArchiveError):
                    raise WorkflowError("archive_invalid") from None
        events.bind_run(run)
        return {"request_id": str(request), "run_id": str(run)}


def collect_request(
    dsn: str, request: UUID, *, client: httpx.Client, clock: Clock | None = None
) -> dict[str, object]:
    with workflow_stage("collect", request) as events:
        store = RequestStore(dsn)
        run = _run(store, request, events)
        clock = SystemClock() if clock is None else clock
        with store.source_lease(request) as guard:
            stored = inspect_run(dsn, run)
            if not stored["collection_complete"]:
                try:
                    guard.start_execution()
                except WorkflowError as exc:
                    store.outcome(request, "deferred", exc.reason)
                    raise
            first = True

            def reserve() -> None:
                nonlocal first
                if first:
                    # Serial workflow invocations also leave a pacing gap between runs.
                    clock.sleep(3)
                    first = False
                guard.reserve_attempt()

            try:
                summary = resume(dsn, run, client=client, clock=clock, attempt_guard=reserve)
            except RunError as exc:
                store.outcome(request, "deferred", exc.reason)
                raise WorkflowError(exc.reason, exc.reason in {"database", "run_busy"}) from None
        if not summary.collection_complete or not summary.normalization_complete:
            reason = summary.failure or "quarantined"
            store.outcome(
                request, "deferred" if reason.startswith("workflow_") else "partial", reason
            )
            raise WorkflowError(reason, reason in {"transport", "retry_exhausted"})
        store.outcome(request, "collected")
        return {
            "run_id": str(run),
            "collection_complete": True,
            "normalization_complete": True,
            "pages": summary.pages,
            "records": summary.records,
            "attempts": summary.attempts,
        }


def project_request(dsn: str, request: UUID) -> dict[str, object]:
    with workflow_stage("project", request) as events:
        store = RequestStore(dsn)
        run = _run(store, request, events)
        if not inspect_run(dsn, run)["normalization_complete"]:
            raise WorkflowError("collection_incomplete")
        counts = _projection_counts(dsn, run)
        if counts[0] == counts[1]:
            return {
                "projection_version": PROJECTION_VERSION,
                "processed_events": 0,
                "remaining_events": 0,
                "status": "complete",
            }
        store.outcome(request, "projecting")
        try:
            store.reserve_projection(request)
        except WorkflowError as exc:
            store.outcome(request, "deferred", exc.reason)
            raise
        try:
            result = drain(dsn, max_events=100, run_id=run)
            if not result["processed_events"] and result["remaining_events"]:
                store.outcome(request, "deferred", "projection_busy")
                raise WorkflowError("projection_busy", True)
            return result
        except ProjectionFailure as exc:
            store.outcome(request, "deferred", exc.reason)
            raise WorkflowError(exc.reason, exc.reason == "database") from None


def _projection_counts(dsn: str, run: UUID) -> tuple[int, int]:
    with _db(dsn) as connection:
        row = connection.execute(
            """SELECT count(*),count(r.observation_id)
            FROM nima.observations o LEFT JOIN nima.projection_receipts r
            ON r.observation_id=o.observation_id AND r.projection_version=%s
            WHERE o.run_id=%s""",
            (PROJECTION_VERSION, run),
        ).fetchone()
    if row is None:
        raise WorkflowError("projection_incomplete")
    return cast(tuple[int, int], row)


def finalize_request(dsn: str, request: UUID) -> dict[str, object]:
    with workflow_stage("finalize", request) as events:
        store = RequestStore(dsn)
        run = _run(store, request, events)
        observed = inspect_run(dsn, run)
        if not observed["collection_complete"] or not observed["normalization_complete"]:
            raise WorkflowError("collection_incomplete")
        counts = _projection_counts(dsn, run)
        if counts[0] != counts[1]:
            raise WorkflowError("projection_incomplete")
        store.outcome(request, "complete")
        return store.show(request)
