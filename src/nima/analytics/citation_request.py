"""Private, explicit two-source selection; decoding reads no database or archive."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from nima.analytics.request import (
    MAX_REQUEST_BYTES,
    RequestError,
    constant_hook,
    cutoff_value,
    pairs_hook,
    path_value,
    read_private_request,
    uuid_value,
)
from nima.graph.pilot_archive import ArchiveBinding

FORMAT = "nima-source-citations-request-v1"
_FIELDS = {
    "version",
    "kimdis_run_ids",
    "diavgeia_run_ids",
    "observation_cutoff",
    "archive_bindings",
}


@dataclass(frozen=True)
class CitationRequest:
    kimdis_run_ids: tuple[UUID, ...]
    diavgeia_run_ids: tuple[UUID, ...]
    observation_cutoff: datetime
    archive_bindings: tuple[ArchiveBinding, ...]

    @property
    def run_ids(self) -> tuple[UUID, ...]:
        return tuple(sorted((*self.kimdis_run_ids, *self.diavgeia_run_ids)))

    def semantic_payload(self) -> dict[str, object]:
        return {
            "version": FORMAT,
            "kimdis_run_ids": [str(run) for run in self.kimdis_run_ids],
            "diavgeia_run_ids": [str(run) for run in self.diavgeia_run_ids],
            "observation_cutoff": self.observation_cutoff.isoformat(),
        }

    @property
    def request_sha256(self) -> str:
        body = json.dumps(self.semantic_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(body).hexdigest()


def _runs(value: object) -> tuple[UUID, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= 10:
        raise RequestError("citation_input")
    return tuple(sorted(uuid_value(run) for run in value))


def decode_citation_request(body: bytes) -> CitationRequest:
    if not isinstance(body, bytes):
        raise RequestError("citation_input")
    if len(body) > MAX_REQUEST_BYTES:
        raise RequestError("citation_limit")
    try:
        value: object = json.loads(
            body.decode("utf-8"), object_pairs_hook=pairs_hook, parse_constant=constant_hook
        )
        if not isinstance(value, dict) or set(value) != _FIELDS or value["version"] != FORMAT:
            raise RequestError("citation_input")
        data = cast(dict[str, object], value)
        kimdis, diavgeia = _runs(data["kimdis_run_ids"]), _runs(data["diavgeia_run_ids"])
        runs = (*kimdis, *diavgeia)
        if len(runs) > 10 or len(set(runs)) != len(runs):
            raise RequestError("citation_input")
        raw = data["archive_bindings"]
        if not isinstance(raw, list) or len(raw) != len(runs):
            raise RequestError("citation_input")
        bindings = []
        for binding in raw:
            if not isinstance(binding, dict) or set(binding) != {"source", "run_id", "root"}:
                raise RequestError("citation_input")
            run = uuid_value(binding["run_id"])
            expected: Literal["kimdis", "diavgeia"] = "kimdis" if run in kimdis else "diavgeia"
            if run not in runs or binding["source"] != expected:
                raise RequestError("citation_input")
            bindings.append(ArchiveBinding(expected, run, path_value(binding["root"])))
        if sorted(b.run_id for b in bindings) != sorted(runs):
            raise RequestError("citation_input")
        return CitationRequest(
            kimdis,
            diavgeia,
            cutoff_value(data["observation_cutoff"]),
            tuple(sorted(bindings, key=lambda b: b.run_id)),
        )
    except (ValueError, TypeError, RecursionError):
        raise RequestError("citation_input") from None


def read_citation_request(path: Path) -> CitationRequest:
    try:
        return read_private_request(path, decode_citation_request)
    except RequestError as error:
        reason = (
            "citation_limit"
            if error.reason in {"analytics_limit", "citation_limit"}
            else "citation_input"
        )
        raise RequestError(reason) from None


def validate_citation_request(request: CitationRequest) -> None:
    """Programmatic callers must provide the same canonical selection as file callers."""
    try:
        if not isinstance(request, CitationRequest):
            raise RequestError("citation_input")
        value = {
            **request.semantic_payload(),
            "archive_bindings": [
                {"source": b.source, "run_id": str(b.run_id), "root": str(b.root)}
                for b in request.archive_bindings
            ],
        }
        if decode_citation_request(json.dumps(value).encode()) != request:
            raise RequestError("citation_input")
    except (ValueError, TypeError, AttributeError):
        raise RequestError("citation_input") from None
