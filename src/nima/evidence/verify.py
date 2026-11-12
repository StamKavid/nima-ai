"""Read-only verification of manual evidence, without authentication claims."""

import fcntl
import hashlib
import os
import re
from pathlib import Path
from typing import cast
from uuid import UUID

from nima.evidence import EvidenceError
from nima.evidence.artifacts import child_directory, directory, read, validate_root
from nima.evidence.publicity import (
    MAX_COMPLETION,
    MAX_FILE,
    MAX_TOTAL,
    SIGNATURES,
    VERSION,
    decode,
    encode,
    parse_manifest,
    summary,
    utc_timestamp,
)


def load_bundle(root: int, request_id: UUID) -> dict[str, object]:
    """Caller holds the archive lock; never initializes or repairs evidence."""
    try:
        validate_root(root)
        bundles = child_directory(root, "bundles")
        try:
            body = read(bundles, f"{request_id.hex}.json", limit=MAX_COMPLETION, private=True)
        finally:
            os.close(bundles)
        decoded = decode(body, limit=MAX_COMPLETION)
        if not isinstance(decoded, dict) or set(decoded) != {
            "version",
            "request_id",
            "source_family",
            "acquisition_channel",
            "input",
            "objects",
            "imported_at",
        }:
            raise EvidenceError("integrity")
        bundle = cast(dict[str, object], decoded)
        if (
            body != encode(bundle)
            or bundle["version"] != VERSION
            or bundle["request_id"] != request_id.hex
            or bundle["source_family"] != "gemi"
            or bundle["acquisition_channel"] != "publicity-manual"
            or utc_timestamp(bundle["imported_at"]) != bundle["imported_at"]
        ):
            raise EvidenceError("integrity")
        records = parse_manifest(encode(bundle["input"]))
        objects = bundle["objects"]
        if not isinstance(objects, list) or len(objects) != len(records):
            raise EvidenceError("integrity")
        store = child_directory(root, "objects")
        total = 0
        try:
            for index, (record, row) in enumerate(zip(records, objects, strict=True)):
                if not isinstance(row, dict):
                    raise EvidenceError("integrity")
                digest, size = row.get("sha256"), row.get("bytes")
                if (
                    not isinstance(digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    or type(size) is not int
                    or not 0 < size <= MAX_FILE
                ):
                    raise EvidenceError("integrity")
                total += size
                if total > MAX_TOTAL:
                    raise EvidenceError("integrity")
                raw = read(store, f"{digest}.body", limit=size, private=True)
                expected = {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                    "input_pointer": f"/records/{index}",
                    "canonical_gemi_number": record.canonical_gemi_number,
                    "claimed_capture_utc": record.captured_at_utc,
                }
                if row != expected or not raw.startswith(SIGNATURES[record.media_type]):
                    raise EvidenceError("integrity")
        finally:
            os.close(store)
        return bundle
    except (EvidenceError, OSError):
        raise EvidenceError("integrity") from None


def verify(request_id: UUID, archive_dir: Path) -> dict[str, object]:
    root = -1
    try:
        root = directory(archive_dir, private=True)
        fcntl.flock(root, fcntl.LOCK_SH)
        bundle = load_bundle(root, request_id)
        records = cast(list[object], bundle["objects"])
        return summary(request_id.hex, len(records), status="verified")
    except OSError:
        raise EvidenceError("archive_io") from None
    finally:
        if root >= 0:
            os.close(root)
