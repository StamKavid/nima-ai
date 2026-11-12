"""Real filesystem intake of synthetic opaque public-document captures."""

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from nima.evidence import EvidenceError
from nima.evidence.intake import intake
from tests.test_publicity_evidence_policy import capture, manifest

PDF = b"%PDF-1.7\nsynthetic evidence\n%%EOF\n"


def inputs(tmp_path: Path, body: bytes = PDF) -> tuple[Path, Path, Path]:
    source = tmp_path / "input"
    source.mkdir(mode=0o700)
    (source / "αρχεία").mkdir()
    (source / "αρχεία/capture.pdf").write_bytes(body)
    metadata = source / "input.json"
    metadata.write_bytes(manifest())
    return metadata, source, tmp_path / "archive"


def ingest(tmp_path: Path) -> tuple[Path, UUID, dict[str, object]]:
    metadata, source, archive = inputs(tmp_path)
    request_id = uuid4()
    return archive, request_id, intake(request_id, metadata, source, archive)


def test_preserves_exact_bytes_and_private_channel(tmp_path: Path) -> None:
    archive, request_id, summary = ingest(tmp_path)
    saved = json.loads((archive / "bundles" / f"{request_id.hex}.json").read_bytes())
    assert saved["acquisition_channel"] == "publicity-manual"
    assert saved["source_family"] == "gemi"
    assert saved["input"]["records"][0]["gemi_number"] == "000123"
    assert summary["identity_verified"] is False
    assert summary["origin_verified"] is False
    assert summary["records"] == 1
    digest = saved["objects"][0]["sha256"]
    assert (archive / "objects" / f"{digest}.body").read_bytes() == PDF
    assert all(
        p.stat().st_mode & 0o777 == (0o700 if p.is_dir() else 0o600)
        for p in [archive, *archive.rglob("*")]
    )
    assert (
        str(tmp_path).encode() not in (archive / "bundles" / f"{request_id.hex}.json").read_bytes()
    )


def test_matching_replay_keeps_first_manifest_and_conflict_cannot_replace(tmp_path: Path) -> None:
    metadata, source, archive = inputs(tmp_path)
    request_id = uuid4()
    first = intake(request_id, metadata, source, archive)
    path = archive / "bundles" / f"{request_id.hex}.json"
    original = path.read_bytes()
    second = intake(request_id, metadata, source, archive)
    assert path.read_bytes() == original
    assert second == {**first, "reused": True}
    (source / "αρχεία/capture.pdf").write_bytes(PDF + b"changed")
    with pytest.raises(EvidenceError, match="^conflict$"):
        intake(request_id, metadata, source, archive)
    assert path.read_bytes() == original


@pytest.mark.parametrize("kind", ["symlink", "parent_symlink", "fifo", "oversized", "signature"])
def test_rejects_unsafe_input_without_completed_bundle(tmp_path: Path, kind: str) -> None:
    metadata, source, archive = inputs(tmp_path)
    document = source / "αρχεία/capture.pdf"
    if kind == "symlink":
        document.unlink()
        document.symlink_to(metadata)
    elif kind == "parent_symlink":
        (source / "αρχεία").rename(source / "original")
        (source / "αρχεία").symlink_to(source / "original", target_is_directory=True)
    elif kind == "fifo":
        document.unlink()
        os.mkfifo(document)
    elif kind == "oversized":
        with document.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
    else:
        document.write_bytes(b"<html>not a PDF</html>")
    with pytest.raises(EvidenceError):
        intake(uuid4(), metadata, source, archive)
    assert not list(archive.glob("bundles/*.json"))


def test_rejects_unrelated_or_public_archive_without_touching_it(tmp_path: Path) -> None:
    metadata, source, archive = inputs(tmp_path)
    archive.mkdir(mode=0o700)
    original = archive / "important.txt"
    original.write_bytes(b"keep")
    with pytest.raises(EvidenceError):
        intake(uuid4(), metadata, source, archive)
    assert list(archive.iterdir()) == [original]
    original.unlink()
    archive.chmod(0o755)
    with pytest.raises(EvidenceError):
        intake(uuid4(), metadata, source, archive)
    assert archive.stat().st_mode & 0o777 == 0o755


def test_read_failure_and_invalid_manifest_do_not_complete(tmp_path: Path) -> None:
    metadata, source, archive = inputs(tmp_path)
    metadata.write_bytes(manifest(capture(file="missing.pdf")))
    with pytest.raises(EvidenceError):
        intake(uuid4(), metadata, source, archive)
    assert not list(archive.glob("bundles/*.json"))
    metadata.write_bytes(b"bad")
    with pytest.raises(EvidenceError, match="^input$"):
        intake(uuid4(), metadata, source, archive)


@pytest.mark.parametrize(
    ("media", "body"),
    [
        ("image/png", b"\x89PNG\r\n\x1a\nsynthetic"),
        ("image/jpeg", b"\xff\xd8\xffsynthetic"),
    ],
)
def test_image_capture_is_opaque_exact_evidence(tmp_path: Path, media: str, body: bytes) -> None:
    metadata, source, archive = inputs(tmp_path, body)
    metadata.write_bytes(manifest(capture(media_type=media, capture_method="screenshot")))
    assert intake(uuid4(), metadata, source, archive)["extraction_complete"] is False
    assert [p.read_bytes() for p in (archive / "objects").glob("*.body")] == [body]


@pytest.mark.parametrize("kind", ["root_symlink", "parent_symlink", "git_internals"])
def test_archive_cannot_follow_links_or_write_git_internals(tmp_path: Path, kind: str) -> None:
    metadata, source, archive = inputs(tmp_path)
    target = tmp_path / (".git" if kind == "git_internals" else "target")
    target.mkdir(mode=0o700)
    if kind == "root_symlink":
        archive.symlink_to(target, target_is_directory=True)
    elif kind == "parent_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(target, target_is_directory=True)
        archive = alias / "archive"
    else:
        archive = target / "archive"
    with pytest.raises(EvidenceError):
        intake(uuid4(), metadata, source, archive)
    assert list(target.iterdir()) == []
