"""Explicit promotion and cached read-only queries; terminal output has no source values."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn
from uuid import UUID

from nima.identity import AssessmentError
from nima.identity.artifacts import publish
from nima.sources.metadata_extract import DIMENSIONS, MetadataError
from nima.metadata.store import promote_metadata, query_metadata


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise MetadataError("metadata_input")


def run(argv: list[str]) -> int:
    try:
        parser = _Parser(prog="python -m nima metadata", allow_abbrev=False)
        commands = parser.add_subparsers(dest="operation", required=True)
        promote = commands.add_parser(
            "promote", allow_abbrev=False, help="Store an explicitly selected verified snapshot"
        )
        promote.add_argument("source", choices=("kimdis", "gemi"))
        promote.add_argument("--run-id", type=UUID, required=True)
        promote.add_argument("--archive-dir", type=Path, required=True)
        promote.add_argument("--snapshot-sha256", required=True)
        query = commands.add_parser(
            "query",
            allow_abbrev=False,
            help="Query a selected stored snapshot without reading archives",
        )
        query.add_argument("--snapshot-sha256", required=True)
        query.add_argument("--output-dir", type=Path, required=True)
        query.add_argument("--dimension", choices=DIMENSIONS)
        query.add_argument("--code")
        args = parser.parse_args(argv)
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if not dsn.strip():
            raise MetadataError("metadata_input")
        if args.operation == "promote":
            summary = asdict(
                promote_metadata(
                    dsn, args.source, args.run_id, args.archive_dir, args.snapshot_sha256
                )
            )
        else:
            output = args.output_dir
            if (
                not output.is_absolute()
                or any(p in {"..", ".git"} for p in output.parts)
                or "\x00" in str(output)
            ):
                raise MetadataError("metadata_input")
            body = query_metadata(
                dsn, args.snapshot_sha256, dimension=args.dimension, code=args.code
            )
            publish(output, body)
            document = json.loads(body)
            summary = {
                key: document["coverage"][key] for key in ("record_count", "assertion_count")
            }
            summary["matched_assertion_count"] = document["matched_assertion_count"]
    except MetadataError as error:
        reason = error.reason
    except (AssessmentError, OSError):
        reason = "metadata_output"
    except KeyboardInterrupt:
        reason = "metadata_interrupted"
    else:
        print(json.dumps({"status": "complete", **summary}, allow_nan=False))
        return 0
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    if reason == "metadata_empty":
        return 3
    return 130 if reason == "metadata_interrupted" else 2 if reason == "metadata_input" else 1
