"""Immutable review inputs; parsing does not establish SQL evidence or authority."""

import hashlib
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from nima.identity.artifacts import encode

if TYPE_CHECKING:
    from nima.identity.registry_cohort import ComparisonCohort, RegistryEvidence
    from nima.identity.registry_policy import RegistryObservation

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
            result.update(
                report_sha256=self.report_sha256, acknowledged_issues=list(self.acknowledged_issues)
            )
        if self.operation == "accept":
            result["entity_id"] = str(self.entity_id)
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


@dataclass(frozen=True)
class ReviewAnchor:
    """Policy view of a handle's anchor; storage must validate the SQL reference."""

    entity_id: UUID
    observation: "RegistryObservation"


@dataclass(frozen=True)
class ReviewEvent:
    """Pure decision view, not a committed or authenticated database event."""

    request: ReviewRequest
    subject_revision: int
    issues: tuple[str, ...] = ()
    policy_version: str = REVIEW_POLICY_VERSION

    @property
    def event_id(self) -> UUID:
        return self.request.request_id


@dataclass(frozen=True)
class ReviewPairState:
    candidate: ReviewCandidate
    state: Literal["unreviewed", "accepted", "rejected"]
    event_id: UUID | None
    entity_id: UUID | None
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewHead:
    subject: ReviewSubject
    revision: int
    pairs: tuple[ReviewPairState, ...] = ()

    @property
    def accepted_entity_id(self) -> UUID | None:
        return next((pair.entity_id for pair in self.pairs if pair.state == "accepted"), None)

    @property
    def automatic_identity_links(self) -> Literal[0]:
        return 0


@dataclass(frozen=True)
class ReviewEvidence:
    """Selected SQL views; writers must revalidate inside their own transaction."""

    cohort: "ComparisonCohort"
    anchors: Mapping[UUID, "RegistryEvidence"]
    input_bytes: int
