"""Boundaries must fail visibly rather than produce successful-looking datasets."""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits, Query
from nima.ingestion.transport import retry_delay
from tests.test_collection import QUERY, Clock, body


def test_small_stream_chunks_cannot_hide_elapsed_run_budget(tmp_path: Path) -> None:
    clock = Clock()

    class Trickle(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            for _ in range(10):
                clock.elapsed += 2
                yield b"x"

    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Trickle()))
    ) as client:
        result = collect(
            QUERY, Limits(run_timeout=5), Archive(tmp_path / "raw"), client=client, clock=clock
        )
    assert result.failure == "time_budget" and clock.elapsed == 6
    assert not list((tmp_path / "raw" / "objects").glob("*/*.body"))


@pytest.mark.parametrize(
    "build",
    [
        lambda: Limits(max_pages=0),
        lambda: Limits(max_attempts=True),
        lambda: Limits(max_bytes=-1),
        lambda: Limits(requests_per_minute=351),
        lambda: Limits(run_timeout=float("nan")),
        lambda: Limits(request_timeout=float("inf")),
        lambda: Limits(max_retry_delay=0),
    ],
)
def test_invalid_limits(build: Callable[[], Limits]) -> None:
    with pytest.raises(ValueError):
        build()


@pytest.mark.parametrize(
    "start,end,buyers",
    [
        (date(2026, 1, 2), date(2026, 1, 1), ()),
        (date(2026, 1, 1), date(2026, 7, 1), ()),
        (date(2026, 1, 1), date(2026, 1, 1), ("０１",)),
        (date(2026, 1, 1), date(2026, 1, 1), ("0",)),
        (date(2026, 1, 1), date(2026, 1, 1), ("bad",)),
    ],
)
def test_invalid_queries(start: date, end: date, buyers: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        Query(start, end, buyers)


def test_inclusive_window_boundary_and_absent_buyer_filter() -> None:
    start = date(2026, 1, 1)
    assert "organizations" not in Query(start, start + timedelta(days=179)).payload()
    with pytest.raises(ValueError):
        Query(start, start + timedelta(days=180))


def test_retry_after_dates_and_malformed_values() -> None:
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    assert 28 <= retry_delay(future, 1) <= 30
    assert retry_delay("invalid", 2) == 2
    assert retry_delay("0", 1) == 0
    assert retry_delay("9" * 1000, 1) == float("inf")
    assert retry_delay("Sun, 08 Nov 2026 12:00:00", 1) == 1  # Unqualified timezone.


def test_transport_timeout_is_retried_without_leaking_exception_text(tmp_path: Path) -> None:
    attempts = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("private diagnostic", request=request)
        return httpx.Response(200, content=body(total=0))

    archive = Archive(tmp_path / "raw")
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = collect(QUERY, Limits(), archive, client=client, clock=Clock())
    assert result.status == "complete" and result.attempts == 2
    manifest = (archive.root / "runs" / result.run_id / "manifest.json").read_text()
    assert "ReadTimeout" in manifest and "private diagnostic" not in manifest


@pytest.mark.parametrize("mode", ["retry", "rate", "body"])
def test_time_budget_covers_retry_rate_and_streaming_waits(tmp_path: Path, mode: str) -> None:
    clock = Clock()

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b"{"
            clock.elapsed += 2
            yield b"}"

    def handle(_: httpx.Request) -> httpx.Response:
        if mode == "retry":
            return httpx.Response(429, headers={"retry-after": "2"})
        if mode == "body":
            return httpx.Response(200, stream=SlowStream())
        return httpx.Response(200, content=body())

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = collect(
            QUERY, Limits(run_timeout=0.5), Archive(tmp_path / "raw"), client=client, clock=clock
        )
    assert result.failure == "time_budget" and not result.collection_complete
    assert result.attempts == 1


@pytest.mark.parametrize("mode", ["changed", "missing", "interrupt", "encoding"])
def test_other_failure_paths(tmp_path: Path, mode: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if mode == "interrupt":
            raise KeyboardInterrupt
        if mode == "encoding":
            return httpx.Response(200, headers={"content-encoding": "gzip"})
        if mode == "changed":
            return httpx.Response(200, content=body(page, total=2 + int(page > 0)))
        return httpx.Response(200, content=body(total=1, referenceNumber=None))

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = collect(QUERY, Limits(), Archive(tmp_path / "raw"), client=client, clock=Clock())
    assert (
        result.failure
        == {
            "changed": "pagination_changed",
            "missing": "identity_coverage",
            "interrupt": "interrupted",
            "encoding": "unsupported_encoding",
        }[mode]
    )
    assert not result.collection_complete


def test_money_serializes_exactly_and_evidence_resolves(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "raw")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=body(total=1, totalCostWithoutVAT="123456789012345678.90")
            )
        )
    ) as client:
        result = collect(QUERY, Limits(), archive, client=client, clock=Clock())
    row = json.loads((archive.root / "runs" / result.run_id / "normalized.jsonl").read_bytes())
    assert row["net_amount"] == "123456789012345678.90"
    digest = row["evidence"]["response_sha256"]
    raw = json.loads((archive.root / "objects" / digest[:2] / f"{digest}.body").read_bytes())
    assert raw["content"][0]["referenceNumber"] == row["source_id"].removeprefix("kimdis:")


def test_oversized_bidder_integer_is_quarantined(tmp_path: Path) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=body(total=1, bidsSubmitted="9" * 5000))
        )
    ) as client:
        result = collect(QUERY, Limits(), Archive(tmp_path / "raw"), client=client, clock=Clock())
    assert result.status == "quarantined" and result.quarantined == 1


def test_rate_limit_without_retry_after_uses_conservative_backoff(tmp_path: Path) -> None:
    replies = iter([httpx.Response(429), httpx.Response(200, content=body(total=0))])
    clock = Clock()
    with httpx.Client(transport=httpx.MockTransport(lambda _: next(replies))) as client:
        result = collect(QUERY, Limits(), Archive(tmp_path / "raw"), client=client, clock=clock)
    assert result.status == "complete" and clock.waits == [30.0]
