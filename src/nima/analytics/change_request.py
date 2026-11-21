"""Closed private selection for the observed-change readout: two explicit, disjoint captures."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

from nima.analytics.cohort_request import run_fields
from nima.analytics.request import (
    MAX_REQUEST_BYTES,
    RequestError,
    constant_hook,
    pairs_hook,
    read_private_request,
    uuid_value,
)
from nima.graph.pilot_archive import ArchiveBinding

FORMAT = "nima-observed-change-request-v1"
_FIELDS = {"version", "source", "earlier_run_ids", "later_run_ids", "archive_bindings"}


@dataclass(frozen=True)
class ChangeRequest:
    earlier_run_ids: tuple[UUID, ...]
    later_run_ids: tuple[UUID, ...]
    archive_bindings: tuple[ArchiveBinding, ...]

    @property
    def run_ids(self) -> tuple[UUID, ...]:
        return tuple(sorted((*self.earlier_run_ids, *self.later_run_ids)))

    def semantic_payload(self) -> dict[str, object]:
        return {
            "version": FORMAT,
            "source": "kimdis.contract",
            "earlier_run_ids": [str(run) for run in self.earlier_run_ids],
            "later_run_ids": [str(run) for run in self.later_run_ids],
        }

    @property
    def request_sha256(self) -> str:
        body = json.dumps(self.semantic_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(body).hexdigest()


def decode_change_request(body: bytes) -> ChangeRequest:
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
        earlier = cast(list[object], data["earlier_run_ids"])
        later = cast(list[object], data["later_run_ids"])
        # One union keeps the bounds and rejects a run that appears twice or in both captures.
        _, bindings = run_fields([*earlier, *later], data["archive_bindings"])
        return ChangeRequest(
            tuple(sorted(uuid_value(run) for run in earlier)),
            tuple(sorted(uuid_value(run) for run in later)),
            bindings,
        )
    except (ValueError, TypeError, RecursionError) as error:
        if isinstance(error, RequestError):
            raise
        raise RequestError("analytics_input") from None


def read_change_request(path: Path) -> ChangeRequest:
    return read_private_request(path, decode_change_request)
