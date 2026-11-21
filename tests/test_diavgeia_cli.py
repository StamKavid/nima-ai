"""`nima ingest diavgeia` collects one explicit organisation and window; no real request is made."""

import json
from pathlib import Path

import httpx
import pytest

from nima.__main__ import main
from nima.ingestion.config import Limits
from tests.diavgeia_samples import decision, search_page


def arguments(tmp_path: Path, **overrides: str) -> list[str]:
    values = {
        "--organization": "99999",
        "--from-date": "2026-01-01",
        "--to-date": "2026-01-30",
        "--archive-dir": str(tmp_path / "raw"),
        **overrides,
    }
    return ["ingest", "diavgeia", *[part for pair in values.items() for part in pair]]


def serve(monkeypatch: pytest.MonkeyPatch, content: bytes, sent: list[httpx.Request]) -> None:
    real_client = httpx.Client

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, content=content)

    monkeypatch.setattr(
        "nima.__main__.httpx.Client", lambda: real_client(transport=httpx.MockTransport(handle))
    )


@pytest.mark.parametrize(("status", "exit_code"), [("PUBLISHED", 0), ("BOGUS", 3)])
def test_the_command_collects_one_window_and_asks_only_diavgeia(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    exit_code: int,
) -> None:
    sent: list[httpx.Request] = []
    serve(monkeypatch, search_page(0, 1, 100, [decision(status=status)]), sent)
    assert main(arguments(tmp_path)) == exit_code
    summary = json.loads(capsys.readouterr().out)
    assert summary["collection_complete"] is True and summary["records"] == 1
    assert (summary["normalized"], summary["quarantined"]) == (1 - exit_code // 3, exit_code // 3)
    assert len(sent) == 1
    request = sent[0]
    assert request.method == "GET" and request.url.host == "diavgeia.gov.gr"
    assert dict(request.url.params) == {
        "org": "99999",
        "type": "Δ.2.2",
        "from_issue_date": "2026-01-01",
        "to_issue_date": "2026-01-30",
        "status": "all",
        "page": "0",
        "size": "100",
    }
    assert (tmp_path / "raw").is_dir()


@pytest.mark.parametrize(
    "bad",
    [
        {"--organization": "a b"},
        {"--to-date": "2026-02-15"},
        {"--from-date": "2026-01-31", "--to-date": "2026-01-01"},
    ],
)
def test_an_unsafe_selection_is_refused_before_any_archive_or_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad: dict[str, str],
) -> None:
    def unexpected_client() -> httpx.Client:
        raise AssertionError("a client must not be created")

    monkeypatch.setattr("nima.__main__.httpx.Client", unexpected_client)
    assert main(arguments(tmp_path, **bad)) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
    assert not (tmp_path / "raw").exists()


def test_the_organisation_and_both_dates_are_required(tmp_path: Path) -> None:
    for missing in ("--organization", "--from-date", "--to-date", "--archive-dir"):
        values = arguments(tmp_path)
        index = values.index(missing)
        del values[index : index + 2]
        with pytest.raises(SystemExit) as caught:
            main(values)
        assert caught.value.code == 2


def test_the_engines_default_limits_and_no_database_unless_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def spy(query: object, limits: Limits, archive: object, **options: object) -> object:
        seen.update(query=query, limits=limits, **options)
        raise RuntimeError("stop before any request")

    monkeypatch.setattr("nima.__main__.collect", spy)
    with pytest.raises(RuntimeError):
        main(arguments(tmp_path))
    assert seen["query"] is None and seen["limits"] == Limits()
    assert seen["database_dsn"] is None
    adapter = seen["adapter"]
    assert adapter.query_payload()["organization"] == "99999"  # type: ignore[attr-defined]
