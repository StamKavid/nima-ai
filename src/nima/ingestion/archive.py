"""Private, content-addressed evidence for one local collector owner.

Bodies are decoded HTTP entity bytes, not compressed wire captures. Files and
renames are fsynced; run manifests are evidence, not transactional checkpoints.
"""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

MARKER = "nima-evidence-v1\n"


class ArchiveError(ValueError):
    """An archive path or previously stored evidence is unsafe."""


def _no_symlinks(path: Path) -> None:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ArchiveError("Archive paths must not contain symlinks")


def _sync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _directory(path: Path) -> None:
    _no_symlinks(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def _write(path: Path, body: bytes, *, immutable: bool = False) -> None:
    _no_symlinks(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            # Hard-link creation cannot replace existing evidence, even in a race.
            try:
                os.link(temporary, path)
            except FileExistsError:
                _verify(path, hashlib.sha256(body).hexdigest())
        else:
            os.replace(temporary, path)
        _sync_dir(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _verify(path: Path, digest: str) -> None:
    _no_symlinks(path)
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ArchiveError("Existing evidence blob is corrupt")


class Archive:
    """Use a new/empty directory, or an archive initialized by this version."""

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        _no_symlinks(self.root)
        marker = self.root / ".nima-archive"
        _no_symlinks(marker)
        if self.root.exists() and any(self.root.iterdir()):
            if not marker.is_file() or marker.read_text() != MARKER:
                raise ArchiveError("Archive directory is not empty or recognized")
            ignore = self.root / ".gitignore"
            _no_symlinks(ignore)
            if not ignore.is_file() or ignore.read_text() != "*\n":
                raise ArchiveError("Archive Git exclusion is missing or changed")
        else:
            _directory(self.root)
            _write(marker, MARKER.encode())
            _write(self.root / ".gitignore", b"*\n")
        self.root.chmod(0o700)
        for name in ("objects", "runs"):
            _directory(self.root / name)

    def store(self, body: bytes) -> str:
        digest = hashlib.sha256(body).hexdigest()
        directory = self.root / "objects" / digest[:2]
        _directory(directory)
        path = directory / f"{digest}.body"
        if path.exists() or path.is_symlink():
            _verify(path, digest)
        else:
            _write(path, body, immutable=True)
        return digest

    def read(self, digest: str, *, max_bytes: int) -> bytes:
        """Read only bounded, hash-verified evidence without following symlinks."""
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None or max_bytes <= 0:
            raise ArchiveError("Invalid evidence reference or byte limit")
        path = self.root / "objects" / digest[:2] / f"{digest}.body"
        _no_symlinks(path)
        with path.open("rb") as stream:
            body = stream.read(max_bytes + 1)
        if len(body) > max_bytes or hashlib.sha256(body).hexdigest() != digest:
            raise ArchiveError("Evidence exceeds its limit or does not match its hash")
        return body

    def start_run(self, manifest: dict[str, object]) -> Path:
        run = self.root / "runs" / uuid4().hex
        _directory(run)
        _sync_dir(run.parent)
        self.write_manifest(run, manifest)
        return run

    def _run_path(self, run: Path, filename: str) -> Path:
        if run.parent != self.root / "runs" or len(run.name) != 32:
            raise ArchiveError("Run does not belong to this archive")
        path = run / filename
        _no_symlinks(path)
        return path

    def write_manifest(self, run: Path, manifest: dict[str, object]) -> None:
        body = json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2).encode() + b"\n"
        _write(self._run_path(run, "manifest.json"), body)

    def append(self, run: Path, kind: str, rows: list[dict[str, object]]) -> None:
        if kind not in {"normalized", "quarantine"}:
            raise ArchiveError("Unknown derived artifact")
        path = self._run_path(run, f"{kind}.jsonl")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        _sync_dir(run)
