"""Query hash-verified captured metadata without advancing freshness or writing SQL."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import cast
from uuid import UUID

from nima.dataops.replay import ReplayError, read_capture
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish
from nima.sources import metadata_extract as extract
from nima.sources.metadata_extract import Assertion, MetadataError, gemi_metadata, kimdis_metadata
from nima.sources.kimdis import InvalidRecord, decode_response
from nima.storage.gemi_archive import ImportFailure, verify_run


@dataclass(frozen=True)
class MetadataExport:
    artifact_sha256: str
    record_count: int
    assertion_count: int
    matched_assertion_count: int


def _kimdis(dsn: str, run: UUID, root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    capture = read_capture(dsn, run, root)
    records: list[dict[str, object]] = []
    assertion_count = 0
    for page in capture.pages:
        raw = capture.bodies[page.raw_sha256]
        rows = kimdis_metadata(raw)
        assertion_count += sum(len(row["assertions"]) for row in rows)
        if assertion_count > extract.MAX_ASSERTIONS:
            raise MetadataError("metadata_limit")
        header = decode_response(raw)
        if (
            header["number"],
            len(rows),
            header["totalElements"],
            header["totalPages"],
            header["size"],
        ) != (
            page.number,
            page.record_count,
            capture.run["total_records"],
            capture.run["total_pages"],
            capture.run["page_size"],
        ):
            raise MetadataError("metadata_scope")
        records.extend(
            {
                **row,
                "source_run_id": str(run),
                "page_number": page.number,
                "raw_sha256": page.raw_sha256,
                "observed_at": page.observed_at,
            }
            for row in rows
        )
    return capture.run, records


def _gemi(run: UUID, root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    verified = verify_run(root, run)
    records: list[dict[str, object]] = []
    for observation in verified.observations:
        profile = None if observation.profile is None else json.loads(observation.profile)
        records.append(
            {
                "source_run_id": str(run),
                "source_id": "gemi:" + observation.number,
                "record_pointer": "",
                "content_sha256": None,
                "record_status": observation.outcome,
                "raw_sha256": observation.sha256,
                "observed_at": observation.observed_at.astimezone(UTC).isoformat(),
                "assertions": [] if profile is None else gemi_metadata(profile),
            }
        )
    manifest = json.loads(verified.manifest)
    return {
        "run_id": str(run),
        "status": "complete",
        "scope": "verified_completed_archive",
        "manifest_sha256": verified.manifest_sha256,
        **{
            key: manifest[key]
            for key in ("connector_version", "normalizer_version", "source", "license", "publisher")
        },
    }, records


def _result(
    source: str,
    capture: dict[str, object],
    records: list[dict[str, object]],
    dimension: str | None,
    code: str | None,
) -> tuple[bytes, int, int]:
    counts: Counter[str] = Counter()
    selected = []
    matched = 0
    for record in records:
        rows = cast(list[Assertion], record["assertions"])
        counts.update(row["status"] for row in rows)
        if sum(counts.values()) > extract.MAX_ASSERTIONS:
            raise MetadataError("metadata_limit")
        filtered = extract.select_assertions(rows, dimension, code)
        matched += len(filtered)
        if filtered or (dimension is None and code is None):
            selected.append({**record, "assertions": filtered})
    body = encode(
        {
            "artifact_version": extract.VERSION,
            "source": source,
            "scope": "captured_occurrences_only",
            "capture": capture,
            "query": {"dimension": dimension, "code": code},
            "coverage": {
                "record_count": len(records),
                "assertion_count": sum(counts.values()),
                "quality_counts": dict(sorted(counts.items())),
                "unavailable_record_count": sum(
                    r["record_status"] == "not_found_at_observation" for r in records
                ),
            },
            "matched_assertion_count": matched,
            "meaning": (
                "Reported occurrences; no taxonomy certification, current-state, "
                "identity or market-absence claim"
            ),
            "records": selected,
        }
    )
    return body, sum(counts.values()), matched


def prepare_metadata(
    source: str,
    run_id: UUID,
    archive_root: Path,
    *,
    dsn: str = "",
    dimension: str | None = None,
    code: str | None = None,
) -> tuple[bytes, MetadataExport]:
    """Prepare verified canonical bytes without publication, SQL writes or network."""
    extract.validate_query(source, dimension, code)
    if (
        source not in {"kimdis", "gemi"}
        or not isinstance(run_id, UUID)
        or any(
            not isinstance(path, Path)
            or not path.is_absolute()
            or any(part in {"..", ".git"} for part in path.parts)
            or "\x00" in str(path)
            for path in (archive_root,)
        )
        or (source == "kimdis" and not dsn.strip())
    ):
        raise MetadataError("metadata_input")
    try:
        capture, records = (
            _kimdis(dsn, run_id, archive_root)
            if source == "kimdis"
            else _gemi(run_id, archive_root)
        )
        body, count, matched = _result(source, capture, records, dimension, code)
        digest = hashlib.sha256(body).hexdigest()
        return body, MetadataExport(digest, len(records), count, matched)
    except ReplayError as error:
        suffix = error.reason.removeprefix("replay_")
        raise MetadataError("metadata_" + suffix) from None
    except (ImportFailure, InvalidRecord, UnicodeError):
        raise MetadataError("metadata_evidence") from None
    except AssessmentError as error:
        raise MetadataError(
            "metadata_limit" if error.reason == "assessment_limit" else "metadata_output"
        ) from None
    except OSError:
        raise MetadataError("metadata_output") from None


def export_metadata(
    source: str,
    run_id: UUID,
    archive_root: Path,
    output: Path,
    *,
    dsn: str = "",
    dimension: str | None = None,
    code: str | None = None,
) -> MetadataExport:
    """Fully validate before private publication; paths are not artifact identity."""
    if (
        not isinstance(output, Path)
        or not output.is_absolute()
        or any(part in {"..", ".git"} for part in output.parts)
        or "\x00" in str(output)
        or (isinstance(archive_root, Path) and output.is_relative_to(archive_root))
    ):
        raise MetadataError("metadata_input")
    body, result = prepare_metadata(
        source, run_id, archive_root, dsn=dsn, dimension=dimension, code=code
    )
    try:
        publish(output, body)
    except (AssessmentError, OSError):
        raise MetadataError("metadata_output") from None
    return result
