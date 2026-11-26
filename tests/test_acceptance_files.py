"""One bounded private subject reader shared by both acceptance consumers."""

import os
from pathlib import Path

import pytest

from nima.dataops.acceptance_files import AcceptanceError, read_subject, valid_path
from nima.evidence import artifacts
from tests.test_citation_acceptance import subject


@pytest.mark.parametrize("limit", [1, 8 * 1024 * 1024])
def test_exact_subject_limit_is_in_bytes(limit: int, tmp_path: Path) -> None:
    body = b"x" * limit
    report = subject(tmp_path / "reports", body)
    assert read_subject(report, limit=limit) == body
    with pytest.raises(AcceptanceError, match="^acceptance_limit$"):
        read_subject(report, limit=limit - 1)


@pytest.mark.parametrize("limit", [0, True, 8 * 1024 * 1024 + 1])
def test_invalid_bound_stops_before_file_access(limit: int, tmp_path: Path) -> None:
    with pytest.raises(AcceptanceError, match="^acceptance_limit$"):
        read_subject(tmp_path / "missing", limit=limit)


@pytest.mark.parametrize(
    "value",
    [
        "absolute-string",
        Path("relative"),
        Path("/x/../y"),
        Path("/x/.git/y"),
        Path("/x/\x00"),
        Path("//x/y"),
    ],
)
def test_unsafe_paths_are_not_accepted(value: object) -> None:
    assert not valid_path(value)


def test_relative_subject_is_not_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = subject(tmp_path / "reports", b"valid")
    monkeypatch.chdir(report.parent)
    with pytest.raises(AcceptanceError, match="^acceptance_input$"):
        read_subject(Path(report.name), limit=32)


def test_link_added_during_read_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = subject(tmp_path / "reports", b"valid")
    original = artifacts.read

    def linked(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        data = original(parent, name, limit=limit, private=private)
        os.link(report, report.with_suffix(".alias"))
        return data

    monkeypatch.setattr(artifacts, "read", linked)
    with pytest.raises(AcceptanceError, match="^acceptance_evidence$"):
        read_subject(report, limit=32)


def test_shared_error_namespace_is_closed() -> None:
    assert str(AcceptanceError("PRIVATE_EXCEPTION")) == "acceptance_contract"
