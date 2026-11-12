"""Strict operator claims, not source authentication.

JSON duplicate handling: https://docs.python.org/3.12/library/json.html#json.loads
"""

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Never, cast
from urllib.parse import urlsplit

from nima.evidence import EvidenceError
from nima.sources.gemi import registry_number

INPUT_VERSION = "publicity-manual-input-v1"
VERSION = "publicity-manual-evidence-v1"
MAX_MANIFEST = 64 * 1024
MAX_COMPLETION = 128 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
SIGNATURES = {
    "application/pdf": b"%PDF-",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}


def _invalid(_: str) -> Never:
    raise EvidenceError("input")


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise EvidenceError("input")
        result[key] = value
    return result


def decode(body: bytes, *, limit: int = MAX_MANIFEST) -> object:
    if not 0 < len(body) <= limit:
        raise EvidenceError("input")
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise EvidenceError("input") from None


def encode(value: object) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        + b"\n"
    )


def text(value: object, *, limit: int = 512) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= limit:
        raise EvidenceError("input")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise EvidenceError("input") from None
    if any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value):
        raise EvidenceError("input")
    return value


def relative(value: object) -> str:
    path = text(value)
    parts = path.split("/")
    if len(parts) > 32 or "\\" in path or any(p in {"", ".", "..", ".git"} for p in parts):
        raise EvidenceError("input")
    return path


def utc_timestamp(value: object) -> str:
    original = text(value, limit=40)
    if (
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", original
        )
        is None
    ):
        raise EvidenceError("input")
    try:
        return datetime.fromisoformat(original).astimezone(UTC).isoformat()
    except ValueError:
        raise EvidenceError("input") from None


@dataclass(frozen=True)
class Capture:
    gemi_number: str
    file: str
    media_type: str
    source_url: str
    claimed_captured_at: str
    capture_method: str
    capture_context: str

    @property
    def canonical_gemi_number(self) -> str:
        return registry_number(self.gemi_number)

    @property
    def captured_at_utc(self) -> str:
        return utc_timestamp(self.claimed_captured_at)

    def payload(self) -> dict[str, str]:
        return asdict(self)


def parse_manifest(body: bytes) -> tuple[Capture, ...]:
    document = decode(body)
    if (
        not isinstance(document, dict)
        or set(document) != {"version", "records"}
        or document["version"] != INPUT_VERSION
    ):
        raise EvidenceError("input")
    rows = document["records"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10:
        raise EvidenceError("input")
    records: list[Capture] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(Capture.__dataclass_fields__):
            raise EvidenceError("input")
        fields = {k: text(v, limit=2048 if k == "source_url" else 512) for k, v in row.items()}
        capture = Capture(**cast(dict[str, str], fields))
        try:
            _ = capture.canonical_gemi_number
            _ = capture.captured_at_utc
            url = urlsplit(capture.source_url)
            if (
                url.scheme != "https"
                or url.netloc
                not in {"publicity.businessportal.gr", "publicity.businessportal.gr:443"}
                or "?" in capture.source_url
                or "#" in capture.source_url
            ):
                raise ValueError
        except ValueError:
            raise EvidenceError("input") from None
        relative(capture.file)
        if (
            capture.media_type not in SIGNATURES
            or capture.capture_context not in {"remote-browser", "vpn-protected"}
            or capture.capture_method not in {"download", "print-to-pdf", "screenshot"}
            or (
                capture.capture_method == "print-to-pdf" and capture.media_type != "application/pdf"
            )
            or (
                capture.capture_method == "screenshot"
                and not capture.media_type.startswith("image/")
            )
        ):
            raise EvidenceError("input")
        if any(
            r.canonical_gemi_number == capture.canonical_gemi_number or r.file == capture.file
            for r in records
        ):
            raise EvidenceError("input")
        records.append(capture)
    return tuple(records)
