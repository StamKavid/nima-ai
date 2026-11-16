"""Offline immutable intent bundles; never executable policy or remote receipts."""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from nima.egress.remote_config import (
    CONFIG_LIMIT,
    ConfigDocument,
    decode_config,
    private_directory,
    read_config,
    validate_paths,
)
from nima.evidence import EvidenceError, artifacts

NAMES = frozenset({"configuration.json", "manifest.json", ".gitignore"})


class RemoteBundleError(ValueError):
    """Fixed reason without paths, configuration values or credentials."""


@dataclass(frozen=True, slots=True, repr=False)
class PreparedBundle:
    directory: Path
    document: ConfigDocument
    manifest_sha256: str


def _manifest(raw: bytes) -> bytes:
    files = {".gitignore": b"*\n", "configuration.json": raw}
    value = {
        "version": "remote-worker-bundle-v1",
        "scope": "offline-preparation",
        "members": [
            {"name": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            for name, body in sorted(files.items())
        ],
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _snapshot(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _names(root: int) -> None:
    seen = set()
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.name not in NAMES:
                raise RemoteBundleError("remote_bundle")
            seen.add(entry.name)
    if seen != NAMES:
        raise RemoteBundleError("remote_bundle")


def _members(root: int) -> dict[str, bytes]:
    _names(root)
    before = {name: os.stat(name, dir_fd=root, follow_symlinks=False) for name in NAMES}
    for info in before.values():
        artifacts.check_private(info, 0o600)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RemoteBundleError("remote_bundle")
    result = {
        name: artifacts.read(
            root,
            name,
            private=True,
            limit=CONFIG_LIMIT
            if name == "configuration.json"
            else (2 if name == ".gitignore" else 64 * 1024),
        )
        for name in sorted(NAMES)
    }
    for name, info in before.items():
        after = os.stat(name, dir_fd=root, follow_symlinks=False)
        if _snapshot(info) != _snapshot(after):
            raise RemoteBundleError("remote_bundle")
    return result


def _read(parent: int, root: int, directory: Path, pin: str) -> PreparedBundle:
    before = os.fstat(root)
    values = _members(root)
    if hashlib.sha256(values["manifest.json"]).hexdigest() != pin:
        raise RemoteBundleError("remote_bundle")
    raw = values["configuration.json"]
    config = decode_config(raw)
    validate_paths(config)
    if (
        directory.parent != Path(config.paths.state_dir)
        or values[".gitignore"] != b"*\n"
        or values["manifest.json"] != _manifest(raw)
    ):
        raise RemoteBundleError("remote_bundle")
    if _snapshot(before) != _snapshot(os.fstat(root)) or _snapshot(before) != _snapshot(
        os.stat(directory.name, dir_fd=parent, follow_symlinks=False)
    ):
        raise RemoteBundleError("remote_bundle")
    return PreparedBundle(
        directory, ConfigDocument(config, raw), hashlib.sha256(values["manifest.json"]).hexdigest()
    )


def _parent(directory: Path) -> int:
    if (
        not directory.is_absolute()
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", directory.name) is None
    ):
        raise RemoteBundleError("remote_bundle")
    return private_directory(directory.parent)


def read_bundle(directory: Path, *, expected_manifest_sha256: str) -> PreparedBundle:
    """Read against a caller-retained manifest pin, never trust a self-supplied hash."""
    try:
        if (
            type(expected_manifest_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256) is None
        ):
            raise RemoteBundleError("remote_bundle")
        parent = _parent(directory)
        try:
            root = artifacts.child_directory(parent, directory.name)
            try:
                return _read(parent, root, directory, expected_manifest_sha256)
            finally:
                os.close(root)
        finally:
            os.close(parent)
    except (OSError, EvidenceError, ValueError):
        raise RemoteBundleError("remote_bundle") from None


def prepare_bundle(config_file: Path, directory: Path) -> PreparedBundle:
    """Create only a new child of configured state, or reuse identical full bytes.

    The canonical manifest binds the original configuration bytes, including its
    whitespace. No credential contents are copied. Incomplete/conflicting existing
    output fails without repair; verification and compiled policy are later work.
    """
    try:
        document = read_config(config_file)
        pin = hashlib.sha256(_manifest(document.body)).hexdigest()
        if directory.parent != Path(document.config.paths.state_dir):
            raise RemoteBundleError("remote_bundle")
        parent = _parent(directory)
        try:
            try:
                os.mkdir(directory.name, 0o700, dir_fd=parent)
            except FileExistsError:
                existing = read_bundle(directory, expected_manifest_sha256=pin)
                if existing.document.body != document.body:
                    raise RemoteBundleError("remote_bundle") from None
                return existing
            os.fsync(parent)
            root = artifacts.child_directory(parent, directory.name)
            try:
                for name, body in (
                    (".gitignore", b"*\n"),
                    ("configuration.json", document.body),
                    ("manifest.json", _manifest(document.body)),
                ):
                    artifacts.publish(root, name, body)
                return _read(parent, root, directory, pin)
            finally:
                os.close(root)
        finally:
            os.close(parent)
    except (OSError, EvidenceError, ValueError):
        raise RemoteBundleError("remote_bundle") from None
