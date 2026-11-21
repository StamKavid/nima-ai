"""Closed private selections; decoding does not access archives, SQL or sources."""

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Never, cast
from uuid import UUID

from nima.evidence import EvidenceError, artifacts
from nima.graph.pilot_archive import ArchiveBinding
from nima.semantics.parties import valid_tax_id

MAX_REQUEST_BYTES = 16 * 1024
FORMAT = "nima-participation-request-v1"
_FIELDS = {
    "version",
    "source",
    "run_ids",
    "observation_cutoff",
    "supplier_country",
    "supplier_tax_id",
    "archive_bindings",
}


class RequestError(ValueError):
    """Fixed reason only; input values and filesystem details remain private."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ReadoutRequest:
    run_ids: tuple[UUID, ...]
    observation_cutoff: datetime
    supplier_tax_id: str
    archive_bindings: tuple[ArchiveBinding, ...]
    supplier_country: str = "GR"

    def semantic_payload(self) -> dict[str, object]:
        return {
            "version": FORMAT,
            "source": "kimdis.contract",
            "run_ids": [str(run) for run in self.run_ids],
            "observation_cutoff": self.observation_cutoff.isoformat(),
            "supplier_country": self.supplier_country,
            "supplier_tax_id": self.supplier_tax_id,
        }

    @property
    def request_sha256(self) -> str:
        body = json.dumps(self.semantic_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(body).hexdigest()


def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RequestError("analytics_input")
        result[key] = value
    return result


def constant_hook(value: str) -> Never:
    raise RequestError("analytics_input")


def uuid_value(value: object) -> UUID:
    if not isinstance(value, str):
        raise RequestError("analytics_input")
    parsed = UUID(value)
    if str(parsed) != value:
        raise RequestError("analytics_input")
    return parsed


def path_value(value: object) -> Path:
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or "\x00" in value:
        raise RequestError("analytics_input")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise RequestError("analytics_input") from None
    path = Path(value)
    if (
        not path.is_absolute()
        or value.startswith("//")
        or str(path) != value
        or any(part in {".", "..", ".git"} for part in value.split("/"))
    ):
        raise RequestError("analytics_input")
    return path


def cutoff_value(value: object) -> datetime:
    if (
        not isinstance(value, str)
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)",
            value,
        )
        is None
    ):
        raise RequestError("analytics_input")
    return datetime.fromisoformat(value).astimezone(UTC)


def decode_request(body: bytes) -> ReadoutRequest:
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
        if (
            data["version"] != FORMAT
            or data["source"] != "kimdis.contract"
            or data["supplier_country"] != "GR"
            or not valid_tax_id(data["supplier_tax_id"])
        ):
            raise RequestError("analytics_input")
        raw_runs, raw_bindings = data["run_ids"], data["archive_bindings"]
        if (
            not isinstance(raw_runs, list)
            or not 1 <= len(raw_runs) <= 10
            or not isinstance(raw_bindings, list)
            or len(raw_bindings) != len(raw_runs)
        ):
            raise RequestError("analytics_input")
        runs = tuple(sorted(uuid_value(run) for run in raw_runs))
        if len(set(runs)) != len(runs):
            raise RequestError("analytics_input")
        bindings = []
        for binding in raw_bindings:
            if not isinstance(binding, dict) or set(binding) != {"run_id", "root"}:
                raise RequestError("analytics_input")
            bindings.append(
                ArchiveBinding("kimdis", uuid_value(binding["run_id"]), path_value(binding["root"]))
            )
        if sorted(binding.run_id for binding in bindings) != list(runs):
            raise RequestError("analytics_input")
        return ReadoutRequest(
            runs,
            cutoff_value(data["observation_cutoff"]),
            cast(str, data["supplier_tax_id"]),
            tuple(sorted(bindings, key=lambda binding: binding.run_id)),
        )
    except (ValueError, TypeError, RecursionError) as error:
        if isinstance(error, RequestError):
            raise
        raise RequestError("analytics_input") from None


def read_private_request[T](path: Path, decode: Callable[[bytes], T]) -> T:
    if not isinstance(path, Path):
        raise RequestError("analytics_input")
    descriptor = None
    try:
        absolute = path_value(str(path.absolute()))
        descriptor = artifacts.directory(absolute.parent, private=True)
        before = os.stat(absolute.name, dir_fd=descriptor, follow_symlinks=False)
        if before.st_nlink != 1:
            raise RequestError("analytics_input_file")
        if before.st_size > MAX_REQUEST_BYTES:
            raise RequestError("analytics_limit")
        body = artifacts.read(descriptor, absolute.name, limit=MAX_REQUEST_BYTES, private=True)
        if len(body) != before.st_size:
            # A write right after the first stat can keep the same coarse ctime tick; the size
            # still differs, so the bytes read are not the file that was checked.
            raise RequestError("analytics_input_file")
        after = os.stat(absolute.name, dir_fd=descriptor, follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_ctime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_ctime_ns,
        ) or after.st_nlink != 1:
            raise RequestError("analytics_input_file")
    except (OSError, EvidenceError):
        raise RequestError("analytics_input_file") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return decode(body)


def read_request(path: Path) -> ReadoutRequest:
    return read_private_request(path, decode_request)
