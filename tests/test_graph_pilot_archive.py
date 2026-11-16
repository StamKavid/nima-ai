"""Recovery checks use real private files; fixtures are not company evidence."""

import hashlib
import os
import stat
from dataclasses import replace
from pathlib import Path
from typing import Literal, Never, cast
from uuid import UUID

import pytest

from nima.evidence import artifacts
from nima.graph.pilot_archive import (
    ArchiveBinding,
    PilotArchiveError,
    RawReference,
    RecoveryLimits,
    recover,
)
from nima.ingestion.archive import Archive


def stored(
    tmp_path: Path, body: bytes = b"original"
) -> tuple[Archive, RawReference, ArchiveBinding]:
    archive = Archive(tmp_path / "archive")
    ref = RawReference("kimdis", UUID(int=1), archive.store(body))
    return archive, ref, ArchiveBinding(ref.source, ref.run_id, archive.root)


def state(root: Path) -> dict[str, tuple[object, ...]]:
    result: dict[str, tuple[object, ...]] = {}
    for path in (root, *root.rglob("*")):
        info = path.stat()
        result[str(path.relative_to(root))] = (
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
            path.read_bytes() if path.is_file() else None,
        )
    return result


def test_recovery_deduplicates_locations_preserves_aliases_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, ref, binding = stored(tmp_path, "αρχικό κείμενο".encode())
    other = RawReference("gemi", UUID(int=2), ref.raw_sha256)
    before = state(archive.root)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Recovery must not initialize archives, open SQL or make HTTP requests")

    monkeypatch.setattr(Archive, "__init__", forbidden)
    monkeypatch.setattr("httpx.Client", forbidden)
    monkeypatch.setattr("nima.storage.postgres._connect", forbidden)
    result = recover(
        (ref, ref, other), (binding, ArchiveBinding("gemi", other.run_id, archive.root))
    )
    assert len(result.objects) == 1
    assert result.objects[0].references == (ref, ref, other)
    assert result.objects[0].raw_sha256 == ref.raw_sha256
    assert result.objects[0].body == "αρχικό κείμενο".encode()
    assert result.total_bytes == len("αρχικό κείμενο".encode())
    assert state(archive.root) == before


def test_missing_archive_is_not_created_and_errors_hide_paths(tmp_path: Path) -> None:
    root = tmp_path / "private-sentinel"
    ref = RawReference("kimdis", UUID(int=1), "0" * 64)
    with pytest.raises(PilotArchiveError, match="^pilot_archive$") as caught:
        recover((ref,), (ArchiveBinding("kimdis", ref.run_id, root),))
    assert caught.value.reason == "pilot_archive"
    assert not root.exists()


def test_corrupt_bytes_are_rejected_without_repair(tmp_path: Path) -> None:
    archive, ref, binding = stored(tmp_path)
    blob = archive.root / "objects" / ref.raw_sha256[:2] / f"{ref.raw_sha256}.body"
    blob.write_bytes(b"tampered")
    before = state(archive.root)
    with pytest.raises(PilotArchiveError, match="^pilot_archive$"):
        recover((ref,), (binding,))
    assert state(archive.root) == before


def test_exact_body_and_total_limits_and_no_truncation(tmp_path: Path) -> None:
    archive, ref, binding = stored(tmp_path, b"1234")
    limits = RecoveryLimits(max_objects=1, max_object_bytes=4, max_total_bytes=4)
    assert recover((ref,), (binding,), limits=limits).total_bytes == 4
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref,), (binding,), limits=RecoveryLimits(max_object_bytes=3))
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref,), (binding,), limits=RecoveryLimits(max_total_bytes=3))
    assert stat.S_IMODE(archive.root.stat().st_mode) == 0o700
    assert hashlib.sha256(recover((ref,), (binding,)).objects[0].body).hexdigest() == ref.raw_sha256


@pytest.mark.parametrize("field", ["max_objects", "max_object_bytes", "max_total_bytes"])
@pytest.mark.parametrize("value", [True, 0, -1, 2**63, 1.5, "private-sentinel"])
def test_invalid_limits_fail_before_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    _, ref, binding = stored(tmp_path)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid limits must not open any directories")

    monkeypatch.setattr(artifacts, "directory", forbidden)
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref,), (binding,), limits=replace(RecoveryLimits(), **{field: cast(int, value)}))


@pytest.mark.parametrize("bad", ["", "../private-sentinel", "A" * 64, True, None])
def test_invalid_digests_fail_without_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: object
) -> None:
    _, ref, binding = stored(tmp_path)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("An invalid reference must not access files")

    monkeypatch.setattr(artifacts, "directory", forbidden)
    with pytest.raises(PilotArchiveError, match="^pilot_input$"):
        recover((replace(ref, raw_sha256=cast(str, bad)),), (binding,))


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "unmapped",
        "duplicate",
        "extra",
        "relative",
        "parent",
        "git",
        "null",
        "source",
        "run",
        "reference_type",
        "binding_type",
        "references_type",
        "bindings_type",
        "aliases",
    ],
)
def test_invalid_bindings_and_references_fail_before_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    _, ref, binding = stored(tmp_path)
    refs: tuple[RawReference, ...] = (ref,)
    bindings: tuple[ArchiveBinding, ...] = (binding,)
    if case == "empty":
        refs = ()
    elif case == "unmapped":
        refs = (replace(ref, run_id=UUID(int=2)),)
    elif case == "duplicate":
        bindings = (binding, binding)
    elif case == "extra":
        bindings = (binding, replace(binding, run_id=UUID(int=2)))
    elif case in {"relative", "parent", "git", "null"}:
        paths = {
            "relative": Path("relative"),
            "parent": tmp_path / ".." / "private-sentinel",
            "git": tmp_path / ".git" / "private-sentinel",
            "null": tmp_path / "\x00",
        }
        bindings = (replace(binding, root=paths[case]),)
    elif case == "source":
        refs = (replace(ref, source=cast(Literal["kimdis", "gemi"], "publicity-manual")),)
    elif case == "run":
        bindings = (replace(binding, run_id=cast(UUID, "private-sentinel")),)
    elif case == "reference_type":
        refs = (cast(RawReference, object()),)
    elif case == "binding_type":
        bindings = (cast(ArchiveBinding, object()),)
    elif case == "references_type":
        refs = cast(tuple[RawReference, ...], [ref])
    elif case == "bindings_type":
        bindings = cast(tuple[ArchiveBinding, ...], [binding])
    else:
        refs = (ref,) * 501

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Invalid mapping must fail before I/O")

    monkeypatch.setattr(artifacts, "directory", forbidden)
    with pytest.raises(PilotArchiveError, match="^pilot_input$"):
        recover(refs, bindings)


def test_all_sizes_and_location_counts_are_checked_before_body_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, ref, binding = stored(tmp_path, b"abc")
    other = replace(ref, raw_sha256=archive.store(b"def"))
    original = artifacts.read

    def no_body(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        assert not name.endswith(".body"), "Over-budget selection read source bytes"
        return original(parent, name, limit=limit, private=private)

    monkeypatch.setattr(artifacts, "read", no_body)
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref, other), (binding,), limits=RecoveryLimits(max_total_bytes=5))
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref, other), (binding,), limits=RecoveryLimits(max_objects=1))


def test_thirty_two_locations_and_five_hundred_aliases_are_allowed(tmp_path: Path) -> None:
    archive, ref, binding = stored(tmp_path, b"\x00")
    refs = tuple(replace(ref, raw_sha256=archive.store(bytes([i]))) for i in range(33))
    assert len(recover(refs[:32], (binding,)).objects) == 32
    assert len(recover((ref,) * 500, (binding,)).objects[0].references) == 500
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover(refs, (binding,))


def test_identical_hashes_in_different_roots_count_twice(tmp_path: Path) -> None:
    first, ref, binding = stored(tmp_path / "one", b"same")
    second, other, other_binding = stored(tmp_path / "two", b"same")
    other = replace(other, run_id=UUID(int=2))
    other_binding = replace(other_binding, run_id=other.run_id)
    result = recover((ref, other), (binding, other_binding))
    assert first.root != second.root and len(result.objects) == 2 and result.total_bytes == 8
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref, other), (binding, other_binding), limits=RecoveryLimits(max_total_bytes=7))


def test_gemi_source_ceiling_still_applies_to_deduplicated_aliases(tmp_path: Path) -> None:
    from nima.sources.gemi import MAX_BODY

    _, ref, binding = stored(tmp_path, b"x" * (MAX_BODY + 1))
    other = RawReference("gemi", UUID(int=2), ref.raw_sha256)
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref, other), (binding, ArchiveBinding("gemi", other.run_id, binding.root)))


def test_wrong_limit_type_is_redacted(tmp_path: Path) -> None:
    _, ref, binding = stored(tmp_path)
    with pytest.raises(PilotArchiveError, match="^pilot_limit$"):
        recover((ref,), (binding,), limits=cast(RecoveryLimits, "private-sentinel"))


def test_descriptor_cleanup_on_late_hash_failure(tmp_path: Path) -> None:
    archive, ref, binding = stored(tmp_path)
    blob = archive.root / "objects" / ref.raw_sha256[:2] / f"{ref.raw_sha256}.body"
    blob.write_bytes(b"tampered")
    before = set(os.listdir("/proc/self/fd"))
    with pytest.raises(PilotArchiveError, match="^pilot_archive$"):
        recover((ref,), (binding,))
    assert set(os.listdir("/proc/self/fd")) == before


@pytest.mark.parametrize(
    "damage",
    [
        "root_mode",
        "objects_mode",
        "bucket_mode",
        "body_mode",
        "marker_mode",
        "marker",
        "ignore",
        "missing_body",
        "fifo",
        "directory",
        "body_link",
        "bucket_link",
        "objects_link",
        "root_link",
    ],
)
def test_unsafe_or_incomplete_archives_fail_without_repair(tmp_path: Path, damage: str) -> None:
    archive, ref, binding = stored(tmp_path)
    bucket = archive.root / "objects" / ref.raw_sha256[:2]
    body = bucket / f"{ref.raw_sha256}.body"
    locations = {
        "root": archive.root,
        "objects": archive.root / "objects",
        "bucket": bucket,
        "body": body,
        "marker": archive.root / ".nima-archive",
    }
    if damage.endswith("_mode"):
        path = locations[damage.removesuffix("_mode")]
        path.chmod(0o755 if path.is_dir() else 0o644)
    elif damage in {"marker", "ignore"}:
        (archive.root / (".nima-archive" if damage == "marker" else ".gitignore")).write_bytes(
            b"bad"
        )
    elif damage.endswith("_link"):
        path = locations[damage.removesuffix("_link")]
        target = path.with_name(path.name + "-original")
        path.rename(target)
        path.symlink_to(target, target_is_directory=target.is_dir())
    else:
        body.unlink()
        if damage == "fifo":
            os.mkfifo(body, 0o600)
        elif damage == "directory":
            body.mkdir(mode=0o700)
    with pytest.raises(PilotArchiveError, match="^pilot_archive$"):
        recover((ref,), (binding,))


def test_a_body_replaced_after_read_is_not_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, ref, binding = stored(tmp_path)
    blob = archive.root / "objects" / ref.raw_sha256[:2] / f"{ref.raw_sha256}.body"
    original = artifacts.read

    def swapped(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        raw = original(parent, name, limit=limit, private=private)
        if name.endswith(".body"):
            temporary = blob.with_suffix(".replacement")
            temporary.write_bytes(raw)
            temporary.chmod(0o600)
            temporary.replace(blob)
        return raw

    monkeypatch.setattr(artifacts, "read", swapped)
    with pytest.raises(PilotArchiveError, match="^pilot_archive$"):
        recover((ref,), (binding,))


@pytest.mark.parametrize("interrupt", [False, True])
def test_open_descriptors_close_on_success_and_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: bool
) -> None:
    _, ref, binding = stored(tmp_path)
    original = artifacts.read

    def interrupted(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        if interrupt and name.endswith(".body"):
            raise KeyboardInterrupt
        return original(parent, name, limit=limit, private=private)

    monkeypatch.setattr(artifacts, "read", interrupted)
    before = set(os.listdir("/proc/self/fd"))
    if interrupt:
        with pytest.raises(KeyboardInterrupt):
            recover((ref,), (binding,))
    else:
        recover((ref,), (binding,))
    assert set(os.listdir("/proc/self/fd")) == before
