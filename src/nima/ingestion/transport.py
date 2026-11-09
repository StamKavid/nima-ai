"""Bounded HTTP attempts against the fixed official source endpoint."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

import httpx

from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.config import ENDPOINT, Limits, Query


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class AttemptJournal(Protocol):
    def started(self, receipt: dict[str, object]) -> None: ...
    def finished(self, receipt: dict[str, object]) -> None: ...


class SystemClock:
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)


class CollectionStopped(ValueError):
    """A sanitized failure code, without source records or credential text."""


def retry_delay(header: str | None, attempt: int) -> float:
    if header is not None:
        if header.isascii() and header.isdecimal():
            # Avoid unbounded integer parsing from an untrusted header.
            return float(header) if len(header) < 12 else float("inf")
        try:
            instant = parsedate_to_datetime(header)
            if instant.tzinfo is not None:
                return max(0.0, (instant - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    return float(2 ** min(attempt - 1, 10))


class Session:
    def __init__(self, client: httpx.Client, archive: Archive, limits: Limits, clock: Clock):
        self.client, self.archive, self.limits, self.clock = client, archive, limits, clock
        self.deadline = clock.monotonic() + limits.run_timeout
        self.previous: float | None = None
        self.responses: list[dict[str, object]] = []
        self.journal: AttemptJournal | None = None
        self.phase = "collect"

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

    def request(self, query: Query, page: int, attempt: int) -> tuple[bytes, int, str | None]:
        if self.previous is not None:
            self.wait(
                max(
                    0.0,
                    60 / self.limits.requests_per_minute - (self.clock.monotonic() - self.previous),
                )
            )
        self.remaining()
        receipt: dict[str, object] = {
            "page": page,
            "attempt": attempt,
            "observed_at": datetime.now(UTC).isoformat(),
            "body_complete": False,
            "phase": self.phase,
        }
        self.responses.append(receipt)
        if self.journal is not None:
            self.journal.started(receipt)
        try:
            timeout = min(self.limits.request_timeout, self.remaining())
            self.previous = self.clock.monotonic()
            with self.client.stream(
                "POST",
                ENDPOINT,
                params={"page": page},
                json=query.payload(),
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "User-Agent": "Nima/0.0.1 (public-source evidence collector)",
                },
                timeout=timeout,
                follow_redirects=False,
            ) as response:
                receipt["status"] = response.status_code
                receipt["headers"] = {
                    key: value[:256]
                    for key, value in response.headers.items()
                    if key in {"content-type", "date", "etag", "last-modified", "retry-after"}
                }
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    # A decompressor can allocate a huge expansion before the
                    # decoded-byte limit sees it. This collector requests identity.
                    raise CollectionStopped("unsupported_encoding")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    self.remaining()
                    if len(body) + len(chunk) > self.limits.max_bytes:
                        raise CollectionStopped("response_size")
                    body.extend(chunk)
                # Archive a completed bounded body before status handling or parsing.
                raw = bytes(body)
                receipt.update(sha256=self.archive.store(raw), bytes=len(raw), body_complete=True)
                self.remaining()
                return raw, response.status_code, response.headers.get("retry-after")
        except ArchiveError:
            receipt["failure"] = "archive_invalid"
            raise
        except OSError:
            receipt["failure"] = "archive_io"
            raise
        except (httpx.TransportError, httpx.DecodingError) as exc:
            receipt["failure"] = type(exc).__name__
            raise CollectionStopped("transport") from exc
        except CollectionStopped as exc:
            receipt["failure"] = str(exc)
            raise
        except KeyboardInterrupt:
            receipt["failure"] = "interrupted"
            raise
        finally:
            if self.journal is not None:
                self.journal.finished(receipt)
