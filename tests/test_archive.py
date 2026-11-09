"""Evidence is immutable, private, and kept outside Git."""

import hashlib
import json
import stat
from pathlib import Path

import pytest

from nima.ingestion.archive import Archive, ArchiveError


def test_recovery_reads_are_bounded_and_hash_verified(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "archive")
    digest = archive.store(b"original")
    assert archive.read(digest, max_bytes=8) == b"original"
    with pytest.raises(ArchiveError):
        archive.read(digest, max_bytes=7)
    with pytest.raises(ArchiveError):
        archive.read("../../escape", max_bytes=8)
    blob = archive.root / "objects" / digest[:2] / f"{digest}.body"
    blob.write_bytes(b"changed")
    with pytest.raises(ArchiveError):
        archive.read(digest, max_bytes=8)


def test_exact_bodies_are_reused_and_runs_are_distinct(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "archive")
    body = b'{"title":"original bytes"}\n'
    digest = archive.store(body)
    assert digest == hashlib.sha256(body).hexdigest()
    assert archive.store(body) == digest
    blob = archive.root / "objects" / digest[:2] / f"{digest}.body"
    assert blob.read_bytes() == body
    first = archive.start_run({"status": "running"})
    second = Archive(archive.root).start_run({"status": "running"})
    assert first != second
    archive.write_manifest(first, {"status": "complete"})
    assert json.loads((first / "manifest.json").read_bytes()) == {"status": "complete"}
    archive.append(first, "normalized", [{"net_amount": "0.10"}])
    archive.append(first, "normalized", [{"net_amount": None}])
    assert len((first / "normalized.jsonl").read_text().splitlines()) == 2
    for path in archive.root.rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
    assert stat.S_IMODE(archive.root.stat().st_mode) == 0o700
    assert (archive.root / ".gitignore").read_text() == "*\n"


def test_corrupt_existing_blob_fails_without_overwrite(tmp_path: Path) -> None:
    archive = Archive(tmp_path / "archive")
    digest = archive.store(b"body")
    blob = archive.root / "objects" / digest[:2] / f"{digest}.body"
    blob.write_bytes(b"corrupt")
    with pytest.raises(ArchiveError, match="corrupt"):
        archive.store(b"body")
    assert blob.read_bytes() == b"corrupt"


def test_unrelated_directory_and_symlinks_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "keep").write_text("existing")
    with pytest.raises(ArchiveError):
        Archive(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ArchiveError):
        Archive(link)
    archive = Archive(tmp_path / "archive")
    (archive.root / "objects").rmdir()
    (archive.root / "objects").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ArchiveError):
        archive.store(b"body")
    assert not list(tmp_path.glob("*.body"))


def test_atomic_manifest_failure_preserves_previous_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = Archive(tmp_path / "archive")
    run = archive.start_run({"status": "running"})

    def fail(*args: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr("nima.ingestion.archive.os.replace", fail)
    with pytest.raises(OSError):
        archive.write_manifest(run, {"status": "complete"})
    assert json.loads((run / "manifest.json").read_bytes())["status"] == "running"
    assert sorted(p.name for p in run.iterdir()) == ["manifest.json"]
