"""Private Linux/POSIX no-clobber report publication using directory descriptors.

https://docs.python.org/3.12/library/os.html#os.link
"""

import hashlib
import json
import os
import stat
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from nima.identity import MAX_REPORT_BYTES, AssessmentError


def encode(value: object, *, limit: int | None = None) -> bytes:
    limit = MAX_REPORT_BYTES if limit is None else limit
    if type(limit) is not int or not 1 <= limit <= MAX_REPORT_BYTES:
        raise AssessmentError("assessment_limit")
    body = bytearray()
    encoder = json.JSONEncoder(
        ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    for chunk in encoder.iterencode(value):
        part = chunk.encode()
        if len(body) + len(part) > limit:
            raise AssessmentError("assessment_limit")
        body.extend(part)
    return bytes(body)


def _directory(path: Path) -> int:
    absolute = path.absolute()
    if ".." in path.parts or ".git" in absolute.parts:
        raise AssessmentError("output_path")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            with suppress(FileExistsError):
                os.mkdir(part, 0o700, dir_fd=descriptor)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise AssessmentError("output_path")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _verify(directory: int, name: str, body: bytes) -> None:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_size != len(body)
            or stream.read(len(body) + 1) != body
        ):
            raise AssessmentError("output_conflict")


def _publish(descriptor: int, final: str, body: bytes) -> None:
    temporary = f".tmp-{uuid4().hex}"
    file = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor
    )
    try:
        with os.fdopen(file, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(
                temporary,
                final,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            _verify(descriptor, final, body)
        os.fsync(descriptor)
    finally:
        os.unlink(temporary, dir_fd=descriptor)


def publish(directory: Path, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    descriptor = _directory(directory)
    try:
        _publish(descriptor, ".gitignore", b"*\n")
        _publish(descriptor, f"{digest}.json", body)
    finally:
        os.close(descriptor)
    return digest
