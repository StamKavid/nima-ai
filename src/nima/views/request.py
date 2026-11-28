"""Closed private configuration for the offline buyer evidence view."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from nima.analytics.request import (
    MAX_REQUEST_BYTES,
    RequestError,
    constant_hook,
    pairs_hook,
    path_value,
    read_private_request,
)

FORMAT = "nima-buyer-evidence-view-request-v1"


class ViewError(ValueError):
    """Fixed operation reasons only; no paths or source values."""

    def __init__(self, reason: str) -> None:
        codes = {
            f"view_{kind}"
            for kind in (
                "input",
                "limit",
                "evidence",
                "database",
                "contract",
                "output",
                "interrupted",
            )
        }
        super().__init__(reason if reason in codes else "view_contract")


@dataclass(frozen=True)
class BuyerViewEntry:
    label: str
    request_path: Path
    report_path: Path


def decode_config(body: bytes) -> tuple[BuyerViewEntry, ...]:
    if not isinstance(body, bytes) or len(body) > MAX_REQUEST_BYTES:
        raise ViewError("view_input")
    try:
        config = json.loads(
            body.decode("utf-8"), object_pairs_hook=pairs_hook, parse_constant=constant_hook
        )
        if not isinstance(config, dict) or set(config) != {"version", "entries"}:
            raise ViewError("view_input")
        rows = config["entries"]
        if config["version"] != FORMAT or not isinstance(rows, list) or not 1 <= len(rows) <= 2:
            raise ViewError("view_input")
        entries = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"label", "request_path", "report_path"}:
                raise ViewError("view_input")
            label = row["label"]
            if not isinstance(label, str) or not 1 <= len(label) <= 80 or not label.strip():
                raise ViewError("view_input")
            label.encode("utf-8")
            if any(ord(c) < 32 or ord(c) == 127 for c in label):
                raise ViewError("view_input")
            request, report = path_value(row["request_path"]), path_value(row["report_path"])
            if re.fullmatch(r"[0-9a-f]{64}\.json", report.name) is None:
                raise ViewError("view_input")
            entries.append(BuyerViewEntry(label, request, report))
        if len({entry.label for entry in entries}) != len(entries) or len(
            {(entry.request_path, entry.report_path) for entry in entries}
        ) != len(entries):
            raise ViewError("view_input")
        return tuple(entries)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ViewError("view_input") from None


def read_config(path: Path) -> tuple[BuyerViewEntry, ...]:
    try:
        return read_private_request(path, decode_config)
    except RequestError:
        raise ViewError("view_input") from None
