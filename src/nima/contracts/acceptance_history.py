"""Immutable citation-attestation identities; no SQL, source access or policy execution."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from nima.contracts.history import valid_digest
from nima.contracts.schema import canonical

POLICY_SHA256 = "f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06"
RECORDER_VERSION = "nima-citation-acceptance-record-v1"
MAX_BODY_BYTES = 65536
_FITNESS = {"ready", "limited", "blocked", "not_assessed"}
_REFUSALS = {
    f"acceptance_{r}" for r in ("input", "limit", "evidence", "database", "contract", "output")
}
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,95}")
# Historical compatibility is separate from defaults used to create new intents.
_SUPPORTED = frozenset(
    {
        (
            "nima-citation-acceptance-record-v1",
            "1.0.0",
            "f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06",
        )
    }
)


class HistoryError(ValueError):
    """Only fixed recorder codes cross command boundaries."""

    def __init__(self, reason: str) -> None:
        allowed = {
            f"acceptance_history_{r}"
            for r in (
                "configuration",
                "integrity",
                "policy",
                "database",
                "schema",
                "unknown",
                "busy",
                "conflict",
                "interrupted",
                "limit",
            )
        }
        super().__init__(reason if reason in allowed else "acceptance_history_integrity")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Intent:
    request_sha256: str
    subject_sha256: str
    policy_sha256: str = POLICY_SHA256
    policy_version: str = "1.0.0"
    recorder_version: str = RECORDER_VERSION

    def __post_init__(self) -> None:
        if (
            not all(
                valid_digest(v)
                for v in (self.request_sha256, self.subject_sha256, self.policy_sha256)
            )
            or not isinstance(self.policy_version, str)
            or len(self.policy_version) > 64
            or _VERSION.fullmatch(self.policy_version) is None
            or not isinstance(self.recorder_version, str)
            or _LABEL.fullmatch(self.recorder_version) is None
        ):
            raise HistoryError("acceptance_history_configuration")

    def payload(self) -> dict[str, object]:
        return {
            "version": "nima-acceptance-intent-v1",
            "use": "citations",
            "subject_format": "nima-source-citations-v1",
            "policy_id": "nima.dataset-acceptance",
            **asdict(self),
        }

    @property
    def digest(self) -> str:
        return digest(self.payload())

    @property
    def supported(self) -> bool:
        return (self.recorder_version, self.policy_version, self.policy_sha256) in _SUPPORTED


def decode_intent(value: object) -> Intent:
    try:
        if not isinstance(value, dict):
            raise ValueError
        result = Intent(
            *(
                cast(str, value[k])
                for k in (
                    "request_sha256",
                    "subject_sha256",
                    "policy_sha256",
                    "policy_version",
                    "recorder_version",
                )
            )
        )
        if canonical(result.payload()) != canonical(value):
            raise ValueError
        return result
    except (ValueError, TypeError, KeyError):
        raise HistoryError("acceptance_history_integrity") from None


@dataclass(frozen=True)
class Outcome:
    intent_sha256: str
    execution_state: str
    data_fitness: str | None
    acceptance_sha256: str | None
    refusal_code: str | None

    def __post_init__(self) -> None:
        if not valid_digest(self.intent_sha256) or not (
            (
                self.execution_state == "assessed"
                and isinstance(self.data_fitness, str)
                and self.data_fitness in _FITNESS
                and valid_digest(self.acceptance_sha256)
                and self.refusal_code is None
            )
            or (
                self.execution_state == "refused"
                and self.data_fitness is None
                and self.acceptance_sha256 is None
                and isinstance(self.refusal_code, str)
                and self.refusal_code in _REFUSALS
            )
        ):
            raise HistoryError("acceptance_history_integrity")

    def payload(self) -> dict[str, object]:
        return {"version": "nima-acceptance-outcome-v1", **asdict(self)}

    @property
    def digest(self) -> str:
        return digest(self.payload())


def decode_outcome(value: object) -> Outcome:
    try:
        if not isinstance(value, dict):
            raise ValueError
        result = Outcome(
            cast(str, value["intent_sha256"]),
            cast(str, value["execution_state"]),
            cast(str | None, value["data_fitness"]),
            cast(str | None, value["acceptance_sha256"]),
            cast(str | None, value["refusal_code"]),
        )
        if canonical(result.payload()) != canonical(value):
            raise ValueError
        return result
    except (ValueError, TypeError, KeyError):
        raise HistoryError("acceptance_history_integrity") from None


def _object(value: object, fields: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise HistoryError("acceptance_history_integrity")
    return value


def assessed_outcome(intent: Intent, body: bytes) -> Outcome:
    """Validate a recorded v1 body and its bindings, without running the policy."""
    if not intent.supported:
        raise HistoryError("acceptance_history_policy")
    if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_BODY_BYTES:
        raise HistoryError("acceptance_history_limit")
    try:
        value = _object(
            json.loads(body.decode("utf-8")),
            "version subject policy assessment interpretation_limits",
        )
        if (
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
            ).encode()
            != body
        ):
            raise ValueError
        subject = _object(
            value["subject"],
            "version artifact_sha256 request cohort_sha256 run_profiles evidence_scope "
            "raw_bytes model",
        )
        metadata = _object(value["policy"], "definition definition_sha256")
        model = _object(subject["model"], "id status definition_sha256 sql_sha256")
        assessment = _object(
            value["assessment"],
            "policy_sha256 facts_sha256 request_sha256 cohort_sha256 use provider_status "
            "status checks "
            "required_checks counts limitations definition_sha256 sql_sha256 "
            "policy_id policy_version "
            "amount_eligibility",
        )
        rules = metadata["definition"]
        if (
            value["version"] != "nima-citation-acceptance-v1"
            or subject["version"] != "nima-source-citations-v1"
            or subject["artifact_sha256"] != intent.subject_sha256
            or digest(subject["request"]) != intent.request_sha256
            or metadata["definition_sha256"] != intent.policy_sha256
            or digest(rules) != intent.policy_sha256
            or assessment["policy_sha256"] != intent.policy_sha256
            or assessment["policy_id"] != "nima.dataset-acceptance"
            or assessment["policy_version"] != intent.policy_version
            or assessment["request_sha256"] != intent.request_sha256
            or assessment["cohort_sha256"] != subject["cohort_sha256"]
            or not valid_digest(subject["cohort_sha256"])
            or assessment["use"] != "citations"
            or assessment["status"] not in _FITNESS
            or assessment["amount_eligibility"] != "not_applicable"
            or model["id"] != "explicit_procurement_citations.v1"
            or model["status"] not in {"draft", "reviewed", "certified"}
            or not all(
                valid_digest(assessment[k])
                for k in ("facts_sha256", "definition_sha256", "sql_sha256")
            )
            or model["definition_sha256"] != assessment["definition_sha256"]
            or model["sql_sha256"] != assessment["sql_sha256"]
            or assessment["provider_status"] not in rules["provider_statuses"]["citations"]
            or assessment["required_checks"] != rules["required_checks"]["citations"]
            or not isinstance(subject["run_profiles"], list)
            or len(subject["run_profiles"]) > 10
            or subject["evidence_scope"] != "all_admitted_pages"
            or subject["raw_bytes"] not in {"verified_against_archived_bytes", "no_admitted_pages"}
            or not isinstance(value["interpretation_limits"], list)
            or any(not isinstance(t, str) for t in value["interpretation_limits"])
        ):
            raise ValueError
        checks = assessment["checks"]
        if not isinstance(checks, list) or len(checks) != len(rules["failure_reasons"]):
            raise ValueError
        seen = set()
        for row in checks:
            check = _object(row, "check_id status reason")
            cid = check["check_id"]
            allowed = {
                "passed": [rules["successful_check_reason"]],
                "failed": rules["failure_reasons"][cid],
                "not_assessed": rules["unassessed_reasons"],
                "not_applicable": [rules["not_applicable_reason"]],
            }
            if cid in seen or check["reason"] not in allowed[check["status"]]:
                raise ValueError
            seen.add(cid)
        if not isinstance(assessment["counts"], list):
            raise ValueError
        seen = set()
        for row in assessment["counts"]:
            count = _object(row, "name grain value")
            name = count["name"]
            if (
                name in seen
                or count["grain"] != rules["count_grains"][name]
                or type(count["value"]) is not int
                or not 0 <= count["value"] <= 2**63 - 1
            ):
                raise ValueError
            seen.add(name)
        limits = assessment["limitations"]
        if (
            not isinstance(limits, list)
            or limits != sorted(set(limits))
            or set(limits)
            - set(
                (
                    *rules["limiting_counts"]["citations"],
                    "partial_capture",
                    "capture_completeness_unknown",
                )
            )
            or (assessment["status"] != "limited" and limits)
        ):
            raise ValueError
        return Outcome(
            intent.digest, "assessed", assessment["status"], hashlib.sha256(body).hexdigest(), None
        )
    except (ValueError, TypeError, KeyError, RecursionError):
        raise HistoryError("acceptance_history_integrity") from None


@dataclass(frozen=True)
class Record:
    attempt_id: UUID
    intent: Intent
    started_at: datetime
    outcome: Outcome | None
    recorded_at: datetime | None
    body: bytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.attempt_id, UUID)
            or not isinstance(self.intent, Intent)
            or not isinstance(self.started_at, datetime)
            or self.started_at.utcoffset() is None
            or (self.outcome is None) != (self.recorded_at is None)
            or (
                self.recorded_at is not None
                and (
                    not isinstance(self.recorded_at, datetime)
                    or self.recorded_at.utcoffset() is None
                )
            )
            or (
                self.outcome is not None
                and (
                    not isinstance(self.outcome, Outcome)
                    or self.outcome.intent_sha256 != self.intent.digest
                )
            )
        ):
            raise HistoryError("acceptance_history_integrity")
        if self.outcome is not None and self.outcome.execution_state == "assessed":
            if (
                not isinstance(self.body, bytes)
                or assessed_outcome(self.intent, self.body) != self.outcome
            ):
                raise HistoryError("acceptance_history_integrity")
        elif self.body is not None:
            raise HistoryError("acceptance_history_integrity")

    @property
    def execution_state(self) -> str:
        return "pending" if self.outcome is None else self.outcome.execution_state

    def payload(self, *, reused: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "version": "nima-acceptance-history-v1",
            "attempt_id": str(self.attempt_id),
            "intent_sha256": self.intent.digest,
            "intent": self.intent.payload(),
            "started_at": self.started_at.isoformat(),
            "recorded_at": None if self.recorded_at is None else self.recorded_at.isoformat(),
            "outcome_sha256": None if self.outcome is None else self.outcome.digest,
            "outcome": None if self.outcome is None else self.outcome.payload(),
            "execution_state": self.execution_state,
            "reused": reused,
            "verification_scope": "recorded_acceptance_history_only"
            if reused
            else "fresh_recording_attempt",
        }
        return value
