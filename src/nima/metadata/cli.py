"""Fixed terminal summaries; reported source values remain in private artifacts."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn
from uuid import UUID

from nima.metadata.export import export_metadata
from nima.metadata.extract import DIMENSIONS, MetadataError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise MetadataError("metadata_input")


def run(argv: list[str]) -> int:
    if argv and argv[0] in {"cpv-reference", "cpv-match"}:
        from nima.metadata.cpv_cli import run as cpv_run

        return cpv_run(argv)
    if argv and argv[0] in {"promote", "query"}:
        from nima.metadata.sql_cli import run as sql_run

        return sql_run(argv)
    try:
        parser = _Parser(
            prog="python -m nima metadata",
            allow_abbrev=False,
            epilog="Operations: promote/query/cpv-reference/cpv-match (use OPERATION --help).",
        )
        parser.add_argument("source", choices=("kimdis", "gemi"))
        parser.add_argument("--run-id", type=UUID, required=True)
        parser.add_argument("--archive-dir", type=Path, required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--dimension", choices=DIMENSIONS)
        parser.add_argument("--code")
        args = parser.parse_args(argv)
        result = export_metadata(
            args.source,
            args.run_id,
            args.archive_dir,
            args.output_dir,
            dsn=os.environ.get("NIMA_DATABASE_URL", ""),
            dimension=args.dimension,
            code=args.code,
        )
    except MetadataError as error:
        reason = error.reason
    except KeyboardInterrupt:
        reason = "metadata_interrupted"
    else:
        summary = asdict(result)
        del summary["artifact_sha256"]
        print(json.dumps({"status": "complete", **summary}, allow_nan=False))
        return 0
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    if reason == "metadata_empty":
        return 3
    return 130 if reason == "metadata_interrupted" else 2 if reason == "metadata_input" else 1
