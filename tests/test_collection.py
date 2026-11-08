"""Offline tests exercise the real HTTP/archive/normalization path."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits, Query


class Clock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.waits: list[float] = []

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.elapsed += seconds


def body(page: int = 0, total: int = 2, **row: object) -> bytes:
    return json.dumps(
        {
            "content": [{"referenceNumber": f"TEST-{page}", "title": "Synthetic", **row}]
            if total
            else [],
            "number": page,
            "size": 1,
            "totalElements": total,
            "totalPages": total,
            "last": page == max(0, total - 1),
        }
    ).encode()


QUERY = Query(date(2026, 11, 6), date(2026, 11, 6), ("00123",))


def test_collects_all_pages_with_exact_query_and_evidence(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            content=body(int(request.url.params["page"])),
            headers={"content-type": "application/json", "set-cookie": "private"},
        )

    archive = Archive(tmp_path / "raw")
    clock = Clock()
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = collect(QUERY, Limits(), archive, client=client, clock=clock)
    assert result.status == "complete"
    assert result.collection_complete and result.normalization_complete
    assert result.pages == result.records == result.normalized == 2
    assert clock.waits == [1.0]
    assert requests[0].method == "POST"
    assert str(requests[0].url).startswith("https://cerpp.eprocurement.gov.gr/")
    assert json.loads(requests[0].content) == {
        "dateFrom": "2026-11-06",
        "dateTo": "2026-11-06",
        "organizations": ["00123"],
    }
    run = archive.root / "runs" / result.run_id
    manifest = json.loads((run / "manifest.json").read_bytes())
    assert "set-cookie" not in manifest["responses"][0]["headers"]
    for response in manifest["responses"]:
        digest = response["sha256"]
        assert (archive.root / "objects" / digest[:2] / f"{digest}.body").is_file()
    assert len((run / "normalized.jsonl").read_text().splitlines()) == 2


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 408])
def test_retries_transient_responses_and_archives_each(tmp_path: Path, status: int) -> None:
    replies = iter(
        [
            httpx.Response(status, content=b"busy", headers={"retry-after": "2"}),
            httpx.Response(200, content=body(total=0)),
        ]
    )
    clock = Clock()
    archive = Archive(tmp_path / "raw")
    with httpx.Client(transport=httpx.MockTransport(lambda _: next(replies))) as client:
        result = collect(QUERY, Limits(), archive, client=client, clock=clock)
    assert result.status == "complete" and result.attempts == 2
    assert clock.waits == [2.0]
    manifest = json.loads((archive.root / "runs" / result.run_id / "manifest.json").read_bytes())
    assert [r["status"] for r in manifest["responses"]] == [status, 200]


@pytest.mark.parametrize(
    ("responses", "limits", "failure"),
    [
        ([httpx.Response(403, content=b"forbidden")], Limits(), "http_403"),
        ([httpx.Response(302, headers={"location": "https://example.com"})], Limits(), "http_302"),
        ([httpx.Response(200, content=b"not json")], Limits(), "invalid_page"),
        ([httpx.Response(200, content=body())], Limits(max_pages=1), "page_limit"),
        ([httpx.Response(200, content=b"large")], Limits(max_bytes=2), "response_size"),
        ([httpx.Response(429, headers={"retry-after": "90"})], Limits(), "retry_delay"),
        ([httpx.Response(503)], Limits(max_attempts=1), "retry_exhausted"),
        ([httpx.Response(200, content=body(page=1))], Limits(), "pagination_changed"),
    ],
)
def test_incomplete_runs_never_claim_success(
    tmp_path: Path, responses: list[httpx.Response], limits: Limits, failure: str
) -> None:
    replies = iter(responses)
    archive = Archive(tmp_path / "raw")
    with httpx.Client(transport=httpx.MockTransport(lambda _: next(replies))) as client:
        result = collect(QUERY, limits, archive, client=client, clock=Clock())
    assert result.status == "failed" and result.failure == failure
    assert not result.collection_complete and not result.normalization_complete
    manifest = json.loads((archive.root / "runs" / result.run_id / "manifest.json").read_bytes())
    assert manifest["summary"]["failure"] == failure


def test_quarantines_without_discarding_raw_collection(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "raw")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=body(total=1, title=42))
        )
    ) as client:
        result = collect(QUERY, Limits(), archive, client=client, clock=Clock())
    assert result.status == "quarantined" and result.collection_complete
    assert not result.normalization_complete and result.quarantined == 1
    assert result.normalized == 0
    assert (archive.root / "runs" / result.run_id / "quarantine.jsonl").is_file()


def test_duplicate_ids_prevent_completeness(tmp_path: Path) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, content=body(int(r.url.params["page"]), referenceNumber="SAME")
            )
        )
    ) as client:
        result = collect(QUERY, Limits(), Archive(tmp_path / "raw"), client=client, clock=Clock())
    assert result.failure == "identity_coverage" and result.duplicate_ids == 1
    assert not result.collection_complete
