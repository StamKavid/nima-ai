"""Closed private selection for the buyer-concentration readout; decoding touches no archive."""

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

FORMAT = "nima-buyer-concentration-request-v1"
_FIELDS = {"version", "source", "run_ids", "observation_cutoff", "buyer", "archive_bindings"}
_BUYER = re.compile(r"[!-~]{1,64}")


@dataclass(frozen=True)
class BuyerRequest:
    run_ids: tuple[UUID, ...]
    observation_cutoff: datetime
    buyer: str
    archive_bindings: tuple[ArchiveBinding, ...]

    def semantic_payload(self) -> dict[str, object]:
        return {
            "version": FORMAT,
            "source": "kimdis.contract",
            "run_ids": [str(run) for run in self.run_ids],
            "observation_cutoff": self.observation_cutoff.isoformat(),
            "buyer": self.buyer,
        }

    @property
    def request_sha256(self) -> str:
        body = json.dumps(self.semantic_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(body).hexdigest()


def decode_buyer_request(body: bytes) -> BuyerRequest:
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
        buyer = data["buyer"]
        if (
            data["version"] != FORMAT
            or data["source"] != "kimdis.contract"
            or not isinstance(buyer, str)
            or _BUYER.fullmatch(buyer) is None
        ):
            raise RequestError("analytics_input")
        runs, cutoff, bindings = cohort_fields(data)
        return BuyerRequest(runs, cutoff, buyer, bindings)
    except (ValueError, TypeError, RecursionError) as error:
        if isinstance(error, RequestError):
            raise
        raise RequestError("analytics_input") from None


def read_buyer_request(path: Path) -> BuyerRequest:
    return read_private_request(path, decode_buyer_request)
