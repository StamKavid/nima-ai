"""Validate a fresh, bounded full-receipt publication before CI artifact upload.

Only the canonical fixture receipt is eligible. Private configuration, partial
HTTP reports, traces and extra files cannot share the upload directory.
"""

import json
import os
import stat
import sys
from pathlib import Path

from nima.egress.policy import FixturePolicy
from nima.egress.receipt import Receipt, ReceiptError, read_receipt
from nima.evidence import EvidenceError, artifacts

MARKER = b"source-worker-egress-v1\n"


def prepare(root: Path) -> None:
    descriptor = None
    try:
        descriptor = artifacts.directory(root, create=True, private=True)
        with os.scandir(descriptor) as entries:
            if next(entries, None) is not None:
                raise ReceiptError("artifact_directory")
    except (OSError, EvidenceError):
        raise ReceiptError("artifact_directory") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read(descriptor: int, name: str, limit: int) -> bytes:
    before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ReceiptError("artifact_file")
    raw = artifacts.read(descriptor, name, limit=limit, private=True)
    after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    if (before.st_dev, before.st_ino, before.st_ctime_ns, before.st_nlink) != (
        after.st_dev,
        after.st_ino,
        after.st_ctime_ns,
        after.st_nlink,
    ):
        raise ReceiptError("artifact_file")
    return raw


def verify(root: Path) -> Receipt:
    descriptor = None
    try:
        descriptor = artifacts.directory(root, private=True)
        names: set[str] = set()
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.add(entry.name)
                if len(names) > 3:
                    raise ReceiptError("artifact_directory")
        reports = [name for name in names if name.endswith(".json")]
        if len(reports) != 1 or names != {".nima-source-worker", ".gitignore", *reports}:
            raise ReceiptError("artifact_directory")
        if _read(descriptor, ".nima-source-worker", len(MARKER)) != MARKER:
            raise ReceiptError("artifact_marker")
        if _read(descriptor, ".gitignore", 2) != b"*\n":
            raise ReceiptError("artifact_marker")
        receipt = read_receipt(_read(descriptor, reports[0], FixturePolicy().max_receipt_bytes))
        if reports[0] != str(receipt.run_id) + ".json":
            raise ReceiptError("artifact_identity")
        return receipt
    except (OSError, EvidenceError, ReceiptError):
        raise ReceiptError("artifact_publication") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] not in {"prepare", "verify"}:
        print(json.dumps({"status": "failed", "failure": "configuration"}))
        return 2
    try:
        if args[0] == "prepare":
            prepare(Path(args[1]))
            count = cases = 0
        else:
            receipt = verify(Path(args[1]))
            count, cases = 1, len(receipt.cases)
    except Exception:
        print(json.dumps({"status": "failed", "failure": "artifact_publication"}))
        return 1
    print(
        json.dumps(
            {
                "version": "source-worker-receipt-check-v1",
                "scope": "controlled-fixtures",
                "operation": args[0],
                "status": "passed",
                "receipts": count,
                "cases": cases,
                "isolation_checks_passed": count == 1,
                "internet_egress_verified": False,
                "investigator_ip_protection_verified": False,
                "production_ready": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
