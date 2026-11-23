"""Fresh, archive-only profile lookups; no registry discovery or identity writes.

Streaming/redirect behavior: https://www.python-httpx.org/quickstart/
Source: https://opendata-api.businessportal.gr/api-docs
"""

import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.transport import Clock, CollectionStopped, SystemClock, retry_delay
from nima.sources.gemi import (
    ENDPOINT,
    MAX_BODY,
    NORMALIZER_VERSION,
    InvalidProfile,
    normalize_profile,
    registry_number,
)


class SearchCompany(Protocol):
    def payload(self) -> dict[str, object]: ...


class SearchHit(Protocol):
    @property
    def company(self) -> SearchCompany: ...

    @property
    def afm_matches(self) -> bool: ...


class SearchAnswer(Protocol):
    """What the engine needs from the source's reading of one search response."""

    @property
    def outcome(self) -> str: ...

    @property
    def truncated(self) -> bool: ...

    @property
    def hits(self) -> tuple[SearchHit, ...]: ...

    @property
    def quarantine_path(self) -> str | None: ...


@dataclass(frozen=True)
class SearchRules:
    """The source's own rules for a search; the caller supplies them so the engine imports none."""

    queryable: Callable[[object], str]  # raises ValueError for an AFM that may not be sent
    parse: Callable[[bytes, str, int], SearchAnswer]  # raw body, queried AFM, HTTP status


MAX_AFMS = 25  # decision D4 of SPEC-gemi-afm-lookup
SEARCH_SIZE = 20  # decision D2: ask for up to 20 hits and keep every one


@dataclass(frozen=True)
class GemiLimits:
    max_attempts: int = 3
    max_bytes: int = MAX_BODY
    requests_per_minute: float = 8
    request_timeout: float = 60
    run_timeout: float = 300
    max_retry_delay: float = 60

    def __post_init__(self) -> None:
        for value, ceiling in ((self.max_attempts, 3), (self.max_bytes, MAX_BODY)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("Invalid GEMI count/byte budget")
        for duration, time_ceiling in (
            (self.requests_per_minute, 8),
            (self.request_timeout, 60),
            (self.run_timeout, 300),
            (self.max_retry_delay, 60),
        ):
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(duration)
                or not 0 < duration <= time_ceiling
            ):
                raise ValueError("Invalid GEMI rate/time budget")


@dataclass
class GemiSummary:
    run_id: str = ""
    status: str = "running"
    requested: int = 0
    found: int = 0
    not_found: int = 0
    quarantined: int = 0
    attempts: int = 0
    collection_complete: bool = False
    normalization_complete: bool = False
    failure: str | None = None


@dataclass
class GemiSearchSummary(GemiSummary):
    """``found`` counts AFMs that returned at least one company; ``companies`` counts the hits."""

    companies: int = 0
    outcome_counts: dict[str, int] = field(default_factory=dict)


class GemiRunError(Exception):
    def __init__(self, run_id: str, reason: str):
        self.run_id, self.reason = run_id, reason
        super().__init__(reason)


def _check_key(key: str) -> None:
    if (
        not isinstance(key, str)
        or not 1 <= len(key) <= 4096
        or any(not 33 <= ord(c) <= 126 for c in key)
        or key == "api-docs-key"
    ):
        raise ValueError("A personal GEMI API key is required")


def validate_afms(afms: tuple[str, ...], key: str, rules: SearchRules) -> tuple[str, ...]:
    _check_key(key)
    if not isinstance(afms, tuple) or not 1 <= len(afms) <= MAX_AFMS:
        raise ValueError(f"Select 1 to {MAX_AFMS} explicit AFMs")
    return tuple(dict.fromkeys(rules.queryable(value) for value in afms))


def validate_inputs(ids: tuple[str, ...], key: str) -> tuple[str, ...]:
    _check_key(key)
    if not isinstance(ids, tuple) or not 1 <= len(ids) <= 10:
        raise ValueError("Select 1–10 explicit registry numbers")
    return tuple(dict.fromkeys(registry_number(value) for value in ids))


class _Lookup:
    """One bounded GET per input, archive first. Subclasses choose the request and the outcome."""

    connector_version = "gemi-profile-v1"
    numbers_key = "registry_numbers"
    receipt_key = "registry_number"
    summary_type: type[GemiSummary] = GemiSummary

    def __init__(
        self,
        ids: tuple[str, ...],
        original: tuple[str, ...],
        key: str,
        archive: Archive,
        client: httpx.Client,
        limits: GemiLimits,
        clock: Clock,
    ):
        self.ids, self.key, self.archive, self.client = ids, key, archive, client
        self.limits, self.clock = limits, clock
        self.deadline = clock.monotonic() + limits.run_timeout
        self.previous: float | None = None
        self.receipts: list[dict[str, object]] = []
        self.outcomes: dict[str, str] = {}
        self.summary = self.summary_type(requested=len(ids))
        self.manifest: dict[str, object] = {
            "format_version": 1,
            "connector_version": self.connector_version,
            "normalizer_version": NORMALIZER_VERSION,
            "endpoint": ENDPOINT,
            "source": "https://opendata.businessportal.gr/techdocs/",
            "schema_sha256": "c91a65517b89f3a8ac1555f49b4f3178cc185c96addcc08dd2f772c353055e54",
            "license": "ODC-BY-1.0",
            "publisher": "Central GEMI Service / Central Union of Chambers",
            "inputs": list(original),
            self.numbers_key: list(ids),
            "limits": asdict(limits),
            "started_at": datetime.now(UTC).isoformat(),
            "attempts": self.receipts,
            "outcomes": self.outcomes,
            "summary": asdict(self.summary),
        }
        self.run = archive.start_run(self.manifest)
        self.summary.run_id = self.run.name

    def save(self) -> None:
        self.summary.attempts = len(self.receipts)
        self.manifest["summary"] = asdict(self.summary)
        self.archive.write_manifest(self.run, self.manifest)

    def remaining(self) -> float:
        remaining = self.deadline - self.clock.monotonic()
        if remaining <= 0:
            raise CollectionStopped("time_budget")
        return remaining

    def wait(self, seconds: float) -> None:
        if seconds >= self.remaining():
            raise CollectionStopped("time_budget")
        if seconds > 0:
            self.clock.sleep(seconds)

    def target(self, item: str) -> tuple[str, dict[str, str] | None]:
        return f"{ENDPOINT}/{item}", None

    def request(self, number: str, attempt: int) -> tuple[bytes, int, str | None, bool]:
        if self.previous is not None:
            self.wait(
                max(
                    0,
                    60 / self.limits.requests_per_minute - (self.clock.monotonic() - self.previous),
                )
            )
        self.remaining()
        receipt: dict[str, object] = {
            self.receipt_key: number,
            "attempt": attempt,
            "state": "started",
            "started_at": datetime.now(UTC).isoformat(),
            "body_complete": False,
        }
        self.receipts.append(receipt)
        self.save()  # The persisted pending attempt precedes the network request.
        try:
            self.previous = self.clock.monotonic()
            url, params = self.target(number)
            with self.client.stream(
                "GET",
                url,
                params=params,
                headers={
                    "api_key": self.key,
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
                timeout=min(self.limits.request_timeout, self.remaining()),
                follow_redirects=False,
            ) as response:
                receipt["status"] = response.status_code
                if (
                    response.headers.get("content-encoding", "identity").strip().lower()
                    != "identity"
                ):
                    raise CollectionStopped("unsupported_encoding")
                body = bytearray()
                # Check every transport chunk: a target chunk size can buffer a
                # slow trickle for longer than the cooperative run budget.
                for chunk in response.iter_bytes():
                    self.remaining()
                    if len(body) + len(chunk) > self.limits.max_bytes:
                        raise CollectionStopped("response_size")
                    body.extend(chunk)
                raw = bytes(body)
                receipt.update(
                    sha256=self.archive.store(raw),
                    bytes=len(raw),
                    body_complete=True,
                    observed_at=datetime.now(UTC).isoformat(),
                )
                self.remaining()
                is_json = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    == "application/json"
                )
                return raw, response.status_code, response.headers.get("retry-after"), is_json
        except (httpx.TransportError, httpx.DecodingError):
            receipt["failure"] = "transport"
            raise CollectionStopped("transport") from None
        except CollectionStopped as exc:
            receipt["failure"] = str(exc)
            raise
        except KeyboardInterrupt:
            receipt["failure"] = "interrupted"
            raise
        finally:
            receipt.update(state="finished", finished_at=datetime.now(UTC).isoformat())
            self.save()

    def fetch(self, number: str) -> tuple[bytes, int, bool]:
        for attempt in range(1, self.limits.max_attempts + 1):
            header, status = None, None
            try:
                raw, status, header, is_json = self.request(number, attempt)
            except CollectionStopped as exc:
                if str(exc) != "transport":
                    raise
            else:
                if status in {200, 404}:
                    return raw, status, is_json
                if status not in {429, 500, 502, 503, 504}:
                    raise CollectionStopped(f"http_{status}")
            if attempt == self.limits.max_attempts:
                raise CollectionStopped("retry_exhausted")
            delay = (
                30 * attempt if status == 429 and header is None else retry_delay(header, attempt)
            )
            if delay > self.limits.max_retry_delay:
                raise CollectionStopped("retry_delay")
            self.wait(delay)
        raise CollectionStopped("retry_exhausted")

    def handle(self, number: str, raw: bytes, status: int, is_json: bool) -> None:
        if status == 404:
            self.outcomes[number] = "not_found_at_observation"
            self.summary.not_found += 1
        else:
            try:
                if not is_json:
                    raise InvalidProfile("content_type")
                profile = normalize_profile(raw, number)
            except InvalidProfile as exc:
                self.archive.append(
                    self.run,
                    "quarantine",
                    [
                        {
                            "registry_number": number,
                            "field": str(exc),
                            "response_sha256": self.receipts[-1]["sha256"],
                        }
                    ],
                )
                self.summary.quarantined += 1
                self.outcomes[number] = "quarantined"
            else:
                self.archive.append(
                    self.run,
                    "normalized",
                    [
                        {
                            "profile": profile.payload(),
                            "observed_at": self.receipts[-1]["observed_at"],
                        }
                    ],
                )
                self.summary.found += 1
                self.outcomes[number] = "found"

    def execute(self) -> GemiSummary:
        try:
            self.save()
            try:
                for number in self.ids:
                    self.handle(number, *self.fetch(number))
                    self.save()
                self.summary.collection_complete = len(self.outcomes) == len(self.ids)
                self.summary.normalization_complete = self.summary.quarantined == 0
                self.summary.status = "quarantined" if self.summary.quarantined else "complete"
            except (CollectionStopped, KeyboardInterrupt) as exc:
                self.summary.status = (
                    "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
                )
                self.summary.failure = (
                    "interrupted" if isinstance(exc, KeyboardInterrupt) else str(exc)
                )
            except (ArchiveError, OSError) as exc:
                self.summary.status = "failed"
                self.summary.failure = (
                    "archive_invalid" if isinstance(exc, ArchiveError) else "archive_io"
                )
                raise
            finally:
                self.manifest["finished_at"] = datetime.now(UTC).isoformat()
                self.save()
        except (ArchiveError, OSError) as exc:
            reason = "archive_invalid" if isinstance(exc, ArchiveError) else "archive_io"
            raise GemiRunError(self.summary.run_id, reason) from None
        return self.summary


def collect(
    ids: tuple[str, ...],
    archive_dir: Path,
    *,
    api_key: str,
    client: httpx.Client,
    limits: GemiLimits | None = None,
    clock: Clock | None = None,
) -> GemiSummary:
    canonical = validate_inputs(ids, api_key)
    return _Lookup(
        canonical,
        ids,
        api_key,
        Archive(archive_dir),
        client,
        limits if limits is not None else GemiLimits(),
        clock if clock is not None else SystemClock(),
    ).execute()


class _AfmLookup(_Lookup):
    connector_version = "gemi-afm-search-v1"
    numbers_key = "afms"
    receipt_key = "afm"
    summary_type = GemiSearchSummary
    summary: GemiSearchSummary

    def __init__(
        self,
        rules: SearchRules,
        ids: tuple[str, ...],
        original: tuple[str, ...],
        key: str,
        archive: Archive,
        client: httpx.Client,
        limits: GemiLimits,
        clock: Clock,
    ):
        self.rules = rules
        super().__init__(ids, original, key, archive, client, limits, clock)

    def target(self, item: str) -> tuple[str, dict[str, str] | None]:
        return ENDPOINT, {"afm": item, "resultsSize": str(SEARCH_SIZE)}

    def handle(self, number: str, raw: bytes, status: int, is_json: bool) -> None:
        hits: tuple[SearchHit, ...] = ()
        if status == 200 and not is_json:
            outcome, truncated, reason = "quarantined", False, "content_type"
        else:
            result = self.rules.parse(raw, number, status)
            outcome, hits, truncated = result.outcome, result.hits, result.truncated
            reason = result.quarantine_path or ""
        if outcome == "quarantined":
            self.archive.append(
                self.run,
                "quarantine",
                [{"afm": number, "field": reason, "response_sha256": self.receipts[-1]["sha256"]}],
            )
            self.summary.quarantined += 1
        elif hits:
            self.archive.append(
                self.run,
                "normalized",
                [
                    {
                        "afm": number,
                        "outcome": outcome,
                        "truncated": truncated,
                        "afm_matches": hit.afm_matches,
                        "profile": hit.company.payload(),
                        "observed_at": self.receipts[-1]["observed_at"],
                    }
                    for hit in hits
                ],
            )
            self.summary.found += 1
            self.summary.companies += len(hits)
        else:
            self.summary.not_found += 1
        self.outcomes[number] = outcome
        counts = self.summary.outcome_counts
        counts[outcome] = counts.get(outcome, 0) + 1


def collect_afm(
    afms: tuple[str, ...],
    archive_dir: Path,
    *,
    rules: SearchRules,
    api_key: str,
    client: httpx.Client,
    limits: GemiLimits | None = None,
    clock: Clock | None = None,
) -> GemiSearchSummary:
    """Search the registry once per explicit AFM; every returned company is kept, none chosen."""
    canonical = validate_afms(afms, api_key, rules)
    lookup = _AfmLookup(
        rules,
        canonical,
        afms,
        api_key,
        Archive(archive_dir),
        client,
        limits if limits is not None else GemiLimits(),
        clock if clock is not None else SystemClock(),
    )
    lookup.execute()
    return lookup.summary
