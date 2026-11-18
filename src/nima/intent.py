"""Pure version-one saved intent decoding, independent of current code defaults."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from nima.ingestion.config import Limits, Query

REQUEST_FORMAT = "nima-kimdis-request-v1"
REFRESH_FORMAT = "kimdis-refresh-v1"
LIMIT_FIELDS = (
    "max_pages",
    "max_attempts",
    "max_bytes",
    "requests_per_minute",
    "request_timeout",
    "run_timeout",
    "max_retry_delay",
)
V1_CEILINGS = Limits(100, 3, 8 * 1024 * 1024, 20.0, 20.0, 300.0, 60.0)


class IntentError(ValueError):
    """Unsupported or invalid serialized intent, without private values."""


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise IntentError("intent_invalid")
    return cast(dict[str, object], value)


def _verified(value: object, digest: object) -> dict[str, object]:
    data = _object(value)
    try:
        body = json.dumps(data, sort_keys=True, allow_nan=False).encode()
    except (ValueError, TypeError):
        raise IntentError("intent_invalid") from None
    if not isinstance(digest, str) or hashlib.sha256(body).hexdigest() != digest:
        raise IntentError("intent_invalid")
    return data


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise IntentError("intent_invalid")
    return value


def _pin(value: object) -> str:
    value = _text(value)
    if re.fullmatch("[A-Za-z0-9_.-]{1,128}", value) is None:
        raise IntentError("intent_invalid")
    return value


def _root(value: object) -> Path:
    text = _text(value)
    root = Path(text)
    if not root.is_absolute() or ".." in root.parts or len(text) > 4096 or str(root) != text:
        raise IntentError("intent_invalid")
    return root


@dataclass(frozen=True)
class RequestIntent:
    format_version: str
    query: Query
    limits: Limits
    root: Path
    connector_version: str
    normalizer_version: str

    def failure(self, connector: str, normalizer: str) -> str | None:
        if (self.connector_version, self.normalizer_version) != (connector, normalizer):
            return "request_processing_version"
        if any(getattr(self.limits, key) > getattr(V1_CEILINGS, key) for key in LIMIT_FIELDS):
            return "request_limits"
        return None


def _integer(value: object) -> int:
    if type(value) is not int:
        raise IntentError("intent_invalid")
    return value


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise IntentError("intent_invalid")
    return float(cast(int | float, value))


def request_intent(value: object, digest: object) -> RequestIntent:
    data = _verified(value, digest)
    if (
        set(data)
        != {
            "format_version",
            "query",
            "limits",
            "archive_root",
            "connector_version",
            "normalizer_version",
        }
        or data["format_version"] != REQUEST_FORMAT
    ):
        raise IntentError("intent_invalid")
    query = _object(data["query"])
    limits = _object(data["limits"])
    if set(limits) != set(LIMIT_FIELDS):
        raise IntentError("intent_invalid")
    buyers = query.get("organizations", [])
    if not isinstance(buyers, list):
        raise IntentError("intent_invalid")
    try:
        parsed = Query(
            date.fromisoformat(_text(query["dateFrom"])),
            date.fromisoformat(_text(query["dateTo"])),
            tuple(_text(b) for b in buyers),
        )
        parsed_limits = Limits(
            _integer(limits["max_pages"]),
            _integer(limits["max_attempts"]),
            _integer(limits["max_bytes"]),
            _number(limits["requests_per_minute"]),
            _number(limits["request_timeout"]),
            _number(limits["run_timeout"]),
            _number(limits["max_retry_delay"]),
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        raise IntentError("intent_invalid") from None
    if query != parsed.payload():
        raise IntentError("intent_invalid")
    return RequestIntent(
        REQUEST_FORMAT,
        parsed,
        parsed_limits,
        _root(data["archive_root"]),
        _pin(data["connector_version"]),
        _pin(data["normalizer_version"]),
    )


@dataclass(frozen=True)
class RefreshIntent:
    format_version: str
    start: date
    buyers: tuple[str, ...]
    root: Path
    connector_version: str
    normalizer_version: str
    cron: str
    timezone: str

    def failure(
        self, connector: str, normalizer: str, version: str, cron: str, timezone: str
    ) -> str | None:
        if (self.connector_version, self.normalizer_version) != (connector, normalizer):
            return "policy_processing_version"
        if (self.format_version, self.cron, self.timezone) != (version, cron, timezone):
            return "policy_profile_version"
        return None


def refresh_intent(value: object, digest: object) -> RefreshIntent:
    data = _verified(value, digest)
    if set(data) != {
        "version",
        "start_date",
        "buyers",
        "archive_root",
        "connector_version",
        "normalizer_version",
        "cron",
        "timezone",
        "overlap",
        "lag",
        "child_cap",
    }:
        raise IntentError("intent_invalid")
    if (
        data["version"] != REFRESH_FORMAT
        or data["cron"] != "0 4 * * *"
        or data["timezone"] != "Europe/Athens"
    ):
        raise IntentError("intent_invalid")
    if any(
        type(data[key]) is not int or data[key] != expected
        for key, expected in [("overlap", 7), ("lag", 1), ("child_cap", 14)]
    ):
        raise IntentError("intent_invalid")
    buyers = data["buyers"]
    if not isinstance(buyers, list) or not 1 <= len(buyers) <= 10:
        raise IntentError("intent_invalid")
    parsed_buyers = tuple(_text(b) for b in buyers)
    if (
        len(set(parsed_buyers)) != len(parsed_buyers)
        or list(sorted(parsed_buyers)) != buyers
        or any(not b.isascii() or not b.isdecimal() or int(b) <= 0 for b in parsed_buyers)
    ):
        raise IntentError("intent_invalid")
    try:
        start = date.fromisoformat(_text(data["start_date"]))
    except ValueError:
        raise IntentError("intent_invalid") from None
    if start.isoformat() != data["start_date"]:
        raise IntentError("intent_invalid")
    return RefreshIntent(
        REFRESH_FORMAT,
        start,
        parsed_buyers,
        _root(data["archive_root"]),
        _pin(data["connector_version"]),
        _pin(data["normalizer_version"]),
        "0 4 * * *",
        "Europe/Athens",
    )
