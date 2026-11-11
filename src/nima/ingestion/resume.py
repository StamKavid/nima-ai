"""Explicit resume entry point using immutable database configuration."""

from collections.abc import Callable
from uuid import UUID

import httpx

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.collector import _run_boundary, collect
from nima.ingestion.config import Summary
from nima.ingestion.transport import Clock
from nima.storage.runs import load_options


def resume(
    dsn: str,
    run_id: UUID,
    *,
    client: httpx.Client,
    clock: Clock | None = None,
    attempt_guard: Callable[[], None] | None = None,
) -> Summary:
    query, limits, root = load_options(dsn, run_id)
    with _run_boundary(run_id.hex):
        if not root.is_dir():
            raise ArchiveError("The original run archive is unavailable")
        return collect(
            query,
            limits,
            Archive(root),
            client=client,
            clock=clock,
            database_dsn=dsn,
            resume_id=run_id,
            attempt_guard=attempt_guard,
        )
