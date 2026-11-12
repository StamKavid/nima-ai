"""Offline private evidence publication, without source/network activity."""

import fcntl
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from nima.evidence import EvidenceError
from nima.evidence.artifacts import child_directory, directory, initialize, publish, read
from nima.evidence.publicity import (
    INPUT_VERSION,
    MAX_COMPLETION,
    MAX_FILE,
    MAX_MANIFEST,
    MAX_TOTAL,
    SIGNATURES,
    VERSION,
    decode,
    encode,
    parse_manifest,
    utc_timestamp,
)


def summary(
    request_id: UUID, count: int, *, reused: bool = False, status: str = "staged"
) -> dict[str, object]:
    return {
        "request_id": request_id.hex,
        "version": VERSION,
        "status": status,
        "records": count,
        "reused": reused,
        "evidence_complete": True,
        "identity_verified": False,
        "origin_verified": False,
        "capture_context_verified": False,
        "extraction_complete": False,
    }


def _manifest(path: Path) -> bytes:
    try:
        parent = directory(path.parent)
        try:
            return read(parent, path.name, limit=MAX_MANIFEST)
        finally:
            os.close(parent)
    except (OSError, EvidenceError):
        raise EvidenceError("input") from None


def intake(
    request_id: UUID, manifest: Path, input_dir: Path, archive_dir: Path
) -> dict[str, object]:
    if not isinstance(request_id, UUID):
        raise EvidenceError("input")
    records = parse_manifest(_manifest(manifest))
    root = -1
    try:
        root = directory(archive_dir, create=True, private=True)
        fcntl.flock(root, fcntl.LOCK_EX)
        initialize(root)
        objects = []
        total = 0
        for index, record in enumerate(records):
            try:
                source = directory(input_dir, private=True)
                try:
                    body = read(source, record.file, limit=MAX_FILE)
                finally:
                    os.close(source)
                if not body.startswith(SIGNATURES[record.media_type]):
                    raise EvidenceError("input")
                total += len(body)
                if total > MAX_TOTAL:
                    raise EvidenceError("input")
            except (OSError, EvidenceError):
                raise EvidenceError("input") from None
            digest = hashlib.sha256(body).hexdigest()
            store = child_directory(root, "objects")
            try:
                publish(store, f"{digest}.body", body)
            finally:
                os.close(store)
            objects.append(
                {
                    "sha256": digest,
                    "bytes": len(body),
                    "input_pointer": f"/records/{index}",
                    "canonical_gemi_number": record.canonical_gemi_number,
                    "claimed_capture_utc": record.captured_at_utc,
                }
            )
        completed: dict[str, object] = {
            "version": VERSION,
            "request_id": request_id.hex,
            "source_family": "gemi",
            "acquisition_channel": "publicity-manual",
            "input": {"version": INPUT_VERSION, "records": [r.payload() for r in records]},
            "objects": objects,
            "imported_at": datetime.now(UTC).isoformat(),
        }
        bundles = child_directory(root, "bundles")
        try:
            name = f"{request_id.hex}.json"
            try:
                previous = decode(
                    read(bundles, name, limit=MAX_COMPLETION, private=True), limit=MAX_COMPLETION
                )
            except FileNotFoundError:
                previous = None
            if previous is not None:
                if not isinstance(previous, dict) or "imported_at" not in previous:
                    raise EvidenceError("integrity")
                if utc_timestamp(previous["imported_at"]) != previous["imported_at"]:
                    raise EvidenceError("integrity")
                comparable = {**previous, "imported_at": completed["imported_at"]}
                if comparable != completed:
                    raise EvidenceError("conflict")
            else:
                publish(bundles, name, encode(completed))
        finally:
            os.close(bundles)
        return summary(request_id, len(records), reused=previous is not None)
    except OSError:
        raise EvidenceError("archive_io") from None
    finally:
        if root >= 0:
            os.close(root)
