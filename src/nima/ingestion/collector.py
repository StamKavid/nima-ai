"""One bounded collection run with explicit evidence and completeness checks."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import httpx
import psycopg

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.config import ENDPOINT, SOURCE, Limits, Query, Summary
from nima.ingestion.transport import Clock, CollectionStopped, Session, SystemClock, retry_delay
from nima.sources.base import (
    NormalizedPage,
    NormalizedRecord,
    PageIssue,
    SourceAdapter,
    SourcePageError,
)
from nima.sources.registry import default_adapter
from nima.storage.postgres import CheckpointError, check_schema
from nima.storage.runs import RunBusy, RunStore

RETRY_STATUSES = {408, 429, 500, 502, 503, 504}


class RunError(RuntimeError):
    def __init__(self, run_id: str, reason: str):
        super().__init__(reason)
        self.run_id, self.reason = run_id, reason


@contextmanager
def _run_boundary(run_id: str) -> Iterator[None]:
    try:
        yield
    except ArchiveError:
        raise RunError(run_id, "archive_invalid") from None
    except OSError:
        raise RunError(run_id, "archive_io") from None
    except RunBusy:
        raise RunError(run_id, "run_busy") from None
    except (psycopg.Error, CheckpointError):
        raise RunError(run_id, "database") from None


def _evidence(page: NormalizedPage, pointer: str) -> dict[str, str]:
    return {"response_sha256": page.response_sha256, "json_pointer": pointer}


def _normalized_row(page: NormalizedPage, record: NormalizedRecord) -> dict[str, object]:
    """The archive's normalized.jsonl row: the stored record followed by its evidence."""
    return {**record.normalized, "evidence": _evidence(page, record.evidence_pointer)}


def _issue_row(page: NormalizedPage, issue: PageIssue) -> dict[str, object]:
    return {"reason": issue.reason, "evidence": _evidence(page, issue.evidence_pointer)}


def collect(
    query: Query,
    limits: Limits,
    archive: Archive,
    *,
    client: httpx.Client,
    clock: Clock | None = None,
    database_dsn: str | None = None,
    resume_id: UUID | None = None,
    attempt_guard: Callable[[], None] | None = None,
    adapter: SourceAdapter | None = None,
) -> Summary:
    """Archive before parsing; never claim a snapshot or automatic crash recovery.

    The monotonic budget is checked between waits/chunks/pages, and each HTTP
    inactivity timeout is capped by the remaining budget. Blocking I/O may take
    one inactivity timeout beyond it; this is not an OS-enforced hard deadline.
    """
    if resume_id is not None and database_dsn is None:
        raise ValueError("Resume requires PostgreSQL")
    if database_dsn is not None:
        check_schema(database_dsn)
    source = adapter if adapter is not None else default_adapter(query)
    session = Session(client, archive, limits, clock if clock is not None else SystemClock())
    session.attempt_guard = attempt_guard
    summary = Summary()
    manifest: dict[str, object] = {
        "format_version": 1,
        "connector_version": source.connector_version,
        "endpoint": ENDPOINT,
        "query": query.payload(),
        "limits": asdict(limits),
        "source": SOURCE,
        "license": "CC BY 4.0",
        "started_at": datetime.now(UTC).isoformat(),
        "responses": session.responses,
        "summary": asdict(summary),
    }
    if resume_id is None:
        run = archive.start_run(manifest)
        summary.run_id = run.name
    else:
        run = None
        summary.run_id = resume_id.hex
    journal = (
        RunStore(database_dsn, archive, UUID(summary.run_id), limits, source)
        if database_dsn is not None
        else None
    )
    with _run_boundary(summary.run_id), journal.lease() if journal else nullcontext():
        if journal is not None:
            if resume_id is None:
                journal.begin(query)
            else:
                journal.takeover(query)
            session.journal = journal
        attempt_offset = 0

        def save() -> None:
            summary.attempts = attempt_offset + len(session.responses)
            if run is not None:
                manifest["summary"] = asdict(summary)
                archive.write_manifest(run, manifest)

        def fetch(page: int) -> bytes:
            for attempt in range(1, limits.max_attempts + 1):
                retry_after = None
                status = None
                try:
                    raw, status, retry_after = session.request(query, page, attempt)
                except CollectionStopped as exc:
                    if str(exc) != "transport":
                        raise
                else:
                    if status == 200:
                        return raw
                    if status not in RETRY_STATUSES:
                        raise CollectionStopped(f"http_{status}")
                finally:
                    save()
                if attempt == limits.max_attempts:
                    raise CollectionStopped("retry_exhausted")
                delay = retry_delay(retry_after, attempt)
                if status == 429 and retry_after is None:
                    delay = 30.0 * attempt
                if delay > limits.max_retry_delay:
                    raise CollectionStopped("retry_delay")
                session.wait(delay)
            raise AssertionError("Validated attempt limit is positive")

        seen: set[str] = set()
        expected_shape: tuple[int, int, int] | None = None

        def decode(raw: bytes) -> NormalizedPage:
            try:
                return source.normalize_page(raw, max_bytes=limits.max_bytes)
            except SourcePageError as exc:
                raise CollectionStopped("invalid_page") from exc

        def accept(raw: bytes, number: int) -> NormalizedPage:
            nonlocal expected_shape
            page = decode(raw)
            shape = (page.total_records, page.total_pages, page.size)
            if page.number != number or (expected_shape is not None and shape != expected_shape):
                raise CollectionStopped("pagination_changed")
            expected_shape = shape
            summary.expected_records, summary.expected_pages = page.total_records, page.total_pages
            for source_id in page.source_ids:
                summary.duplicate_ids += int(source_id in seen)
                seen.add(source_id)
            summary.unidentified += page.record_count - len(page.source_ids)
            if journal is not None and summary.duplicate_ids:
                raise CollectionStopped("identity_coverage")
            return page

        def count(page: NormalizedPage) -> None:
            summary.pages += 1
            summary.records += page.record_count
            summary.normalized += len(page.records)
            summary.quarantined += len(page.issues)

        def complete(page: NormalizedPage) -> bool:
            if not page.last:
                return False
            if (
                summary.duplicate_ids
                or summary.unidentified
                or len(seen) != page.total_records
                or summary.records != page.total_records
            ):
                raise CollectionStopped("identity_coverage")
            summary.collection_complete = True
            summary.normalization_complete = summary.quarantined == 0
            summary.status = "complete" if summary.normalization_complete else "quarantined"
            return True

        def signature(page: NormalizedPage) -> tuple[object, ...]:
            return (
                page.number,
                page.size,
                page.total_records,
                page.total_pages,
                page.last,
                page.record_hashes,
            )

        save()
        try:
            start = 0
            pending: tuple[bytes, datetime] | None = None
            done = False
            if resume_id is not None and journal is not None:
                start, attempt_offset, stored = journal.snapshot()
                if start != len(stored) or start > limits.max_pages:
                    raise CheckpointError("Checkpoint does not match committed pages")
                prefix = []
                for number, digest, _ in stored:
                    if number != summary.pages:
                        raise CheckpointError("Committed pages contain a gap")
                    page = accept(archive.read(digest, max_bytes=limits.max_bytes), number)
                    count(page)
                    prefix.append((number, signature(page)))
                    session.remaining()
                done = bool(stored) and complete(page)
                if not done:
                    session.phase = "verify"
                    for number, previous in prefix:
                        if signature(decode(fetch(number))) != previous:
                            raise CollectionStopped("source_changed")
                    saved = journal.pending(start)
                    if saved is not None:
                        raw = archive.read(saved[0], max_bytes=limits.max_bytes)
                        previous_page = decode(raw)
                        if previous_page.number != start:
                            raise CollectionStopped("invalid_page")
                        if signature(decode(fetch(start))) != signature(previous_page):
                            raise CollectionStopped("source_changed")
                        pending = raw, saved[1]
                    session.phase = "collect"
            if not done:
                for number in range(start, limits.max_pages):
                    if pending is not None:
                        raw, observed_at = pending
                        pending = None
                    else:
                        raw = fetch(number)
                        observed_at = datetime.fromisoformat(
                            str(session.responses[-1]["observed_at"])
                        )
                    page = accept(raw, number)
                    if journal is not None:
                        journal.commit_page(
                            UUID(summary.run_id),
                            raw,
                            observed_at=observed_at,
                            owner=journal.owner,
                            max_bytes=limits.max_bytes,
                        )
                    if run is not None:
                        archive.append(
                            run, "normalized", [_normalized_row(page, r) for r in page.records]
                        )
                        archive.append(
                            run, "quarantine", [_issue_row(page, i) for i in page.issues]
                        )
                    count(page)
                    session.remaining()
                    save()
                    if complete(page):
                        break
                else:
                    raise CollectionStopped("page_limit")
        except CollectionStopped as exc:
            summary.status, summary.failure = "failed", str(exc)
        except KeyboardInterrupt:
            summary.status, summary.failure = "interrupted", "interrupted"
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        save()
        if journal is not None:
            journal.finish(summary)
        return summary
