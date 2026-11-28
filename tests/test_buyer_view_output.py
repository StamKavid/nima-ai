"""Publication failure atomicity and renderer limits at the export boundary."""

import hashlib
from pathlib import Path
from typing import Any

import pytest

from nima.analytics import buyer_view as view
from nima.analytics import buyer_view_html as html
from nima.analytics.buyer_view_request import ViewError
from nima.evidence import artifacts
from nima.identity import AssessmentError
from tests.test_buyer_view_request import configuration


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tmp_path.chmod(0o700)
    path = tmp_path / "view.json"
    path.write_bytes(configuration())
    path.chmod(0o600)
    # Boundary-only fixture: production provider admission is exercised natively.
    monkeypatch.setattr(
        view, "prepare_buyer_evidence_view", lambda *args: view.PreparedBuyerView((), ())
    )
    monkeypatch.setattr(html, "render_view", lambda *args: b"<!doctype html>fixture")
    return path


@pytest.mark.parametrize(
    "error,reason",
    [
        (AssessmentError("assessment_limit"), "limit"),
        (ViewError("view_limit"), "limit"),
        (KeyError("private"), "contract"),
        (OSError("private"), "contract"),
    ],
)
def test_renderer_failure_never_creates_an_output_directory(
    error: Exception, reason: str, config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object) -> Any:
        raise error

    monkeypatch.setattr(html, "render_view", fail)
    output = tmp_path / "output"
    with pytest.raises(ViewError, match="^view_" + reason + "$"):
        view.export_buyer_evidence_view("fixture", config, output)
    assert not output.exists()


@pytest.mark.parametrize("which", ["config", "output"])
def test_export_requires_safe_absolute_paths(which: str, config: Path, tmp_path: Path) -> None:
    with pytest.raises(ViewError, match="^view_input$"):
        view.export_buyer_evidence_view(
            "fixture",
            Path("relative") if which == "config" else config,
            Path("relative") if which == "output" else tmp_path / "out",
        )


def test_output_refuses_symlink_roots_and_existing_conflicts(config: Path, tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ViewError, match="^view_output$"):
        view.export_buyer_evidence_view("fixture", config, link)
    digest = hashlib.sha256(b"<!doctype html>fixture").hexdigest()
    conflict = target / (digest + ".html")
    conflict.write_bytes(b"unchanged conflicting file")
    conflict.chmod(0o600)
    with pytest.raises(ViewError, match="^view_output$"):
        view.export_buyer_evidence_view("fixture", config, target)
    assert conflict.read_bytes() == b"unchanged conflicting file"


def test_interruption_does_not_publish_partial_html(
    config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = artifacts.publish

    def interrupt(parent: int, name: str, body: bytes) -> None:
        if name.endswith(".html"):
            raise KeyboardInterrupt
        original(parent, name, body)

    monkeypatch.setattr(artifacts, "publish", interrupt)
    with pytest.raises(KeyboardInterrupt):
        view.export_buyer_evidence_view("fixture", config, tmp_path / "out")
    assert list((tmp_path / "out").glob("*.html")) == []
