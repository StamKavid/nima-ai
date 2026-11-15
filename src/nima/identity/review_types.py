"""Immutable review inputs; parsing does not establish SQL evidence or authority."""

import hashlib
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from nima.identity.artifacts import encode

if TYPE_CHECKING:
    from nima.identity.registry_cohort import ComparisonCohort

REQUEST_FORMAT = "nima-identity-review-request-v1"
REVIEW_POLICY_VERSION = "reviewed-identity-v1"
MAX_REQUEST_BYTES = 16 * 1024
MAX_RATIONALE_BYTES = 4 * 1024
CONFLICT_CODES = frozenset(
    {
        "multiple_registry_numbers_for_reported_afm",
        "reported_afm_changed_for_registry_number",
    }
)
type ReviewOperation = Literal["accept", "reject", "revoke"]
type ReviewRole = Literal["buyer", "supplier"]


class ReviewError(Exception):
    """Fixed diagnostics only; never attach a path, free text or driver message."""

    def __init__(
        self,
        reason: Literal[
            "review_input",
            "review_input_io",
            "review_limit",
            "review_state",
            "review_conflict",
            "review_evidence",
            "review_permission",
            "review_database",
            "review_schema",
            "review_output",
        ],
    ) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ReviewSubject:
    run_id: UUID
    observation_id: int
    projection_version: str
    source_id: str
    normalizer_version: str
    content_sha256: str
    role: ReviewRole
    ordinal: int

    def payload(self) -> dict[str, object]:
        return {**asdict(self), "run_id": str(self.run_id)}


@dataclass(frozen=True)
class ReviewCandidate:
    import_id: UUID
    registry_number: str

    def payload(self) -> dict[str, object]:
        return {"import_id": str(self.import_id), "registry_number": self.registry_number}


@dataclass(frozen=True)
class ReviewRequest:
    request_id: UUID
    operation: ReviewOperation
    subject: ReviewSubject
    candidate: ReviewCandidate
    expected_revision: int
    rationale: str
    report_sha256: str | None = None
    entity_id: UUID | None = None
    reverses_event_id: UUID | None = None
    acknowledged_issues: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        result: dict[str, object] = {
            "request_format": REQUEST_FORMAT,
            "operation": self.operation,
            "subject": self.subject.payload(),
            "candidate": self.candidate.payload(),
            "expected_revision": self.expected_revision,
            "rationale": self.rationale,
        }
        if self.operation in ("accept", "reject"):
            result["report_sha256"] = self.report_sha256
        if self.operation == "accept":
            result.update(
                entity_id=str(self.entity_id), acknowledged_issues=list(self.acknowledged_issues)
            )
        if self.operation == "revoke":
            result["reverses_event_id"] = str(self.reverses_event_id)
        return result

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode(self.payload())).hexdigest()


@dataclass(frozen=True)
class ReviewReport:
    """Parsed byte-identified claims, NOT evidence validated against PostgreSQL."""

    sha256: str
    cohort: "ComparisonCohort"
