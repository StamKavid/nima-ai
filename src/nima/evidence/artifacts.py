"""Private POSIX descriptor-based storage, independent of API archives.

https://docs.python.org/3.12/library/os.html#os.open
https://docs.python.org/3.12/library/os.html#os.link
"""

import os
import stat
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from nima.evidence import EvidenceError
from nima.evidence.publicity import relative

MARKER = b"nima-publicity-manual-v1\n"
MARKER_NAME = ".nima-publicity"


def check_private(info: os.stat_result, mode: int) -> None:
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != mode:
        raise EvidenceError("archive_path")


def directory(path: Path, *, create: bool = False, private: bool = False) -> int:
    absolute = path.absolute()
    if ".." in path.parts or ".git" in absolute.parts:
        raise EvidenceError("archive_path")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                os.fsync(descriptor)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        if private:
            check_private(os.fstat(descriptor), 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def child_directory(parent: int, name: str, *, create: bool = False) -> int:
    if create:
        with suppress(FileExistsError):
            os.mkdir(name, 0o700, dir_fd=parent)
        os.fsync(parent)
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        check_private(os.fstat(descriptor), 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _snapshot(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
    parts = relative(name).split("/")
    descriptor = os.dup(parent)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(file, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= limit:
                raise EvidenceError("file_limit")
            if private:
                check_private(before, 0o600)
            body = bytearray()
            while chunk := stream.read(min(65536, limit + 1 - len(body))):
                body.extend(chunk)
                if len(body) > limit:
                    raise EvidenceError("file_limit")
            after = os.fstat(stream.fileno())
            entry = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
            if (
                _snapshot(before) != _snapshot(after)
                or _snapshot(after) != _snapshot(entry)
                or len(body) != after.st_size
            ):
                raise EvidenceError("input_changed")
            return bytes(body)
    finally:
        os.close(descriptor)


def publish(parent: int, name: str, body: bytes) -> None:
    temporary = f".tmp-{uuid4().hex}"
    file = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
    )
    try:
        with os.fdopen(file, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        except FileExistsError:
            if read(parent, name, limit=len(body), private=True) != body:
                raise EvidenceError("conflict") from None
        os.fsync(parent)
    finally:
        os.unlink(temporary, dir_fd=parent)


def initialize(root: int) -> None:
    names = set(os.listdir(root))
    if MARKER_NAME not in names and any(not n.startswith(".tmp-") for n in names):
        raise EvidenceError("archive_path")
    # These directories are created only after the immutable root metadata.
    # Their presence rules out an interrupted, not-yet-initialized root.
    if names & {"objects", "bundles"}:
        validate_root(root)
    publish(root, MARKER_NAME, MARKER)
    publish(root, ".gitignore", b"*\n")
    for name in ("objects", "bundles"):
        os.close(child_directory(root, name, create=True))


def validate_root(root: int) -> None:
    if (
        read(root, MARKER_NAME, limit=len(MARKER), private=True) != MARKER
        or read(root, ".gitignore", limit=2, private=True) != b"*\n"
    ):
        raise EvidenceError("archive_path")
