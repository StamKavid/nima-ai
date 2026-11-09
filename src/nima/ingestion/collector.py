"""One bounded collection run with explicit evidence and completeness checks."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import httpx
import psycopg

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.config import CONNECTOR_VERSION, ENDPOINT, SOURCE, Limits, Query, Summary
from nima.ingestion.transport import Clock, CollectionStopped, Session, SystemClock, retry_delay
from nima.sources.kimdis import InvalidRecord, normalize_page
from nima.storage.postgres import CheckpointError, check_schema
from nima.storage.runs import RunStore

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
    except (psycopg.Error, CheckpointError):
        raise RunError(run_id, "database") from None


def collect(
    query: Query,
    limits: Limits,
    archive: Archive,
    *,
    client: httpx.Client,
    clock: Clock | None = None,
    database_dsn: str | None = None,
) -> Summary:
    """Archive before parsing; never claim a snapshot or automatic crash recovery.

    The monotonic budget is checked between waits/chunks/pages, and each HTTP
    inactivity timeout is capped by the remaining budget. Blocking I/O may take
    one inactivity timeout beyond it; this is not an OS-enforced hard deadline.
    """
    if database_dsn is not None:
        check_schema(database_dsn)
    session = Session(client, archive, limits, clock if clock is not None else SystemClock())
    summary = Summary()
    manifest: dict[str, object] = {
        "format_version": 1,
        "connector_version": CONNECTOR_VERSION,
        "endpoint": ENDPOINT,
        "query": query.payload(),
        "limits": asdict(limits),
        "source": SOURCE,
        "license": "CC BY 4.0",
        "started_at": datetime.now(UTC).isoformat(),
        "responses": session.responses,
        "summary": asdict(summary),
    }
    run = archive.start_run(manifest)
    summary.run_id = run.name

    with _run_boundary(summary.run_id):
        journal = None
        if database_dsn is not None:
            journal = RunStore(database_dsn, archive, UUID(summary.run_id), limits)
            journal.begin(query)
            session.journal = journal

        def save() -> None:
            summary.attempts = len(session.responses)
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
        save()
        try:
            for number in range(limits.max_pages):
                raw = fetch(number)
                try:
                    page = normalize_page(raw, max_bytes=limits.max_bytes)
                except InvalidRecord as exc:
                    raise CollectionStopped("invalid_page") from exc
                shape = (page.total_records, page.total_pages, page.size)
                if page.number != number or (
                    expected_shape is not None and shape != expected_shape
                ):
                    raise CollectionStopped("pagination_changed")
                expected_shape = shape
                summary.expected_records, summary.expected_pages = (
                    page.total_records,
                    page.total_pages,
                )
                for source_id in page.source_ids:
                    summary.duplicate_ids += int(source_id in seen)
                    seen.add(source_id)
                summary.unidentified += page.record_count - len(page.source_ids)
                if journal is not None:
                    if summary.duplicate_ids:
                        raise CollectionStopped("identity_coverage")
                    journal.commit_page(
                        UUID(summary.run_id),
                        raw,
                        observed_at=datetime.fromisoformat(
                            str(session.responses[-1]["observed_at"])
                        ),
                        owner=journal.owner,
                        max_bytes=limits.max_bytes,
                    )
                normalized = []
                for contract in page.contracts:
                    row = asdict(contract)
                    for field in ("net_amount", "gross_amount"):
                        if row[field] is not None:
                            row[field] = str(row[field])
                    normalized.append(row)
                archive.append(run, "normalized", normalized)
                archive.append(run, "quarantine", [asdict(issue) for issue in page.issues])
                summary.pages += 1
                summary.records += page.record_count
                summary.normalized += len(page.contracts)
                summary.quarantined += len(page.issues)
                session.remaining()
                save()
                if page.last:
                    if (
                        summary.duplicate_ids
                        or summary.unidentified
                        or len(seen) != page.total_records
                    ):
                        raise CollectionStopped("identity_coverage")
                    summary.collection_complete = True
                    summary.normalization_complete = summary.quarantined == 0
                    summary.status = "complete" if summary.normalization_complete else "quarantined"
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
