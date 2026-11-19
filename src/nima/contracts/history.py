"""Small versioned validation records; no source values or execution metadata."""

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import cast

from nima.contracts.schema import canonical

VALIDATOR_VERSION = "nima-readout-verification-v1"
_DIGEST = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_CHECKS = {
    ("blocked", "artifact_integrity", "artifact_unavailable"),
    ("failed", "artifact_integrity", "artifact_digest"),
    ("blocked", "reconstruction", "inputs_unavailable"),
    ("failed", "output_contract", "contract_rejected"),
    ("failed", "byte_equivalence", "bytes_differ"),
    ("passed", "byte_equivalence", "ok"),
}


class HistoryError(ValueError):
    """Fixed codes only; no SQL context, source values or private locations."""


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


@dataclass(frozen=True)
class Intent:
    request_sha256: str
    artifact_sha256: str
    contract_version: str
    contract_sha256: str

    def __post_init__(self) -> None:
        if (
            not all(
                valid_digest(v)
                for v in (self.request_sha256, self.artifact_sha256, self.contract_sha256)
            )
            or not isinstance(self.contract_version, str)
            or _VERSION.fullmatch(self.contract_version) is None
        ):
            raise HistoryError("validation_configuration")

    def payload(self) -> dict[str, object]:
        return {
            "version": "nima-validation-intent-v1",
            **asdict(self),
            "contract_id": "nima.supplier-buyers-readout",
            "validator_version": VALIDATOR_VERSION,
        }

    @property
    def digest(self) -> str:
        return digest(self.payload())


@dataclass(frozen=True)
class Outcome:
    intent_sha256: str
    status: str
    check: str
    reason: str
    snapshot_sha256: str | None = None
    observation_count: int | None = None
    record_count: int | None = None

    def __post_init__(self) -> None:
        if (
            not valid_digest(self.intent_sha256)
            or (self.status, self.check, self.reason) not in _CHECKS
        ):
            raise HistoryError("validation_integrity")
        if self.status == "passed":
            if (
                not valid_digest(self.snapshot_sha256)
                or type(self.observation_count) is not int
                or type(self.record_count) is not int
                or not 0 <= self.record_count <= self.observation_count <= 500
            ):
                raise HistoryError("validation_integrity")
        elif any(
            v is not None for v in (self.snapshot_sha256, self.observation_count, self.record_count)
        ):
            raise HistoryError("validation_integrity")

    def payload(self) -> dict[str, object]:
        return {"version": "nima-validation-outcome-v1", **asdict(self)}

    @property
    def digest(self) -> str:
        return digest(self.payload())


def decode_outcome(value: object) -> Outcome:
    keys = {
        "version",
        "intent_sha256",
        "status",
        "check",
        "reason",
        "snapshot_sha256",
        "observation_count",
        "record_count",
    }
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or value["version"] != "nima-validation-outcome-v1"
    ):
        raise HistoryError("validation_integrity")
    try:
        return Outcome(
            cast(str, value["intent_sha256"]),
            cast(str, value["status"]),
            cast(str, value["check"]),
            cast(str, value["reason"]),
            cast(str | None, value["snapshot_sha256"]),
            cast(int | None, value["observation_count"]),
            cast(int | None, value["record_count"]),
        )
    except (ValueError, TypeError):
        raise HistoryError("validation_integrity") from None


def decode_intent(value: object) -> Intent:
    try:
        if not isinstance(value, dict):
            raise HistoryError("validation_integrity")
        result = Intent(
            cast(str, value["request_sha256"]),
            cast(str, value["artifact_sha256"]),
            cast(str, value["contract_version"]),
            cast(str, value["contract_sha256"]),
        )
        if result.payload() != value:
            raise HistoryError("validation_integrity")
        return result
    except (ValueError, TypeError, KeyError):
        raise HistoryError("validation_integrity") from None
