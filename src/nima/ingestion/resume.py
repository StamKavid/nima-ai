"""Explicit resume entry point using immutable database configuration."""

from collections.abc import Callable
from uuid import UUID

import httpx

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.collector import _run_boundary, collect
from nima.ingestion.config import Summary
from nima.ingestion.transport import Clock
from nima.sources.base import SourceAdapter
from nima.sources.registry import adapter_from_run
from nima.storage.postgres import CheckpointError
from nima.storage.runs import load_run_options


def resume(
    dsn: str,
    run_id: UUID,
    *,
    client: httpx.Client,
    clock: Clock | None = None,
    attempt_guard: Callable[[], None] | None = None,
    adapter: SourceAdapter | None = None,
) -> Summary:
    options = load_run_options(dsn, run_id)
    if adapter is None:
        # An unregistered source, or a saved query its source cannot read, stops here: before the
        # run is claimed and before any request. It is reported as an unusable saved run.
        try:
            adapter = adapter_from_run(options.connector_version, options.payload)
        except ValueError:
            raise CheckpointError("The saved run's source is unavailable") from None
    with _run_boundary(run_id.hex):
        if not options.archive_root.is_dir():
            raise ArchiveError("The original run archive is unavailable")
        return collect(
            None,
            options.limits,
            Archive(options.archive_root),
            client=client,
            clock=clock,
            database_dsn=dsn,
            resume_id=run_id,
            attempt_guard=attempt_guard,
            adapter=adapter,
        )
