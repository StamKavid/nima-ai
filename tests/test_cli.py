"""The command validates before network access and reports useful exit states."""

import json
from pathlib import Path

import httpx
import pytest

from nima.__main__ import main
from tests.test_collection import body


def arguments(tmp_path: Path) -> list[str]:
    return [
        "ingest",
        "kimdis",
        "--from-date",
        "2026-11-06",
        "--to-date",
        "2026-11-06",
        "--archive-dir",
        str(tmp_path / "raw"),
    ]


@pytest.mark.parametrize(("bad", "exit_code"), [(False, 0), (True, 3)])
def test_cli_runs_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad: bool,
    exit_code: int,
) -> None:
    real_client = httpx.Client

    def client() -> httpx.Client:
        return real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, content=body(total=1, title=42 if bad else "Synthetic private title")
                )
            )
        )

    monkeypatch.setattr("nima.__main__.httpx.Client", client)
    assert main(arguments(tmp_path)) == exit_code
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["collection_complete"] is True
    assert summary["normalization_complete"] is not bad
    assert "Synthetic private title" not in output.out
    assert output.err == ""


def test_invalid_config_never_creates_archive_or_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_client() -> None:
        pytest.fail("Invalid configuration reached the HTTP client")

    monkeypatch.setattr("nima.__main__.httpx.Client", unexpected_client)
    assert main([*arguments(tmp_path), "--max-pages", "0"]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize("text", ["20261106", "yesterday", "2026-02-30"])
def test_dates_require_explicit_iso_format(tmp_path: Path, text: str) -> None:
    args = arguments(tmp_path)
    args[args.index("--from-date") + 1] = text
    with pytest.raises(SystemExit) as stopped:
        main(args)
    assert stopped.value.code == 2


def test_disk_error_cannot_be_reported_as_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*args: object) -> None:
        raise OSError("private path must not be echoed")

    monkeypatch.setattr("nima.__main__.Archive", fail)
    assert main(arguments(tmp_path)) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "archive_io"


def test_unrelated_directory_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "keep").write_text("unrelated")
    assert main(arguments(tmp_path)) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "archive_invalid"
