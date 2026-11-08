"""Validated, explicit collection boundaries."""

import math
from dataclasses import dataclass
from datetime import date

ENDPOINT = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract"
SOURCE = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help"
CONNECTOR_VERSION = "kimdis-contract-v1"


@dataclass(frozen=True)
class Query:
    from_date: date
    to_date: date
    buyers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= (self.to_date - self.from_date).days < 180:
            raise ValueError("Choose an ordered window of at most 180 inclusive calendar days")
        if any(not b.isascii() or not b.isdecimal() or int(b) <= 0 for b in self.buyers):
            raise ValueError("Buyer IDs must be positive ASCII decimal strings")

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "dateFrom": self.from_date.isoformat(),
            "dateTo": self.to_date.isoformat(),
        }
        if self.buyers:
            payload["organizations"] = list(self.buyers)
        return payload


@dataclass(frozen=True)
class Limits:
    max_pages: int = 100
    max_attempts: int = 3
    max_bytes: int = 8 * 1024 * 1024
    requests_per_minute: float = 20.0
    request_timeout: float = 20.0
    run_timeout: float = 300.0
    max_retry_delay: float = 60.0

    def __post_init__(self) -> None:
        for value in (self.max_pages, self.max_attempts, self.max_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError("Page, attempt, and byte limits must be positive integers")
        for duration in (
            self.requests_per_minute,
            self.request_timeout,
            self.run_timeout,
            self.max_retry_delay,
        ):
            if isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
                raise ValueError("Rate and time limits must be positive finite numbers")
        if self.requests_per_minute > 350:
            raise ValueError("Rate exceeds the documented 350 requests/minute ceiling")


@dataclass
class Summary:
    run_id: str = ""
    status: str = "running"
    collection_complete: bool = False
    normalization_complete: bool = False
    pages: int = 0
    attempts: int = 0
    records: int = 0
    normalized: int = 0
    quarantined: int = 0
    unidentified: int = 0
    duplicate_ids: int = 0
    expected_records: int | None = None
    expected_pages: int | None = None
    failure: str | None = None
