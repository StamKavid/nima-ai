"""C0: look up the decision type of a few explicit ADAs. No real request is made."""

import json
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest

from nima.__main__ import _DIAVGEIA_DECISIONS, main
from nima.ingestion.archive import Archive, ArchiveError
from nima.ingestion.diavgeia_lookup import LookupLimits, LookupSummary
from nima.ingestion.diavgeia_lookup import lookup as _lookup
from nima.sources.diavgeia import InvalidDecision, decision_summary, decision_url
from tests.diavgeia_samples import decision
from tests.test_collection import Clock

ADA = "ΑΒΓΔΕ-ΖΗ1"
OTHER = "ΩΨΧΦΥ-ΤΣ2"


def lookup(adas: tuple[str, ...], archive_dir: Path, **options: object) -> LookupSummary:
    return _lookup(adas, archive_dir, source=_DIAVGEIA_DECISIONS, **options)  # type: ignore[arg-type]


def raw(**fields: object) -> bytes:
    return json.dumps(decision(**fields), ensure_ascii=False).encode()


def _decoded(name: str) -> str:
    return unquote(name)


def test_url_is_the_documented_decision_path_and_refuses_odd_ada() -> None:
    assert decision_url(ADA) == f"https://diavgeia.gov.gr/opendata/decisions/{ADA}.json"
    for bad in ("", "a b", "../x", "x/y", "a" * 65, "_x", 5):
        with pytest.raises(ValueError):
            decision_url(bad)  # type: ignore[arg-type]


def test_summary_keeps_only_type_organisation_and_status() -> None:
    assert decision_summary(raw(decisionTypeId="Β.1.3"), ADA, 10_000) == {
        "decision_type": "Β.1.3",
        "organization_id": "99999",
        "status": "PUBLISHED",
    }
    assert decision_summary(raw(organizationId=None), ADA, 10_000)["organization_id"] is None


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"x" * 11, "size"),
        (b"not json", "json"),
        (b"[]", "object"),
        (b'{"ada": "' + ADA.encode() + b'", "ada": "x"}', "json"),
        (raw(ada=OTHER), "ada_mismatch"),
        (raw(ada=None), "ada_mismatch"),
        (raw(status="BOGUS"), "status"),
        (raw(decisionTypeId=None), "decision_type"),
        (raw(decisionTypeId=" "), "decision_type"),
        (raw(organizationId=5), "organization"),
    ],
)
def test_a_response_that_does_not_match_is_refused_with_a_fixed_reason(
    body: bytes, reason: str
) -> None:
    with pytest.raises(InvalidDecision) as caught:
        decision_summary(body, ADA, 10 if reason == "size" else 10_000)
    assert str(caught.value) == reason


def test_lookup_archives_first_counts_types_and_waits_between_requests(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    clock = Clock()
    responses = {
        ADA: httpx.Response(200, content=raw(decisionTypeId="Β.1.3")),
        OTHER: httpx.Response(404, content=b"missing"),
    }

    def handle(request: httpx.Request) -> httpx.Response:
        pending = json.loads(next((tmp_path / "raw" / "runs").glob("*/manifest.json")).read_text())
        assert pending["attempts"][-1]["state"] == "started"
        seen.append(request)
        return responses[_decoded(request.url.path.rsplit("/", 1)[1].removesuffix(".json"))]

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = lookup((ADA, OTHER, ADA), tmp_path / "raw", client=client, clock=clock)
    assert result.status == "complete" and result.collection_complete
    assert (result.requested, result.found, result.not_found, result.quarantined) == (2, 1, 1, 0)
    assert result.types == {"Β.1.3": 1}
    assert clock.waits == [3.0]
    assert [r.url.host for r in seen] == ["diavgeia.gov.gr"] * 2
    assert seen[0].headers["accept-encoding"] == "identity"
    run = tmp_path / "raw" / "runs" / result.run_id
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["inputs"] == [ADA, OTHER, ADA] and manifest["license"].startswith("CC BY 4.0")
    assert manifest["outcomes"] == {ADA: "found", OTHER: "not_found_at_observation"}
    assert len(list((tmp_path / "raw" / "objects").glob("*/*.body"))) == 2


def test_a_mismatching_record_is_quarantined_not_counted(tmp_path: Path) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw(ada=OTHER)))
    ) as client:
        result = lookup((ADA,), tmp_path / "raw", client=client, clock=Clock())
    assert result.status == "quarantined" and result.quarantined == 1 and result.types == {}
    run = tmp_path / "raw" / "runs" / result.run_id
    row = json.loads((run / "quarantine.jsonl").read_text())
    assert row["field"] == "ada_mismatch" and row["ada"] == ADA


@pytest.mark.parametrize("status", [429, 500, 403])
def test_any_other_status_stops_the_run_without_retry(tmp_path: Path, status: int) -> None:
    calls: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(status, content=b"")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = lookup((ADA, OTHER), tmp_path / "raw", client=client, clock=Clock())
    assert result.status == "failed" and result.failure == f"http_{status}"
    assert len(calls) == 1 and not result.collection_complete


def test_a_transport_error_and_an_oversize_body_stop_the_run(tmp_path: Path) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with httpx.Client(transport=httpx.MockTransport(broken)) as client:
        result = lookup((ADA,), tmp_path / "a", client=client, clock=Clock())
    assert (result.status, result.failure) == ("failed", "transport")
    big = httpx.Response(200, content=b"x" * 20)
    with httpx.Client(transport=httpx.MockTransport(lambda _: big)) as client:
        result = lookup(
            (ADA,), tmp_path / "b", client=client, clock=Clock(), limits=LookupLimits(max_bytes=10)
        )
    assert (result.status, result.failure) == ("failed", "response_size")


def test_an_encoded_response_and_a_redirect_are_not_followed(tmp_path: Path) -> None:
    gz = httpx.Response(200, content=raw(), headers={"content-encoding": "x-unknown"})
    with httpx.Client(transport=httpx.MockTransport(lambda _: gz)) as client:
        result = lookup((ADA,), tmp_path / "a", client=client, clock=Clock())
    assert result.failure == "unsupported_encoding"
    moved = httpx.Response(302, headers={"location": "https://elsewhere.example/"})
    with httpx.Client(transport=httpx.MockTransport(lambda _: moved)) as client:
        result = lookup((ADA,), tmp_path / "b", client=client, clock=Clock())
    assert result.failure == "http_302"


def test_the_run_budget_stops_the_run(tmp_path: Path) -> None:
    clock = Clock()
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw()))
    ) as client:
        result = lookup(
            (ADA, OTHER),
            tmp_path / "raw",
            client=client,
            clock=clock,
            limits=LookupLimits(run_timeout=2.0),
        )
    assert (result.status, result.failure) == ("failed", "time_budget")
    assert clock.waits == [] and not result.collection_complete


@pytest.mark.parametrize("adas", [(), ("a b",), tuple(f"A{i}" for i in range(16))])
def test_invalid_inputs_precede_archive_and_http(tmp_path: Path, adas: tuple[str, ...]) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("HTTP"))) as client,
        pytest.raises(ValueError),
    ):
        lookup(adas, tmp_path / "raw", client=client, clock=Clock())
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_bytes": 0},
        {"max_bytes": 2_000_000},
        {"requests_per_minute": 0},
        {"requests_per_minute": 21},
        {"request_timeout": 0},
        {"run_timeout": 301},
        {"requests_per_minute": True},
    ],
)
def test_limits_are_bounded(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        LookupLimits(**kwargs)  # type: ignore[arg-type]


def test_the_command_prints_counts_by_type_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_client = httpx.Client
    monkeypatch.setattr(
        "nima.__main__.httpx.Client",
        lambda: real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, content=raw(decisionTypeId="Β.1.3"))
            )
        ),
    )
    monkeypatch.setattr("nima.ingestion.diavgeia_lookup.SystemClock", Clock)
    code = main(
        ["ingest", "diavgeia-decisions", "--ada", ADA, "--archive-dir", str(tmp_path / "raw")]
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["types"] == {"Β.1.3": 1} and out["found"] == 1
    assert ADA not in json.dumps(out, ensure_ascii=False)


def test_the_command_refuses_a_bad_ada_before_any_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected() -> httpx.Client:
        raise AssertionError("no client")

    monkeypatch.setattr("nima.__main__.httpx.Client", unexpected)
    arguments = ["ingest", "diavgeia-decisions", "--ada", "a b", "--archive-dir", str(tmp_path)]
    assert main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"


def test_a_slow_body_interruption_and_archive_failure_end_the_run_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()

    def slow(request: httpx.Request) -> httpx.Response:
        clock.elapsed += 400
        return httpx.Response(200, content=raw())

    with httpx.Client(transport=httpx.MockTransport(slow)) as client:
        result = lookup((ADA,), tmp_path / "a", client=client, clock=clock)
    assert (result.status, result.failure) == ("failed", "time_budget")

    def interrupted(request: httpx.Request) -> httpx.Response:
        raise KeyboardInterrupt

    with httpx.Client(transport=httpx.MockTransport(interrupted)) as client:
        result = lookup((ADA,), tmp_path / "b", client=client, clock=Clock())
    assert (result.status, result.failure) == ("interrupted", "interrupted")

    def broken(self: Archive, body: bytes) -> str:
        raise ArchiveError("bad")

    monkeypatch.setattr(Archive, "store", broken)
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw()))
        ) as client,
        pytest.raises(ArchiveError),
    ):
        lookup((ADA,), tmp_path / "c", client=client, clock=Clock())
    manifest = json.loads(next((tmp_path / "c" / "runs").glob("*/manifest.json")).read_text())
    assert manifest["summary"]["failure"] == "archive" and manifest["summary"]["status"] == "failed"
