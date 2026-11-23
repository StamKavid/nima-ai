"""Bounded, read-only validation of completed GEMI collector archives.

Descriptor-relative no-follow reads: https://docs.python.org/3.12/library/os.html#os.open
"""

import hashlib
import json
import os
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast
from uuid import UUID

from nima.ingestion.archive import MARKER
from nima.ingestion.gemi import GemiLimits, SearchRules
from nima.sources.gemi import (
    ENDPOINT,
    MAX_BODY,
    NORMALIZER_VERSION,
    InvalidProfile,
    normalize_profile,
    registry_number,
)

MAX_MANIFEST = 1024 * 1024
MAX_TOTAL_BODY = 30 * MAX_BODY
MAX_PROFILES = 16 * 1024 * 1024
CONTRACT = {
    "connector_version": "gemi-profile-v1",
    "normalizer_version": NORMALIZER_VERSION,
    "endpoint": ENDPOINT,
    "source": "https://opendata.businessportal.gr/techdocs/",
    "schema_sha256": "c91a65517b89f3a8ac1555f49b4f3178cc185c96addcc08dd2f772c353055e54",
    "license": "ODC-BY-1.0",
    "publisher": "Central GEMI Service / Central Union of Chambers",
}
SEARCH_CONTRACT = {**CONTRACT, "connector_version": "gemi-afm-search-v1"}
SEARCH_STATUSES = {"complete", "quarantined"}
NOT_FOUND = "not_found_at_observation"


class ImportFailure(Exception):
    """Public reason codes never include source assertions or driver messages."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ResponseEvidence:
    number: str
    attempt: int
    started_at: datetime
    finished_at: datetime
    status: int | None
    failure: str | None
    sha256: str | None
    byte_length: int | None
    observed_at: datetime | None


@dataclass(frozen=True)
class Observation:
    number: str
    attempt: int
    outcome: str
    observed_at: datetime
    sha256: str
    profile: str | None


@dataclass(frozen=True)
class VerifiedRun:
    run_id: UUID
    archive_root: str
    manifest: bytes
    manifest_sha256: str
    responses: tuple[ResponseEvidence, ...]
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class VerifiedSearch:
    """Recomputed from the original response bodies; counts and outcomes, no company data."""

    run_id: UUID
    manifest_sha256: str
    requested: int
    attempts: int
    outcomes: Mapping[str, str]
    outcome_counts: Mapping[str, int]
    companies: int
    eligible_hits: int
    unconfirmed_quarantines: int


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part == "..":
                raise ImportFailure("archive_invalid")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _read(directory: int, name: str, limit: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ImportFailure("archive_invalid")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ImportFailure("archive_budget")
    return raw


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ImportFailure("manifest_invalid")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ImportFailure("manifest_invalid")


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ImportFailure("manifest_invalid")
    return cast(dict[str, object], value)


def _time(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ImportFailure("manifest_invalid")
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ImportFailure("manifest_invalid")
    return result


def _integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ImportFailure("manifest_invalid")
    return value


def _list(value: object, maximum: int) -> list[object]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ImportFailure("manifest_invalid")
    return cast(list[object], value)


def _duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ImportFailure("manifest_invalid")
    return float(value)


def _limits(data: dict[str, object]) -> GemiLimits:
    raw_limits = _object(data["limits"])
    defaults = GemiLimits()
    if raw_limits.keys() != asdict(defaults).keys():
        raise ImportFailure("manifest_invalid")
    # Constructor enforces the collector's finite ceilings and exact integer counts.
    return GemiLimits(
        max_attempts=_integer(raw_limits["max_attempts"], 1, 3),
        max_bytes=_integer(raw_limits["max_bytes"], 1, defaults.max_bytes),
        requests_per_minute=_duration(raw_limits["requests_per_minute"]),
        request_timeout=_duration(raw_limits["request_timeout"]),
        run_timeout=_duration(raw_limits["run_timeout"]),
        max_retry_delay=_duration(raw_limits["max_retry_delay"]),
    )


def _header(data: dict[str, object], run_id: UUID) -> tuple[list[str], GemiLimits]:
    if type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ImportFailure("manifest_version")
    if any(data.get(key) != value for key, value in CONTRACT.items()):
        raise ImportFailure("manifest_version")
    summary = _object(data["summary"])
    if (
        summary["run_id"] != run_id.hex
        or summary["status"] != "complete"
        or summary["collection_complete"] is not True
        or summary["normalization_complete"] is not True
        or summary["failure"] is not None
    ):
        raise ImportFailure("run_incomplete")
    inputs = _list(data["inputs"], 10)
    numbers = [registry_number(cast(str, n)) for n in _list(data["registry_numbers"], 10)]
    if (
        numbers != data["registry_numbers"]
        or list(dict.fromkeys(registry_number(cast(str, n)) for n in inputs)) != numbers
    ):
        raise ImportFailure("manifest_invalid")
    return numbers, _limits(data)


def _receipt(
    value: object,
    number: str,
    attempt: int,
    previous: datetime,
    end: datetime,
    limits: GemiLimits,
    key: str = "registry_number",
) -> tuple[dict[str, object], ResponseEvidence]:
    row = _object(value)
    started, finished = _time(row["started_at"]), _time(row["finished_at"])
    if (
        row[key] != number
        or row["state"] != "finished"
        or _integer(row["attempt"], 1, limits.max_attempts) != attempt
        or not previous <= started <= finished <= end
        or type(row["body_complete"]) is not bool
    ):
        raise ImportFailure("manifest_invalid")
    status = None if "status" not in row else _integer(row["status"], 100, 599)
    failure = row.get("failure")
    if row["body_complete"]:
        observed = _time(row["observed_at"])
        length = _integer(row["bytes"], 0, limits.max_bytes)
        if not started <= observed <= finished or status is None or failure is not None:
            raise ImportFailure("manifest_invalid")
    else:
        observed, length = None, None
        if failure != "transport" or any(k in row for k in ("sha256", "bytes", "observed_at")):
            raise ImportFailure("manifest_invalid")
    return row, ResponseEvidence(
        number,
        attempt,
        started,
        finished,
        status,
        failure,
        cast(str | None, row.get("sha256")),
        length,
        observed,
    )


def _body(root: Path, receipt: dict[str, object], remaining: int) -> bytes:
    digest = receipt["sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ImportFailure("manifest_invalid")
    limit = min(MAX_BODY, remaining)
    if cast(int, receipt["bytes"]) > limit:
        raise ImportFailure("archive_budget")
    with _directory(root / "objects" / digest[:2]) as directory:
        raw = _read(directory, f"{digest}.body", limit)
    if hashlib.sha256(raw).hexdigest() != digest or len(raw) != receipt["bytes"]:
        raise ImportFailure("archive_integrity")
    return raw


def verify_run(archive_root: Path, run_id: UUID) -> VerifiedRun:
    """No archive initialization, HTTP, key lookup, SQL or derived-artifact trust."""
    root = archive_root.absolute()
    try:
        with _directory(root) as directory:
            if _read(directory, ".nima-archive", len(MARKER)) != MARKER.encode():
                raise ImportFailure("archive_invalid")
        with _directory(root / "runs" / run_id.hex) as directory:
            manifest = _read(directory, "manifest.json", MAX_MANIFEST)
        data = _object(
            json.loads(manifest.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        )
        numbers, limits = _header(data, run_id)
        attempts = _list(data["attempts"], 30)
        previous, end = _time(data["started_at"]), _time(data["finished_at"])
        responses: list[ResponseEvidence] = []
        observations: list[Observation] = []
        total_body = total_profiles = cursor = 0
        for number in numbers:
            for attempt in range(1, limits.max_attempts + 1):
                row, response = _receipt(attempts[cursor], number, attempt, previous, end, limits)
                cursor += 1
                previous = response.finished_at
                raw = (
                    _body(root, row, MAX_TOTAL_BODY - total_body) if row["body_complete"] else None
                )
                total_body += 0 if raw is None else len(raw)
                responses.append(response)
                if raw is None:
                    continue  # A transport failure may follow an HTTP status line.
                if response.status not in {200, 404}:
                    if response.status not in {429, 500, 502, 503, 504}:
                        raise ImportFailure("manifest_invalid")
                    continue
                payload = (
                    None
                    if response.status == 404
                    else json.dumps(
                        normalize_profile(raw, number).payload(),
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                )
                total_profiles += 0 if payload is None else len(payload.encode())
                if total_profiles > MAX_PROFILES:
                    raise ImportFailure("archive_budget")
                observations.append(
                    Observation(
                        number,
                        attempt,
                        "found" if response.status == 200 else "not_found_at_observation",
                        cast(datetime, response.observed_at),
                        cast(str, response.sha256),
                        payload,
                    )
                )
                break
            else:
                raise ImportFailure("run_incomplete")
        outcomes = {o.number: o.outcome for o in observations}
        summary = _object(data["summary"])
        expected = {
            "requested": len(numbers),
            "found": sum(o.profile is not None for o in observations),
            "not_found": sum(o.profile is None for o in observations),
            "quarantined": 0,
            "attempts": cursor,
        }
        if (
            cursor != len(attempts)
            or data["outcomes"] != outcomes
            or any(_integer(summary[k], 0, 30) != v for k, v in expected.items())
        ):
            raise ImportFailure("manifest_invalid")
        return VerifiedRun(
            run_id,
            str(root),
            manifest,
            hashlib.sha256(manifest).hexdigest(),
            tuple(responses),
            tuple(observations),
        )
    except OSError:
        raise ImportFailure("archive_invalid") from None
    except InvalidProfile:
        raise ImportFailure("profile_invalid") from None
    except (KeyError, IndexError, TypeError, ValueError, RecursionError, OverflowError):
        raise ImportFailure("manifest_invalid") from None


def _search_header(
    data: dict[str, object], run_id: UUID, rules: SearchRules
) -> tuple[list[str], GemiLimits]:
    if type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ImportFailure("manifest_version")
    if any(data.get(key) != value for key, value in SEARCH_CONTRACT.items()):
        raise ImportFailure("manifest_version")
    summary = _object(data["summary"])
    if (
        summary["run_id"] != run_id.hex
        or summary["status"] not in SEARCH_STATUSES
        or summary["collection_complete"] is not True
        or summary["normalization_complete"] is not (summary["status"] == "complete")
        or summary["failure"] is not None
    ):
        raise ImportFailure("run_incomplete")
    inputs = _list(data["inputs"], 25)
    afms = [rules.queryable(value) for value in _list(data["afms"], 25)]
    if afms != data["afms"] or list(dict.fromkeys(rules.queryable(v) for v in inputs)) != afms:
        raise ImportFailure("manifest_invalid")
    return afms, _limits(data)


def verify_search_run(archive_root: Path, run_id: UUID, rules: SearchRules) -> VerifiedSearch:
    """Recompute every AFM's outcome from the archived bodies; no HTTP, key, SQL or derived file.

    A quarantine caused only by the response's media type cannot be recomputed, because headers
    are not archived. It is accepted for a 200 answer and counted as unconfirmed, never trusted.
    """
    root = archive_root.absolute()
    try:
        with _directory(root) as directory:
            if _read(directory, ".nima-archive", len(MARKER)) != MARKER.encode():
                raise ImportFailure("archive_invalid")
        with _directory(root / "runs" / run_id.hex) as directory:
            manifest = _read(directory, "manifest.json", MAX_MANIFEST)
        data = _object(
            json.loads(manifest.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        )
        afms, limits = _search_header(data, run_id, rules)
        attempts = _list(data["attempts"], 75)
        previous, end = _time(data["started_at"]), _time(data["finished_at"])
        claimed = _object(data["outcomes"])
        outcomes: dict[str, str] = {}
        total_body = companies = eligible = unconfirmed = cursor = 0
        for afm in afms:
            for attempt in range(1, limits.max_attempts + 1):
                row, response = _receipt(
                    attempts[cursor], afm, attempt, previous, end, limits, "afm"
                )
                cursor += 1
                previous = response.finished_at
                raw = (
                    _body(root, row, MAX_TOTAL_BODY - total_body) if row["body_complete"] else None
                )
                total_body += 0 if raw is None else len(raw)
                if raw is None:
                    continue  # A transport failure may follow an HTTP status line.
                if response.status not in {200, 404}:
                    if response.status not in {429, 500, 502, 503, 504}:
                        raise ImportFailure("manifest_invalid")
                    continue
                answer = rules.parse(raw, afm, response.status)
                outcome = answer.outcome
                if outcome != "quarantined" and claimed.get(afm) == "quarantined":
                    if response.status != 200:
                        raise ImportFailure("manifest_invalid")
                    outcome, unconfirmed = "quarantined", unconfirmed + 1
                elif outcome != "quarantined":
                    companies += len(answer.hits)
                    eligible += sum(hit.afm_matches for hit in answer.hits)
                outcomes[afm] = outcome
                break
            else:
                raise ImportFailure("run_incomplete")
        counts: dict[str, int] = {}
        for outcome in outcomes.values():
            counts[outcome] = counts.get(outcome, 0) + 1
        summary = _object(data["summary"])
        expected = {
            "requested": len(afms),
            "found": sum(1 for o in outcomes.values() if o not in {"quarantined", NOT_FOUND}),
            "not_found": counts.get(NOT_FOUND, 0),
            "quarantined": counts.get("quarantined", 0),
            "attempts": cursor,
            "companies": companies,
        }
        if (
            cursor != len(attempts)
            or claimed != outcomes
            or summary["outcome_counts"] != counts
            or any(_integer(summary[k], 0, 1000) != v for k, v in expected.items())
        ):
            raise ImportFailure("manifest_invalid")
        return VerifiedSearch(
            run_id,
            hashlib.sha256(manifest).hexdigest(),
            len(afms),
            cursor,
            MappingProxyType(outcomes),
            MappingProxyType(counts),
            companies,
            eligible,
            unconfirmed,
        )
    except OSError:
        raise ImportFailure("archive_invalid") from None
    except (KeyError, IndexError, TypeError, ValueError, RecursionError, OverflowError):
        raise ImportFailure("manifest_invalid") from None
