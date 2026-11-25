"""Bounded read-only recovery of explicitly mapped collector evidence, without keys.

This checks bytes, not publisher authenticity, registry identity or Publicity fields.
Reuse descriptor-relative reads: https://docs.python.org/3.12/library/os.html#os.open
"""

import hashlib
import os
import re
import stat
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from nima.evidence import EvidenceError, artifacts
from nima.ingestion.archive import MARKER
from nima.sources.gemi import MAX_BODY

MAX_REFERENCES = 500
MAX_OBJECTS = 32
MAX_OBJECT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class PilotArchiveError(ValueError):
    """Fixed reason only; no source labels, filesystem paths or driver details."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class RawReference:
    source: Literal["kimdis", "gemi", "diavgeia"]
    run_id: UUID
    raw_sha256: str


@dataclass(frozen=True)
class ArchiveBinding:
    source: Literal["kimdis", "gemi", "diavgeia"]
    run_id: UUID
    root: Path


@dataclass(frozen=True)
class RecoveryLimits:
    max_objects: int = MAX_OBJECTS
    max_object_bytes: int = MAX_OBJECT_BYTES
    max_total_bytes: int = MAX_TOTAL_BYTES


DEFAULT_LIMITS = RecoveryLimits()


@dataclass(frozen=True)
class RecoveredObject:
    raw_sha256: str
    references: tuple[RawReference, ...]
    body: bytes


@dataclass(frozen=True)
class ArchiveRecovery:
    objects: tuple[RecoveredObject, ...]
    total_bytes: int


def _selection(
    references: tuple[RawReference, ...],
    bindings: tuple[ArchiveBinding, ...],
    limits: RecoveryLimits,
) -> dict[tuple[Path, str], list[RawReference]]:
    if not isinstance(limits, RecoveryLimits) or any(
        type(value) is not int or not 1 <= value <= ceiling
        for value, ceiling in (
            (limits.max_objects, MAX_OBJECTS),
            (limits.max_object_bytes, MAX_OBJECT_BYTES),
            (limits.max_total_bytes, MAX_TOTAL_BYTES),
        )
    ):
        raise PilotArchiveError("pilot_limit")
    if (
        not isinstance(references, tuple)
        or not 1 <= len(references) <= MAX_REFERENCES
        or not isinstance(bindings, tuple)
        or not 1 <= len(bindings) <= MAX_REFERENCES
    ):
        raise PilotArchiveError("pilot_input")
    roots = {}
    for binding in bindings:
        if (
            not isinstance(binding, ArchiveBinding)
            or binding.source not in ("kimdis", "gemi", "diavgeia")
            or not isinstance(binding.run_id, UUID)
            or not isinstance(binding.root, Path)
            or not binding.root.is_absolute()
            or any(part in {"..", ".git"} for part in binding.root.parts)
            or "\x00" in str(binding.root)
            or (binding.source, binding.run_id) in roots
        ):
            raise PilotArchiveError("pilot_input")
        roots[binding.source, binding.run_id] = binding.root
    selected: dict[tuple[Path, str], list[RawReference]] = {}
    used = set()
    for ref in references:
        if (
            not isinstance(ref, RawReference)
            or ref.source not in ("kimdis", "gemi", "diavgeia")
            or not isinstance(ref.run_id, UUID)
            or not isinstance(ref.raw_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", ref.raw_sha256) is None
            or (ref.source, ref.run_id) not in roots
        ):
            raise PilotArchiveError("pilot_input")
        used.add((ref.source, ref.run_id))
        selected.setdefault((roots[ref.source, ref.run_id], ref.raw_sha256), []).append(ref)
    if used != roots.keys():
        raise PilotArchiveError("pilot_input")
    if len(selected) > limits.max_objects:
        raise PilotArchiveError("pilot_limit")
    return selected


def recover(
    references: tuple[RawReference, ...],
    bindings: tuple[ArchiveBinding, ...],
    *,
    limits: RecoveryLimits = DEFAULT_LIMITS,
) -> ArchiveRecovery:
    """Preflight all locations before bodies; never initialize/repair an archive.

    Sources/run IDs bind caller-selected roots, not trusted issuer identities.
    Every alias is retained; distinct roots with the same digest count separately.
    """
    selected = _selection(references, bindings, limits)
    try:
        with ExitStack() as stack:
            pending = []
            total = 0
            for (root, digest), aliases in selected.items():
                parent = artifacts.directory(root, private=True)
                stack.callback(os.close, parent)
                if (
                    artifacts.read(parent, ".nima-archive", limit=len(MARKER), private=True)
                    != MARKER.encode()
                    or artifacts.read(parent, ".gitignore", limit=2, private=True) != b"*\n"
                ):
                    raise PilotArchiveError("pilot_archive")
                objects = artifacts.child_directory(parent, "objects")
                stack.callback(os.close, objects)
                bucket = artifacts.child_directory(objects, digest[:2])
                stack.callback(os.close, bucket)
                name = f"{digest}.body"
                info = os.stat(name, dir_fd=bucket, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise PilotArchiveError("pilot_archive")
                artifacts.check_private(info, 0o600)
                ceiling = min(
                    limits.max_object_bytes,
                    MAX_BODY if any(ref.source == "gemi" for ref in aliases) else MAX_OBJECT_BYTES,
                )
                total += info.st_size
                if info.st_size > ceiling or total > limits.max_total_bytes:
                    raise PilotArchiveError("pilot_limit")
                pending.append((bucket, name, digest, tuple(aliases), info))
            recovered = []
            for bucket, name, digest, refs, before in pending:
                body = artifacts.read(bucket, name, limit=before.st_size, private=True)
                after = os.stat(name, dir_fd=bucket, follow_symlinks=False)
                if (
                    artifacts._snapshot(before) != artifacts._snapshot(after)
                    or hashlib.sha256(body).hexdigest() != digest
                ):
                    raise PilotArchiveError("pilot_archive")
                recovered.append(RecoveredObject(digest, refs, body))
        return ArchiveRecovery(tuple(recovered), total)
    except (EvidenceError, OSError, UnicodeError):
        raise PilotArchiveError("pilot_archive") from None
