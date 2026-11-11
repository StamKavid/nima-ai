"""Domain workflow identity, dispatch evidence, source leases and enclosing budgets.

https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS
"""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from nima.ingestion.config import CONNECTOR_VERSION, Limits, Query
from nima.ingestion.transport import CollectionStopped
from nima.storage.postgres import (
    NORMALIZER_VERSION,
    CheckpointError,
    Connection,
    MigrationError,
    _connect,
    check_schema,
)
from nima.storage.runs import inspect_run

REQUEST_VERSION = "nima-kimdis-request-v1"


class WorkflowError(Exception):
    def __init__(self, reason: str, retryable: bool = False):
        self.reason, self.retryable = reason, retryable
        super().__init__(reason)


@contextmanager
def _db(dsn: str) -> Iterator[Connection]:
    try:
        check_schema(dsn)
        with _connect(dsn) as connection:
            yield connection
    except MigrationError:
        raise WorkflowError("database_schema") from None
    except CheckpointError:
        raise WorkflowError("run_unavailable") from None
    except psycopg.Error:
        raise WorkflowError("database", True) from None


class RequestGuard:
    def __init__(self, connection: Connection, request: UUID, owner: UUID):
        self.connection, self.request, self.owner = connection, request, owner

    def _budget(self) -> tuple[int, int]:
        row = self.connection.execute(
            "SELECT source_owner, executions, attempts, "
            "coalesce(started_at < clock_timestamp()-interval '30 minutes', false) "
            "FROM nima.workflow_requests WHERE request_id=%s FOR UPDATE",
            (self.request,),
        ).fetchone()
        if row is None or row[0] != self.owner:
            raise WorkflowError("workflow_fenced")
        if row[3]:
            raise WorkflowError("workflow_deadline")
        return cast(int, row[1]), cast(int, row[2])

    def start_execution(self) -> None:
        with self.connection.transaction():
            executions, _ = self._budget()
            if executions >= 4:
                raise WorkflowError("workflow_execution_limit")
            self.connection.execute(
                "UPDATE nima.workflow_requests SET executions=executions+1, status='running', "
                "started_at=coalesce(started_at,clock_timestamp()), updated_at=clock_timestamp() "
                "WHERE request_id=%s",
                (self.request,),
            )

    def reserve_attempt(self) -> None:
        try:
            with self.connection.transaction():
                _, attempts = self._budget()
                if self.connection.execute(
                    "SELECT started_at FROM nima.workflow_requests WHERE request_id=%s",
                    (self.request,),
                ).fetchone() == (None,):
                    raise WorkflowError("workflow_not_started")
                if attempts >= 300:
                    raise WorkflowError("workflow_attempt_limit")
                self.connection.execute(
                    "UPDATE nima.workflow_requests SET attempts=attempts+1, "
                    "updated_at=clock_timestamp() WHERE request_id=%s",
                    (self.request,),
                )
        except WorkflowError as exc:
            raise CollectionStopped(exc.reason) from None


class RequestStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def submit(self, request: UUID, query: Query, root: Path) -> None:
        root = root.absolute()
        if (
            ".." in root.parts
            or len(str(root)) > 4096
            or root.is_file()
            or any(p.is_symlink() for p in (root, *root.parents))
        ):
            raise WorkflowError("archive_invalid")
        parameters = {
            "format_version": REQUEST_VERSION,
            "query": query.payload(),
            "limits": asdict(Limits()),
            "archive_root": str(root),
            "connector_version": CONNECTOR_VERSION,
            "normalizer_version": NORMALIZER_VERSION,
        }
        digest = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
        with _db(self.dsn) as connection, connection.transaction():
            connection.execute(
                "INSERT INTO nima.workflow_requests (request_id,parameters,parameters_sha256) "
                "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (request, Jsonb(parameters), digest),
            )
            row = connection.execute(
                "SELECT parameters,parameters_sha256 FROM nima.workflow_requests "
                "WHERE request_id=%s",
                (request,),
            ).fetchone()
            if row != (parameters, digest):
                raise WorkflowError("request_conflict")

    def options(self, request: UUID) -> tuple[Query, Limits, Path]:
        with _db(self.dsn) as connection:
            row = connection.execute(
                "SELECT parameters,parameters_sha256 FROM nima.workflow_requests "
                "WHERE request_id=%s",
                (request,),
            ).fetchone()
        if row is None:
            raise WorkflowError("request_unavailable")
        p = cast(dict[str, object], row[0])
        try:
            query = cast(dict[str, object], p["query"])
            parsed = Query(
                date.fromisoformat(cast(str, query["dateFrom"])),
                date.fromisoformat(cast(str, query["dateTo"])),
                tuple(cast(list[str], query.get("organizations", []))),
            )
            expected = {
                "format_version": REQUEST_VERSION,
                "query": parsed.payload(),
                "limits": asdict(Limits()),
                "archive_root": p["archive_root"],
                "connector_version": CONNECTOR_VERSION,
                "normalizer_version": NORMALIZER_VERSION,
            }
            if (
                p != expected
                or hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest() != row[1]
            ):
                raise WorkflowError("request_version")
            return parsed, Limits(), Path(cast(str, p["archive_root"]))
        except (ValueError, TypeError, KeyError):
            raise WorkflowError("request_version") from None

    def bind(self, request: UUID, run: UUID) -> None:
        query, limits, root = self.options(request)
        with _db(self.dsn) as connection, connection.transaction():
            actual = connection.execute(
                "SELECT query,settings,connector_version,normalizer_version,archive_root "
                "FROM nima.ingest_runs WHERE run_id=%s",
                (run,),
            ).fetchone()
            if actual != (
                query.payload(),
                asdict(limits),
                CONNECTOR_VERSION,
                NORMALIZER_VERSION,
                str(root),
            ):
                raise WorkflowError("request_conflict")
            row = connection.execute(
                "SELECT run_id FROM nima.workflow_requests WHERE request_id=%s FOR UPDATE",
                (request,),
            ).fetchone()
            if row is None or row[0] not in (None, run):
                raise WorkflowError("request_conflict")
            connection.execute(
                "UPDATE nima.workflow_requests SET run_id=%s WHERE request_id=%s", (run, request)
            )

    def outcome(self, request: UUID, status: str, failure: str | None = None) -> None:
        if status not in {"collected", "projecting", "complete", "partial", "failed", "deferred"}:
            raise ValueError("Unknown workflow outcome")
        if failure is not None and (
            not failure.isascii() or not failure.replace("_", "").isalnum() or len(failure) > 64
        ):
            raise ValueError("Failure must be a fixed reason code")
        with _db(self.dsn) as connection:
            row = connection.execute(
                "UPDATE nima.workflow_requests SET status=%s,failure=%s, "
                "updated_at=clock_timestamp() "
                "WHERE request_id=%s AND status<>'complete' RETURNING 1",
                (status, failure, request),
            ).fetchone()
        if row is None and self.show(request)["status"] != "complete":
            raise WorkflowError("request_unavailable")

    def reserve_projection(self, request: UUID) -> None:
        with _db(self.dsn) as connection:
            row = connection.execute(
                "UPDATE nima.workflow_requests SET projection_batches=projection_batches+1 "
                "WHERE request_id=%s AND projection_batches<100 "
                "AND started_at >= clock_timestamp()-interval '30 minutes' RETURNING 1",
                (request,),
            ).fetchone()
        if row is None:
            raise WorkflowError("projection_budget")

    def show(self, request: UUID) -> dict[str, object]:
        with _db(self.dsn) as connection:
            row = connection.execute(
                """SELECT jsonb_build_object(
                'request_id',w.request_id,'run_id',w.run_id,'status',w.status,'failure',w.failure,
                'executions',w.executions,'attempts',w.attempts,'format_version',%s::text,
                'worker_liveness','unknown',
                'collection_complete',coalesce(r.status IN ('complete','quarantined'),false),
                'normalization_complete',coalesce(r.status='complete',false),
                'dispatches',(SELECT count(*) FROM nima.workflow_dispatches
                    WHERE request_id=w.request_id),
                'unknown_dispatches',(SELECT count(*) FROM nima.workflow_dispatches
                    WHERE request_id=w.request_id AND state IN ('pending','unknown')),
                'engine_run_id',(SELECT engine_run_id FROM nima.workflow_dispatches
                    WHERE request_id=w.request_id AND engine_run_id IS NOT NULL
                    ORDER BY created_at DESC,dispatch_id LIMIT 1))
                FROM nima.workflow_requests w LEFT JOIN nima.ingest_runs r USING(run_id)
                WHERE w.request_id=%s""",
                (REQUEST_VERSION, request),
            ).fetchone()
        if row is None:
            raise WorkflowError("request_unavailable")
        result = cast(dict[str, object], row[0])
        if isinstance(result["run_id"], str):
            try:
                evidence = inspect_run(self.dsn, UUID(result["run_id"]))
            except (psycopg.Error, CheckpointError):
                raise WorkflowError("run_unavailable") from None
            for key in (
                "collection_complete",
                "normalization_complete",
                "pages",
                "records",
                "normalized",
                "quarantined",
            ):
                result[key] = evidence[key]
        return result

    def begin_dispatch(self, request: UUID) -> UUID:
        self.show(request)
        dispatch = uuid4()
        with _db(self.dsn) as connection:
            connection.execute(
                "INSERT INTO nima.workflow_dispatches (dispatch_id,request_id) VALUES (%s,%s)",
                (dispatch, request),
            )
        return dispatch

    def finish_dispatch(self, dispatch: UUID, engine_run: UUID | None) -> None:
        with _db(self.dsn) as connection:
            row = connection.execute(
                "UPDATE nima.workflow_dispatches SET state=%s,engine_run_id=%s, "
                "finished_at=clock_timestamp() WHERE dispatch_id=%s "
                "AND state='pending' RETURNING 1",
                ("unknown" if engine_run is None else "accepted", engine_run, dispatch),
            ).fetchone()
        if row is None:
            raise WorkflowError("dispatch_conflict")

    @contextmanager
    def source_lease(self, request: UUID) -> Iterator[RequestGuard]:
        with _db(self.dsn) as connection:
            if connection.execute("SELECT pg_try_advisory_lock(812344030,1)").fetchone() != (True,):
                raise WorkflowError("source_busy", True)
            owner = uuid4()
            row = connection.execute(
                "UPDATE nima.workflow_requests SET source_owner=%s WHERE request_id=%s RETURNING 1",
                (owner, request),
            ).fetchone()
            if row is None:
                raise WorkflowError("request_unavailable")
            try:
                yield RequestGuard(connection, request, owner)
            finally:
                connection.execute(
                    "UPDATE nima.workflow_requests SET source_owner=NULL "
                    "WHERE request_id=%s AND source_owner=%s",
                    (request, owner),
                )
