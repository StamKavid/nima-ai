"""One bounded collection run with explicit evidence and completeness checks."""

from dataclasses import asdict
from datetime import UTC, datetime

import httpx

from nima.ingestion.archive import Archive
from nima.ingestion.config import CONNECTOR_VERSION, ENDPOINT, SOURCE, Limits, Query, Summary
from nima.ingestion.transport import Clock, CollectionStopped, Session, SystemClock, retry_delay
from nima.sources.kimdis import InvalidRecord, normalize_page

RETRY_STATUSES = {408, 429, 500, 502, 503, 504}


def collect(
    query: Query,
    limits: Limits,
    archive: Archive,
    *,
    client: httpx.Client,
    clock: Clock | None = None,
) -> Summary:
    """Archive before parsing; never claim a snapshot or automatic crash recovery.

    The monotonic budget is checked between waits/chunks/pages, and each HTTP
    inactivity timeout is capped by the remaining budget. Blocking I/O may take
    one inactivity timeout beyond it; this is not an OS-enforced hard deadline.
    """
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

    def save() -> None:
        summary.attempts = len(session.responses)
        manifest["summary"] = asdict(summary)
        archive.write_manifest(run, manifest)

    def fetch(page: int) -> bytes:
        for attempt in range(1, limits.max_attempts + 1):
            retry_after = None
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
            if page.number != number or (expected_shape is not None and shape != expected_shape):
                raise CollectionStopped("pagination_changed")
            expected_shape = shape
            summary.expected_records, summary.expected_pages = page.total_records, page.total_pages
            for source_id in page.source_ids:
                summary.duplicate_ids += int(source_id in seen)
                seen.add(source_id)
            summary.unidentified += page.record_count - len(page.source_ids)
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
                if summary.duplicate_ids or summary.unidentified or len(seen) != page.total_records:
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
    return summary
