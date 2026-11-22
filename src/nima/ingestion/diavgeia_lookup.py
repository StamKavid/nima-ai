"""Archive-first lookup of a few explicit Diavgeia ADAs reduced to counts by decision type.

The source rules (URL, response check, manifest facts) are passed in; the engine imports no source.

This answers one question (what type of decision is a cited ADA) for at most 15 decisions. It
stops on any status other than 200 or 404, never retries and never follows a redirect.
"""

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.transport import Clock, CollectionStopped, SystemClock

MAX_ADAS = 15
MAX_BODY = 1024 * 1024


@dataclass(frozen=True)
class LookupLimits:
    max_bytes: int = MAX_BODY
    requests_per_minute: float = 20
    request_timeout: float = 20
    run_timeout: float = 300

    def __post_init__(self) -> None:
        if type(self.max_bytes) is not int or not 1 <= self.max_bytes <= MAX_BODY:
            raise ValueError("Invalid byte budget")
        for value, ceiling in (
            (self.requests_per_minute, 20),
            (self.request_timeout, 60),
            (self.run_timeout, 300),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 < value <= ceiling
            ):
                raise ValueError("Invalid rate or time budget")


@dataclass
class LookupSummary:
    run_id: str = ""
    status: str = "running"
    requested: int = 0
    found: int = 0
    not_found: int = 0
    quarantined: int = 0
    types: dict[str, int] = field(default_factory=dict)
    collection_complete: bool = False
    failure: str | None = None


@dataclass(frozen=True)
class LookupSource:
    """What the engine needs from a source; the caller supplies it so the engine imports none."""

    url_for: Callable[[str], str]
    summarize: Callable[[bytes, str, int], dict[str, str | None]]
    invalid: type[ValueError]
    manifest: dict[str, object]


def lookup(
    adas: tuple[str, ...],
    archive_dir: Path,
    *,
    source: LookupSource,
    client: httpx.Client,
    limits: LookupLimits | None = None,
    clock: Clock | None = None,
) -> LookupSummary:
    unique = tuple(dict.fromkeys(adas))
    if not 1 <= len(unique) <= MAX_ADAS:
        raise ValueError(f"Select 1 to {MAX_ADAS} ADAs")
    urls = {ada: source.url_for(ada) for ada in unique}
    limits = limits if limits is not None else LookupLimits()
    clock = clock if clock is not None else SystemClock()
    archive = Archive(archive_dir)
    deadline = clock.monotonic() + limits.run_timeout
    summary = LookupSummary(requested=len(unique))
    receipts: list[dict[str, object]] = []
    outcomes: dict[str, str] = {}
    manifest: dict[str, object] = {
        "format_version": 1,
        **source.manifest,
        "inputs": list(adas),
        "limits": asdict(limits),
        "started_at": datetime.now(UTC).isoformat(),
        "attempts": receipts,
        "outcomes": outcomes,
        "summary": asdict(summary),
    }
    run = archive.start_run(manifest)
    summary.run_id = run.name

    def save() -> None:
        manifest["summary"] = asdict(summary)
        archive.write_manifest(run, manifest)

    def remaining() -> float:
        left = deadline - clock.monotonic()
        if left <= 0:
            raise CollectionStopped("time_budget")
        return left

    previous: float | None = None
    try:
        for ada in unique:
            if previous is not None:
                pause = max(0.0, 60 / limits.requests_per_minute - (clock.monotonic() - previous))
                if pause >= remaining():
                    raise CollectionStopped("time_budget")
                clock.sleep(pause)
            remaining()
            receipt: dict[str, object] = {
                "ada": ada,
                "state": "started",
                "started_at": datetime.now(UTC).isoformat(),
                "body_complete": False,
            }
            receipts.append(receipt)
            save()  # The pending attempt is persisted before the request.
            previous = clock.monotonic()
            try:
                with client.stream(
                    "GET",
                    urls[ada],
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    timeout=min(limits.request_timeout, remaining()),
                    follow_redirects=False,
                ) as response:
                    receipt["status"] = response.status_code
                    if response.headers.get("content-encoding", "identity").strip().lower() != (
                        "identity"
                    ):
                        raise CollectionStopped("unsupported_encoding")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        remaining()
                        if len(body) + len(chunk) > limits.max_bytes:
                            raise CollectionStopped("response_size")
                        body.extend(chunk)
                    raw = bytes(body)
                    receipt.update(
                        sha256=archive.store(raw),
                        bytes=len(raw),
                        body_complete=True,
                        observed_at=datetime.now(UTC).isoformat(),
                    )
                    status = response.status_code
            except (httpx.TransportError, httpx.DecodingError):
                receipt["failure"] = "transport"
                raise CollectionStopped("transport") from None
            except CollectionStopped as stop:
                receipt["failure"] = str(stop)
                raise
            finally:
                receipt.update(state="finished", finished_at=datetime.now(UTC).isoformat())
                save()
            if status == 404:
                outcomes[ada] = "not_found_at_observation"
                summary.not_found += 1
            elif status == 200:
                try:
                    facts = source.summarize(raw, ada, limits.max_bytes)
                except source.invalid as bad:
                    archive.append(
                        run,
                        "quarantine",
                        [{"ada": ada, "field": str(bad), "response_sha256": receipt["sha256"]}],
                    )
                    outcomes[ada] = "quarantined"
                    summary.quarantined += 1
                else:
                    kind = str(facts["decision_type"])
                    summary.types[kind] = summary.types.get(kind, 0) + 1
                    archive.append(run, "normalized", [{"ada": ada, **facts}])
                    outcomes[ada] = "found"
                    summary.found += 1
            else:
                raise CollectionStopped(f"http_{status}")
            save()
        summary.collection_complete = True  # every requested ADA has an outcome
        summary.status = "quarantined" if summary.quarantined else "complete"
    except CollectionStopped as stop:
        summary.status, summary.failure = "failed", str(stop)
    except KeyboardInterrupt:
        summary.status, summary.failure = "interrupted", "interrupted"
    except (ArchiveError, OSError):
        summary.status, summary.failure = "failed", "archive"
        raise
    finally:
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        save()
    return summary
