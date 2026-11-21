"""Private offline CPV publication and read-only selected-snapshot annotations."""

import argparse
import json
import os
from pathlib import Path
from typing import NoReturn

from nima.evidence import EvidenceError
from nima.evidence.artifacts import directory, read
from nima.identity import AssessmentError
from nima.identity.artifacts import publish
from nima.metadata.cpv import MAX_BYTES, CpvReference, prepare_reference
from nima.metadata.cpv_match import match_metadata
from nima.metadata.store import query_metadata
from nima.sources.metadata_extract import MetadataError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise MetadataError("reference_input")


def _path(path: Path) -> None:
    if (
        not path.is_absolute()
        or any(p in {"..", ".git"} for p in path.parts)
        or "\x00" in str(path)
    ):
        raise MetadataError("reference_input")


def load_reference(
    path: Path,
    *,
    raw_sha256: str,
    language: str,
    retrieved_at: str,
) -> CpvReference:
    """Reuse no-follow, bounded regular-file reads with private ownership/modes."""
    _path(path)
    try:
        parent = directory(path.parent, private=True)
        try:
            raw = read(parent, path.name, limit=MAX_BYTES, private=True)
        finally:
            os.close(parent)
    except (EvidenceError, OSError):
        raise MetadataError("reference_evidence") from None
    return prepare_reference(
        raw, raw_sha256=raw_sha256, language=language, retrieved_at=retrieved_at
    )


def run(argv: list[str]) -> int:
    try:
        parser = _Parser(prog="python -m nima metadata", allow_abbrev=False)
        parser.add_argument("operation", choices=("cpv-reference", "cpv-match"))
        parser.add_argument("--reference-file", type=Path, required=True)
        parser.add_argument("--reference-raw-sha256", required=True)
        parser.add_argument("--language", choices=("ell", "eng"), required=True)
        parser.add_argument("--retrieved-at", required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--snapshot-sha256")
        args = parser.parse_args(argv)
        _path(args.output_dir)
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if (
            args.operation == "cpv-match"
            and (not dsn.strip() or not args.snapshot_sha256)
            or args.operation == "cpv-reference"
            and args.snapshot_sha256 is not None
        ):
            raise MetadataError("reference_input")
        reference = load_reference(
            args.reference_file,
            raw_sha256=args.reference_raw_sha256,
            language=args.language,
            retrieved_at=args.retrieved_at,
        )
        body = reference.body()
        summary = {"entry_count": len(reference.entries)}
        if args.operation == "cpv-match":
            metadata = query_metadata(dsn, args.snapshot_sha256)
            body = match_metadata(metadata, args.snapshot_sha256, reference)
            summary["cpv_assertion_count"] = json.loads(body)["coverage"]["cpv_assertion_count"]
        publish(args.output_dir, body)
    except MetadataError as error:
        reason = error.reason
    except (AssessmentError, OSError):
        reason = "reference_output"
    except KeyboardInterrupt:
        reason = "reference_interrupted"
    else:
        print(json.dumps({"status": "complete", **summary}, allow_nan=False))
        return 0
    print(json.dumps({"status": "failed", "failure": reason}, allow_nan=False))
    return (
        130
        if reason == "reference_interrupted"
        else 2
        if reason in {"reference_input", "metadata_input"}
        else 1
    )
