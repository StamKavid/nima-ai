"""Lifecycle references (M4): explicit edges between captured records, never inferred chains.

Only references a source states form edges, with the relation fixed by the source field. A
reference records that one record *cites* another; it never says the cited record is superseded,
and nothing here removes or merges a record. A target is ``resolved`` only if it is selected in
the cohort. Targets of other procurement stages (awards, payments) are expected to be
``unresolved`` in a contract-only capture, so that status describes the cohort, not a defect.
Sharing of a target is disclosed; an umbrella is flagged only when the caller supplies a
threshold, because none is adopted by default.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import cast

from nima.semantics.participation import SemanticError
from nima.semantics.selection import select_latest

MAX_OBSERVATIONS = 5000
MAX_REFERENCES = 1000
RELATION_FIELDS = {
    "award": "auctionRefNo",
    "previous_record": "prevReferenceNo",
    "payment_order": "paymentRefNo",
    "commitment_decision": "diavgeiaADA",
}
_SHA = re.compile(r"[0-9a-f]{64}")
_TARGET = re.compile(r"([a-z][a-z0-9.-]*):(.+)", re.DOTALL)


@dataclass(frozen=True)
class Reference:
    relation: str
    target_id: str
    source_field: str


@dataclass(frozen=True)
class Cited:
    observation_id: int
    source_id: str
    content_sha256: str
    observed_at: datetime
    references: tuple[Reference, ...] | None


@dataclass(frozen=True)
class Edge:
    source_id: str
    relation: str
    source_field: str
    target_id: str
    status: str
    umbrella: bool
    version_hash: str
    observation_ids: tuple[int, ...]


@dataclass(frozen=True)
class RelationSummary:
    relation: str
    references: int
    distinct_targets: int
    resolved: int
    unresolved: int
    external: int
    target_ambiguous: int
    self_reference: int
    max_citing_records: int


@dataclass(frozen=True)
class SharedTarget:
    relation: str
    target_id: str
    citing_records: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class UmbrellaTarget:
    relation: str
    target_id: str
    citing_records: int


@dataclass(frozen=True)
class LifecycleResult:
    status: str
    umbrella_threshold: int | None
    records: int
    relations: tuple[RelationSummary, ...]
    edges: tuple[Edge, ...]
    shared_targets: tuple[SharedTarget, ...]
    umbrella_targets: tuple[UmbrellaTarget, ...]
    ambiguous_source_ids: tuple[str, ...]
    unknown_reference_source_ids: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(json.dumps(asdict(self), allow_nan=False)))


def definition() -> dict[str, object]:
    return {
        "model": "lifecycle_references.v1",
        "status": "draft",
        "edges": "explicit_source_references_only",
        "relations": RELATION_FIELDS,
        "resolution": "resolved_only_if_the_target_is_selected_in_the_cohort",
        "statuses": ["external", "resolved", "self_reference", "target_ambiguous", "unresolved"],
        "cites": "a_reference_records_a_citation_not_supersession",
        "umbrella": "no_default_threshold_disclose_sharing_and_flag_only_when_asked",
        "revision": "latest_captured_before_filters_ties_unresolved",
        "sql": "not_provided_until_a_metric_consumes_edges",
    }


def definition_sha256() -> str:
    return hashlib.sha256(
        json.dumps(definition(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _valid_reference(value: object) -> bool:
    if not isinstance(value, Reference):
        return False
    if (
        not isinstance(value.relation, str)
        or RELATION_FIELDS.get(value.relation) != value.source_field
    ):
        return False
    if not isinstance(value.target_id, str):
        return False
    match = _TARGET.fullmatch(value.target_id)
    return match is not None and bool(match.group(2).strip())


def _valid_observation(row: object) -> bool:
    return (
        isinstance(row, Cited)
        and type(row.observation_id) is int
        and row.observation_id > 0
        and isinstance(row.source_id, str)
        and row.source_id.startswith("kimdis:")
        and bool(row.source_id[7:].strip())
        and isinstance(row.content_sha256, str)
        and _SHA.fullmatch(row.content_sha256) is not None
        and isinstance(row.observed_at, datetime)
        and row.observed_at.utcoffset() == timedelta(0)
        and (
            row.references is None
            or (
                isinstance(row.references, tuple)
                and len(row.references) <= MAX_REFERENCES
                and all(_valid_reference(ref) for ref in row.references)
            )
        )
    )


def _validate(observations: tuple[Cited, ...]) -> None:
    if not isinstance(observations, tuple) or len(observations) > MAX_OBSERVATIONS:
        raise SemanticError("semantic_input")
    ids: set[int] = set()
    versions: dict[tuple[str, str], object] = {}
    for row in observations:
        if not _valid_observation(row) or row.observation_id in ids:
            raise SemanticError("semantic_input")
        ids.add(row.observation_id)
        key = (row.source_id, row.content_sha256)
        if key in versions and versions[key] != row.references:
            raise SemanticError("semantic_version_conflict")
        versions[key] = row.references


def evaluate(
    observations: tuple[Cited, ...], *, cutoff: datetime, umbrella_threshold: int | None = None
) -> LifecycleResult:
    """Select captured revisions, then classify every explicit reference of the selected records."""
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() != timedelta(0):
        raise SemanticError("semantic_selection")
    if umbrella_threshold is not None and (
        type(umbrella_threshold) is not int or umbrella_threshold < 1
    ):
        raise SemanticError("semantic_selection")
    _validate(observations)
    selections = select_latest(observations, cutoff)
    ambiguous = tuple(item.source_id for item in selections if item.ambiguous)
    selected = {item.source_id: item for item in selections if not item.ambiguous}
    unknown = tuple(sid for sid, item in selected.items() if item.chosen.references is None)
    citations: dict[tuple[str, str], set[str]] = {}
    pending: list[tuple[str, Reference]] = []
    for source_id, item in selected.items():
        seen: set[tuple[str, str]] = set()
        for ref in item.chosen.references or ():
            if (ref.relation, ref.target_id) in seen:
                continue
            seen.add((ref.relation, ref.target_id))
            citations.setdefault((ref.relation, ref.target_id), set()).add(source_id)
            pending.append((source_id, ref))
    flagged = {
        key
        for key, citing in citations.items()
        if umbrella_threshold is not None and len(citing) > umbrella_threshold
    }

    def status(source_id: str, ref: Reference) -> str:
        if ref.target_id == source_id:
            return "self_reference"
        if not ref.target_id.startswith("kimdis:"):
            return "external"
        if ref.target_id in selected:
            return "resolved"
        return "target_ambiguous" if ref.target_id in ambiguous else "unresolved"

    edges = tuple(
        Edge(
            source_id,
            ref.relation,
            ref.source_field,
            ref.target_id,
            status(source_id, ref),
            (ref.relation, ref.target_id) in flagged,
            next(iter(selected[source_id].versions)),
            tuple(sorted(row.observation_id for row in selected[source_id].current)),
        )
        for source_id, ref in sorted(pending, key=lambda p: (p[0], p[1].relation, p[1].target_id))
    )
    relations = tuple(
        RelationSummary(
            relation,
            len(rows),
            len({row.target_id for row in rows}),
            sum(row.status == "resolved" for row in rows),
            sum(row.status == "unresolved" for row in rows),
            sum(row.status == "external" for row in rows),
            sum(row.status == "target_ambiguous" for row in rows),
            sum(row.status == "self_reference" for row in rows),
            max(len(citations[(relation, row.target_id)]) for row in rows),
        )
        for relation in sorted({edge.relation for edge in edges})
        for rows in [[edge for edge in edges if edge.relation == relation]]
    )
    shared = tuple(
        SharedTarget(relation, target, len(citing), tuple(sorted(citing)))
        for (relation, target), citing in sorted(citations.items())
        if len(citing) >= 2
    )
    umbrella = tuple(
        UmbrellaTarget(relation, target, len(citations[(relation, target)]))
        for relation, target in sorted(flagged)
    )
    if not observations:
        state = "empty_capture"
    elif not selections:
        state = "no_observations_before_cutoff"
    elif edges:
        state = "observed_references"
    else:
        state = "no_references"
    return LifecycleResult(
        state,
        umbrella_threshold,
        len(selected),
        relations,
        edges,
        shared,
        umbrella,
        ambiguous,
        tuple(sorted(unknown)),
    )
