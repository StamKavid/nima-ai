"""Private immutable preparation never becomes a verification receipt."""

import hashlib
import json
import os
import signal
import socket
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from nima.egress.remote_bundle import RemoteBundleError, prepare_bundle, read_bundle
from tests.test_remote_config import configuration as configuration
from tests.test_remote_config import private_config as private_config


def test_preparation_preserves_exact_bytes_and_never_copies_credentials(
    private_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("offline preparation attempted external work")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    raw = private_config.read_bytes()
    destination = private_config.parent / "state" / "bundle"
    prepared = prepare_bundle(private_config, destination)
    assert prepared.directory == destination
    assert prepared.document.body == raw
    assert prepared.document.sha256 == hashlib.sha256(raw).hexdigest()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert {p.name for p in destination.iterdir()} == {
        "configuration.json",
        "manifest.json",
        ".gitignore",
    }
    for file in destination.iterdir():
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
        assert b"private-credential-sentinel" not in file.read_bytes()
    manifest = json.loads((destination / "manifest.json").read_bytes())
    assert manifest["version"] == "remote-worker-bundle-v1"
    assert manifest["scope"] == "offline-preparation"
    assert not any("verified" in key or "ready" in key for key in manifest)
    assert prepared == read_bundle(destination, expected_manifest_sha256=prepared.manifest_sha256)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()}
    directory_time = destination.stat().st_mtime_ns
    assert prepare_bundle(private_config, destination) == prepared
    assert destination.stat().st_mtime_ns == directory_time
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()}


def test_canonical_manifest_hashes_exact_original_configuration(private_config: Path) -> None:
    destination = private_config.parent / "state" / "bundle"
    result = prepare_bundle(private_config, destination)
    value = json.loads((destination / "manifest.json").read_bytes())
    assert value == {
        "version": "remote-worker-bundle-v1",
        "scope": "offline-preparation",
        "members": [
            {"name": ".gitignore", "bytes": 2, "sha256": hashlib.sha256(b"*\n").hexdigest()},
            {
                "name": "configuration.json",
                "bytes": len(private_config.read_bytes()),
                "sha256": hashlib.sha256(private_config.read_bytes()).hexdigest(),
            },
        ],
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    assert (destination / "manifest.json").read_bytes() == raw
    assert result.manifest_sha256 == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "fault",
    [
        "config_changed",
        "config_missing",
        "config_huge",
        "manifest_changed",
        "manifest_missing",
        "manifest_huge",
        "manifest_duplicates",
        "manifest_whitespace",
        "extra",
        "temp_extra",
        "missing_gitignore",
        "wrong_gitignore",
        "file_mode",
        "directory_mode",
        "symlink_file",
        "symlink_directory",
        "fifo",
        "hardlink",
    ],
)
def test_missing_corrupt_or_unsafe_bundle_is_never_repaired(
    private_config: Path,
    fault: str,
) -> None:
    destination = private_config.parent / "state" / "bundle"
    prepared = prepare_bundle(private_config, destination)
    config = destination / "configuration.json"
    manifest = destination / "manifest.json"
    if fault == "config_changed":
        config.write_bytes(config.read_bytes() + b" ")
    if fault == "config_missing":
        config.unlink()
    if fault == "config_huge":
        config.write_bytes(b"x" * 16385)
    if fault == "manifest_changed":
        manifest.write_bytes(b"{}\n")
    if fault == "manifest_missing":
        manifest.unlink()
    if fault == "manifest_huge":
        manifest.write_bytes(b"x" * 65537)
    if fault == "manifest_duplicates":
        manifest.write_bytes(
            manifest.read_bytes().replace(b"{", b'{"scope":"offline-preparation",', 1)
        )
    if fault == "manifest_whitespace":
        manifest.write_bytes(manifest.read_bytes() + b" ")
    if fault == "extra":
        (destination / "foreign").write_bytes(b"unrelated")
    if fault == "temp_extra":
        (destination / ".tmp-leftover").write_bytes(b"incomplete")
    if fault == "missing_gitignore":
        (destination / ".gitignore").unlink()
    if fault == "wrong_gitignore":
        (destination / ".gitignore").write_bytes(b"ignored-no-longer")
    if fault == "file_mode":
        config.chmod(0o644)
    if fault == "directory_mode":
        destination.chmod(0o755)
    if fault == "symlink_file":
        config.unlink()
        config.symlink_to(private_config)
    if fault == "symlink_directory":
        moved = destination.with_name("original")
        destination.rename(moved)
        destination.symlink_to(moved)
    if fault == "fifo":
        config.unlink()
        os.mkfifo(config, 0o600)
    if fault == "hardlink":
        os.link(config, private_config.parent / "external-alias")
    before = {p.name: (p.lstat().st_ino, p.lstat().st_mode) for p in destination.iterdir()}
    with pytest.raises(RemoteBundleError, match="^remote_bundle$"):
        read_bundle(destination, expected_manifest_sha256=prepared.manifest_sha256)
    with pytest.raises(RemoteBundleError, match="^remote_bundle$"):
        prepare_bundle(private_config, destination)
    assert before == {p.name: (p.lstat().st_ino, p.lstat().st_mode) for p in destination.iterdir()}


@pytest.mark.parametrize("fault", ["sibling", "relative", "git", "foreign", "bad_input"])
def test_rejected_preparation_never_writes_or_changes_existing_files(
    private_config: Path,
    fault: str,
) -> None:
    state = private_config.parent / "state"
    destination = state / "bundle"
    if fault == "sibling":
        destination = state.parent / "elsewhere"
    if fault == "relative":
        destination = Path("relative/bundle")
    if fault == "git":
        destination = state / ".git"
    if fault == "foreign":
        destination.mkdir(mode=0o700)
        (destination / "foreign").write_bytes(b"keep")
    if fault == "bad_input":
        private_config.write_bytes(b"{}")
    before = sorted(
        str(p.relative_to(private_config.parent)) for p in private_config.parent.rglob("*")
    )
    with pytest.raises(RemoteBundleError):
        prepare_bundle(private_config, destination)
    assert before == sorted(
        str(p.relative_to(private_config.parent)) for p in private_config.parent.rglob("*")
    )


def test_different_input_bytes_cannot_overwrite_an_existing_bundle(private_config: Path) -> None:
    destination = private_config.parent / "state" / "bundle"
    prepare_bundle(private_config, destination)
    before = {p.name: p.read_bytes() for p in destination.iterdir()}
    private_config.write_bytes(private_config.read_bytes() + b" ")
    with pytest.raises(RemoteBundleError):
        prepare_bundle(private_config, destination)
    assert before == {p.name: p.read_bytes() for p in destination.iterdir()}


def test_member_change_after_read_is_not_hidden_by_cached_bytes(
    private_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.evidence import artifacts

    destination = private_config.parent / "state" / "bundle"
    prepared = prepare_bundle(private_config, destination)
    original = artifacts.read

    def changed(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        raw = original(parent, name, limit=limit, private=private)
        if name == "manifest.json":
            target = destination / "configuration.json"
            target.write_bytes(target.read_bytes() + b" ")
        return raw

    monkeypatch.setattr(artifacts, "read", changed)
    with pytest.raises(RemoteBundleError):
        read_bundle(destination, expected_manifest_sha256=prepared.manifest_sha256)


def test_directory_replacement_after_open_cannot_change_the_bundle_binding(
    private_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    from nima.evidence import artifacts

    destination = private_config.parent / "state" / "bundle"
    prepared = prepare_bundle(private_config, destination)
    original = artifacts.read
    swapped = False

    def replace_directory(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        nonlocal swapped
        raw = original(parent, name, limit=limit, private=private)
        if not swapped:
            swapped = True
            old = destination.with_name("old")
            destination.rename(old)
            shutil.copytree(old, destination)
        return raw

    monkeypatch.setattr(artifacts, "read", replace_directory)
    with pytest.raises(RemoteBundleError):
        read_bundle(destination, expected_manifest_sha256=prepared.manifest_sha256)
    assert swapped


def test_process_killed_during_publication_leaves_unusable_unrepaired_output(
    private_config: Path,
) -> None:
    destination = private_config.parent / "state" / "bundle"
    script = """
import os,signal,sys
from pathlib import Path
from nima.egress.remote_bundle import prepare_bundle
from nima.evidence import artifacts
original=artifacts.publish
def stop_after_configuration(parent,name,body):
    original(parent,name,body)
    if name=='configuration.json':
        os.kill(os.getpid(),signal.SIGKILL)
artifacts.publish=stop_after_configuration
prepare_bundle(Path(sys.argv[1]),Path(sys.argv[2]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(private_config), str(destination)],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == -signal.SIGKILL
    assert {p.name for p in destination.iterdir()} == {"configuration.json", ".gitignore"}
    before = {p.name: p.read_bytes() for p in destination.iterdir()}
    with pytest.raises(RemoteBundleError):
        read_bundle(destination, expected_manifest_sha256="1" * 64)
    with pytest.raises(RemoteBundleError):
        prepare_bundle(private_config, destination)
    assert before == {p.name: p.read_bytes() for p in destination.iterdir()}


def test_bundle_manifest_is_not_a_fixture_verification_receipt(private_config: Path) -> None:
    from nima.egress.receipt import ReceiptError, read_receipt

    destination = private_config.parent / "state" / "bundle"
    prepare_bundle(private_config, destination)
    with pytest.raises(ReceiptError):
        read_receipt((destination / "manifest.json").read_bytes())


def test_reader_failure_closes_all_bundle_descriptors(
    private_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.evidence import artifacts

    destination = private_config.parent / "state" / "bundle"
    prepared = prepare_bundle(private_config, destination)

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise OSError("private-value-sentinel")

    monkeypatch.setattr(artifacts, "read", unavailable)
    before = len(list(Path("/proc/self/fd").iterdir()))
    for _ in range(10):
        with pytest.raises(RemoteBundleError, match="^remote_bundle$"):
            read_bundle(destination, expected_manifest_sha256=prepared.manifest_sha256)
    assert len(list(Path("/proc/self/fd").iterdir())) == before


def test_reader_requires_the_independently_retained_manifest_pin(private_config: Path) -> None:
    destination = private_config.parent / "state" / "bundle"
    prepare_bundle(private_config, destination)
    with pytest.raises(RemoteBundleError):
        read_bundle(destination, expected_manifest_sha256="0" * 64)


def test_consistent_rewrite_of_members_and_manifest_still_fails_the_original_pin(
    private_config: Path,
) -> None:
    destination = private_config.parent / "state" / "bundle"
    prepared = prepare_bundle(private_config, destination)
    configuration_file = destination / "configuration.json"
    raw = configuration_file.read_bytes() + b" "
    configuration_file.write_bytes(raw)
    manifest_file = destination / "manifest.json"
    manifest = json.loads(manifest_file.read_bytes())
    for member in manifest["members"]:
        if member["name"] == "configuration.json":
            member["bytes"] = len(raw)
            member["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_file.write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    with pytest.raises(RemoteBundleError):
        read_bundle(destination, expected_manifest_sha256=prepared.manifest_sha256)


@pytest.mark.parametrize("pin", ["", "latest", "A" * 64, True, None])
def test_invalid_manifest_pin_fails_before_reading(
    private_config: Path,
    pin: Any,
) -> None:
    with pytest.raises(RemoteBundleError, match="^remote_bundle$"):
        read_bundle(private_config.parent / "not-created", expected_manifest_sha256=pin)
