"""Redacted, offline manual-evidence commands."""

import argparse
import json
from pathlib import Path
from typing import Never
from uuid import UUID

from nima.evidence import EvidenceError
from nima.evidence.intake import intake
from nima.evidence.publicity import VERSION
from nima.evidence.verify import verify


def _failure(reason: str) -> None:
    print(
        json.dumps(
            {"version": VERSION, "status": "failed", "failure": reason, "evidence_complete": False}
        )
    )


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse otherwise echoes invalid values, paths and unrecognised options.
        _failure("input")
        self.exit(2)


def run(argv: list[str]) -> int:
    parser = _Parser(prog="python -m nima evidence", description="Offline manual evidence only")
    operations = parser.add_subparsers(dest="operation", required=True)
    intake_sources = operations.add_parser("intake").add_subparsers(dest="source", required=True)
    capture = intake_sources.add_parser("publicity")
    capture.add_argument("--request-id", type=UUID, required=True)
    capture.add_argument("--manifest", type=Path, required=True)
    capture.add_argument("--input-dir", type=Path, required=True)
    capture.add_argument("--archive-dir", type=Path, required=True)
    check = operations.add_parser("verify")
    check.add_argument("request_id", type=UUID)
    check.add_argument("--archive-dir", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        if args.operation == "intake":
            result = intake(args.request_id, args.manifest, args.input_dir, args.archive_dir)
        else:
            result = verify(args.request_id, args.archive_dir)
    except EvidenceError as exc:
        _failure(exc.reason)
        return 2 if exc.reason == "input" else 1
    except KeyboardInterrupt:
        _failure("interrupted")
        return 130
    print(json.dumps(result, allow_nan=False))
    return 0
