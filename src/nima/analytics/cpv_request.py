"""Closed private selection for the CPV-by-period readout; decoding touches no archive or SQL."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from nima.analytics.cohort_request import cohort_fields
from nima.analytics.request import (
    MAX_REQUEST_BYTES,
    RequestError,
    constant_hook,
    pairs_hook,
    read_private_request,
)
from nima.graph.pilot_archive import ArchiveBinding

FORMAT = "nima-cpv-period-request-v1"
_FIELDS = {
    "version",
    "source",
    "run_ids",
    "observation_cutoff",
    "cpv_base_code",
    "period_from",
    "period_to",
    "archive_bindings",
}
_BASE = re.compile(r"[0-9]{8}")
_PERIOD = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")


@dataclass(frozen=True)
class CpvRequest:
    run_ids: tuple[UUID, ...]
    observation_cutoff: datetime
    archive_bindings: tuple[ArchiveBinding, ...]
    cpv_base_code: str | None = None
    period_from: str | None = None
    period_to: str | None = None

    def semantic_payload(self) -> dict[str, object]:
        return {
            "version": FORMAT,
            "source": "kimdis.contract",
            "run_ids": [str(run) for run in self.run_ids],
            "observation_cutoff": self.observation_cutoff.isoformat(),
            "cpv_base_code": self.cpv_base_code,
            "period_from": self.period_from,
            "period_to": self.period_to,
        }

    @property
    def request_sha256(self) -> str:
        body = json.dumps(self.semantic_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(body).hexdigest()


def _optional(value: object, pattern: re.Pattern[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RequestError("analytics_input")
    return value


def decode_cpv_request(body: bytes) -> CpvRequest:
    if not isinstance(body, bytes):
        raise RequestError("analytics_input")
    if len(body) > MAX_REQUEST_BYTES:
        raise RequestError("analytics_limit")
    try:
        value: object = json.loads(
            body.decode("utf-8"), object_pairs_hook=pairs_hook, parse_constant=constant_hook
        )
        if not isinstance(value, dict) or set(value) != _FIELDS:
            raise RequestError("analytics_input")
        data = cast(dict[str, object], value)
        if data["version"] != FORMAT or data["source"] != "kimdis.contract":
            raise RequestError("analytics_input")
        base = _optional(data["cpv_base_code"], _BASE)
        first = _optional(data["period_from"], _PERIOD)
        last = _optional(data["period_to"], _PERIOD)
        if first is not None and last is not None and first > last:
            raise RequestError("analytics_input")
        runs, cutoff, bindings = cohort_fields(data)
        return CpvRequest(runs, cutoff, bindings, base, first, last)
    except (ValueError, TypeError, RecursionError) as error:
        if isinstance(error, RequestError):
            raise
        raise RequestError("analytics_input") from None


def read_cpv_request(path: Path) -> CpvRequest:
    return read_private_request(path, decode_cpv_request)
