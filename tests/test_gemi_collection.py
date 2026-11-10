"""Bounded profile GETs exercise actual HTTPX, archive and normalization paths."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from nima.ingestion.archive import Archive
from nima.ingestion.gemi import GemiLimits, GemiRunError, collect
from tests.test_collection import Clock
from tests.test_gemi_contracts import profile

KEY = "synthetic-test-credential"


def test_lookup_archives_before_transform_and_accounts_for_404(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    clock = Clock()

    def handle(request: httpx.Request) -> httpx.Response:
        pending = json.loads(next((tmp_path / "raw" / "runs").glob("*/manifest.json")).read_text())
        assert pending["attempts"][-1]["state"] == "started"
        requests.append(request)
        number = int(request.url.path.rsplit("/", 1)[1])
        return (
            httpx.Response(200, content=profile(), headers={"content-type": "application/json"})
            if number == 1
            else httpx.Response(404, content=b"missing")
        )

    with httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
        result = collect(
            ("0001", "1", "2"), tmp_path / "raw", api_key=KEY, client=client, clock=clock
        )
    assert (
        result.status == "complete" and result.collection_complete and result.normalization_complete
    )
    assert (result.requested, result.found, result.not_found, result.attempts) == (2, 1, 1, 2)
    assert clock.waits == [3.0]
    assert requests[0].method == "GET" and requests[0].headers["api_key"] == KEY
    assert (
        str(requests[0].url) == "https://opendata-api.businessportal.gr/api/opendata/v1/companies/1"
    )
    assert requests[0].headers["accept-encoding"] == "identity"
    run = tmp_path / "raw" / "runs" / result.run_id
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["inputs"] == ["0001", "1", "2"]
    assert manifest["outcomes"] == {"1": "found", "2": "not_found_at_observation"}
    assert manifest["license"] == "ODC-BY-1.0" and KEY not in json.dumps(manifest)
    assert len(list((tmp_path / "raw" / "objects").glob("*/*.body"))) == 2
    normalized = json.loads((run / "normalized.jsonl").read_text())
    assert normalized["profile"]["fields"]["reported_afm"]["value"] == "001234567"


@pytest.mark.parametrize(
    "key,ids",
    [
        ("", ("1",)),
        (" ", ("1",)),
        ("bad\nkey", ("1",)),
        ("api-docs-key", ("1",)),
        (KEY, ()),
        (KEY, ("0",)),
        (KEY, ("../1",)),
        (KEY, ("１",)),
        (KEY, ("1" * 65,)),
        (KEY, ("1",) * 11),
    ],
)
def test_invalid_inputs_precede_archive_or_http(
    tmp_path: Path, key: str, ids: tuple[str, ...]
) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected HTTP"))
        ) as client,
        pytest.raises(ValueError),
    ):
        collect(ids, tmp_path / "raw", api_key=key, client=client)
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize(
    "make",
    [
        lambda: GemiLimits(max_attempts=4),
        lambda: GemiLimits(max_bytes=0),
        lambda: GemiLimits(requests_per_minute=21),
        lambda: GemiLimits(run_timeout=float("nan")),
        lambda: GemiLimits(request_timeout=True),
        lambda: GemiLimits(max_retry_delay=-1),
    ],
)
def test_limits_reject_unbounded_or_invalid_values(make: Callable[[], GemiLimits]) -> None:
    with pytest.raises(ValueError):
        make()


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("retry", "complete"),
        ("transport", "complete"),
        ("retry_exhausted", "failed"),
        ("deferred", "failed"),
        ("redirect", "failed"),
        ("auth", "failed"),
        ("oversized", "failed"),
        ("encoding", "failed"),
        ("budget", "failed"),
        ("quarantine", "quarantined"),
        ("media", "quarantined"),
        ("interrupt", "interrupted"),
    ],
)
def test_attempt_failures_and_quarantine_remain_visible(
    tmp_path: Path, kind: str, expected: str
) -> None:
    calls = 0
    clock = Clock()

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if kind == "interrupt":
            raise KeyboardInterrupt
        if kind == "transport" and calls == 1:
            raise httpx.ReadTimeout("private credential details")
        if kind == "deferred":
            return httpx.Response(429, headers={"retry-after": "61"}, content=b"later")
        if kind == "retry" and calls == 1 or kind == "retry_exhausted":
            return httpx.Response(503, headers={"retry-after": "4"}, content=b"later")
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://example.org/private"})
        if kind == "auth":
            return httpx.Response(403)
        if kind == "budget":
            clock.elapsed = 301
        return httpx.Response(
            200,
            content=profile(2 if kind == "quarantine" else 1),
            headers={
                "content-type": "text/plain" if kind == "media" else "application/json",
                "content-encoding": "gzip" if kind == "encoding" else "identity",
            },
        )

    limits = GemiLimits(max_bytes=1) if kind == "oversized" else GemiLimits()
    # HTTPX decodes eager MockTransport content on Response construction. Encoding
    # is tested below with a genuinely lazy body so the collector sees the header.
    if kind == "encoding":
        transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200, stream=httpx.ByteStream(b"compressed"), headers={"content-encoding": "gzip"}
            )
        )
    else:
        transport = httpx.MockTransport(handle)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        result = collect(
            ("1",), tmp_path / "raw", api_key=KEY, client=client, clock=clock, limits=limits
        )
    assert result.status == expected
    if kind in {"redirect", "auth", "deferred"}:
        assert calls == 1
    manifest = json.loads(next((tmp_path / "raw" / "runs").glob("*/manifest.json")).read_text())
    assert KEY not in json.dumps(manifest) and "private credential" not in json.dumps(manifest)
    if kind in {"quarantine", "media"}:
        assert result.collection_complete and not result.normalization_complete
        assert len(list((tmp_path / "raw" / "objects").glob("*/*.body"))) == 1
    if expected in {"failed", "interrupted"}:
        assert not result.collection_complete and not result.normalization_complete


def test_raw_storage_failure_prevents_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_store(self: Archive, body: bytes) -> str:
        raise OSError("private storage details")

    def no_parse(*_: object) -> None:
        pytest.fail("Parsed before durable raw storage")

    monkeypatch.setattr(Archive, "store", fail_store)
    monkeypatch.setattr("nima.ingestion.gemi.normalize_profile", no_parse)
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, content=profile(), headers={"content-type": "application/json"}
                )
            )
        ) as client,
        pytest.raises(GemiRunError, match="archive_io"),
    ):
        collect(("1",), tmp_path / "raw", api_key=KEY, client=client)


def test_cli_requires_key_before_client_and_emits_only_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.__main__ import main

    args = ["ingest", "gemi", "--gemi-id", "1", "--archive-dir", str(tmp_path / "raw")]
    real_client = httpx.Client
    monkeypatch.delenv("NIMA_GEMI_API_KEY", raising=False)
    monkeypatch.setattr(
        "nima.__main__.httpx.Client", lambda: pytest.fail("Client before configuration")
    )
    assert main(args) == 2 and not (tmp_path / "raw").exists()
    capsys.readouterr()
    monkeypatch.setenv("NIMA_GEMI_API_KEY", KEY)
    monkeypatch.setattr(
        "nima.__main__.httpx.Client",
        lambda: real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, content=profile(), headers={"content-type": "application/json"}
                )
            )
        ),
    )
    assert main(args) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["found"] == 1
    assert KEY not in output.out + output.err and "001234567" not in output.out

    def fail(*args: object, **kwargs: object) -> None:
        raise GemiRunError("synthetic-run", "archive_io")

    monkeypatch.setattr("nima.__main__.collect_gemi", fail)
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["run_id"] == "synthetic-run"


def test_stream_error_never_archives_partial_body_and_rate_budget_keeps_prior_success(
    tmp_path: Path,
) -> None:
    class Broken(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b'{"arGemi":'
            raise httpx.ReadError("private transport details")

    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Broken()))
    ) as client:
        result = collect(
            ("1",),
            tmp_path / "partial",
            api_key=KEY,
            client=client,
            limits=GemiLimits(max_attempts=1),
            clock=Clock(),
        )
    assert result.failure == "retry_exhausted"
    assert not list((tmp_path / "partial" / "objects").glob("*/*.body"))
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=profile(), headers={"content-type": "application/json"}
            )
        )
    ) as client:
        result = collect(
            ("1", "2"),
            tmp_path / "budget",
            api_key=KEY,
            client=client,
            limits=GemiLimits(run_timeout=2),
            clock=Clock(),
        )
    assert result.failure == "time_budget" and result.found == result.attempts == 1
    assert not result.collection_complete
