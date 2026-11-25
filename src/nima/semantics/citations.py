"""Explicit KIMDIS citations, resolved only against the declared Diavgeia cohort.

This pure model classifies reported references. It establishes neither identity nor
economic equivalence. Archive/SQL verification belongs to the later readout boundary.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from importlib.resources import files
from typing import cast

from nima.semantics.lifecycle import RELATION_FIELDS, Reference
from nima.semantics.selection import Selected, select_latest

MAX_OBSERVATIONS = 5000
MAX_REFERENCES = 1000
MAX_EDGES = 5000
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
NORMALIZERS = frozenset({"diavgeia-decision-v1", "diavgeia-commitment-v1"})
OUTCOMES = (
    "resolved",
    "unresolved",
    "target_ambiguous",
    "target_type_unknown",
    "target_type_mismatch",
)


class CitationError(ValueError):
    """Only a fixed reason, never a source value."""


@dataclass(frozen=True)
class ContractObservation:
    observation_id: int
    source_id: str
    normalizer_version: str
    content_sha256: str
    observed_at: datetime
    references: tuple[Reference, ...] | None
    cancelled: bool | None


@dataclass(frozen=True)
class DecisionObservation:
    observation_id: int
    source_id: str
    normalizer_version: str
    content_sha256: str
    observed_at: datetime
    ada: str
    decision_type: str | None
    decision_status: str


type Observation = ContractObservation | DecisionObservation


@dataclass(frozen=True)
class Version:
    content_sha256: str
    normalizer_version: str
    observations: tuple[tuple[int, str], ...]
    decision_type: str | None
    decision_status: str | None
    cancelled: bool | None


@dataclass(frozen=True)
class SourceSelection:
    source_id: str
    versions: tuple[Version, ...]


@dataclass(frozen=True)
class Edge:
    source_id: str
    target_id: str
    outcome: str
    source_version: Version
    target_versions: tuple[Version, ...]
    relation: str = "cites_decision"
    source_field: str = "diavgeiaADA"
    reported_relation: str = "commitment_decision"
    expected_target_type: str = "Β.1.3"


@dataclass(frozen=True)
class SharedTarget:
    target_id: str
    citing_records: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class CitationResult:
    status: str
    records: int
    source_ambiguous_ids: tuple[str, ...]
    unknown_reference_ids: tuple[str, ...]
    no_citation_ids: tuple[str, ...]
    sources: tuple[SourceSelection, ...]
    edges: tuple[Edge, ...]
    distinct_targets: int
    outcome_counts: dict[str, int]
    shared_targets: tuple[SharedTarget, ...]

    def payload(self) -> dict[str, object]:
        value = asdict(self)
        size = 0
        encoder = json.JSONEncoder(
            ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        for part in encoder.iterencode(value):
            size += len(part.encode())
            if size > MAX_OUTPUT_BYTES:
                raise CitationError("citation_limit")
        return cast(dict[str, object], json.loads(json.dumps(value, allow_nan=False)))


def _text(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _reference(value: object) -> bool:
    if not isinstance(value, Reference) or not isinstance(value.relation, str):
        return False
    namespace = "diavgeia:" if value.relation == "commitment_decision" else "kimdis:"
    return (
        value.relation in RELATION_FIELDS
        and RELATION_FIELDS[value.relation] == value.source_field
        and isinstance(value.target_id, str)
        and value.target_id.startswith(namespace)
        and _text(value.target_id[len(namespace) :])
    )


def _facts(row: Observation) -> tuple[object, ...]:
    if isinstance(row, ContractObservation):
        return row.normalizer_version, row.references, row.cancelled
    return row.normalizer_version, row.ada, row.decision_type, row.decision_status


def validate_observations(
    contracts: tuple[ContractObservation, ...], decisions: tuple[DecisionObservation, ...]
) -> None:
    """Validate all rows before selection; a nonmatching or future row cannot hide a defect."""
    if not isinstance(contracts, tuple) or not isinstance(decisions, tuple):
        raise CitationError("citation_input")
    if len(contracts) + len(decisions) > MAX_OBSERVATIONS:
        raise CitationError("citation_limit")
    ids: set[int] = set()
    facts: dict[tuple[str, str], tuple[object, ...]] = {}
    for rows, kind, namespace in (
        (contracts, ContractObservation, "kimdis:"),
        (decisions, DecisionObservation, "diavgeia:"),
    ):
        for row in rows:
            if (
                not isinstance(row, kind)
                or type(row.observation_id) is not int
                or row.observation_id <= 0
                or row.observation_id in ids
                or not isinstance(row.source_id, str)
                or not row.source_id.startswith(namespace)
                or not _text(row.source_id[len(namespace) :])
                or not isinstance(row.content_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", row.content_sha256) is None
                or not isinstance(row.observed_at, datetime)
                or row.observed_at.utcoffset() != timedelta(0)
            ):
                raise CitationError("citation_input")
            if isinstance(row, ContractObservation):
                valid = (
                    row.normalizer_version == "kimdis-normalized-v1"
                    and (row.cancelled is None or type(row.cancelled) is bool)
                    and (
                        row.references is None
                        or (
                            isinstance(row.references, tuple)
                            and len(row.references) <= MAX_REFERENCES
                            and all(_reference(ref) for ref in row.references)
                        )
                    )
                )
            else:
                valid = (
                    isinstance(row.normalizer_version, str)
                    and row.normalizer_version in NORMALIZERS
                    and _text(row.ada)
                    and row.source_id == f"diavgeia:{row.ada}"
                    and (row.decision_type is None or _text(row.decision_type))
                    and isinstance(row.decision_status, str)
                    and row.decision_status in {"PUBLISHED", "REVOKED", "PENDING_REVOCATION"}
                )
            key = (row.source_id, row.content_sha256)
            if not valid or (key in facts and facts[key] != _facts(row)):
                raise CitationError("citation_contract")
            ids.add(row.observation_id)
            facts[key] = _facts(row)


def _versions[T: Observation](
    selected: Selected[T], lineage: dict[tuple[str, str], list[Observation]]
) -> tuple[Version, ...]:
    return tuple(
        Version(
            digest,
            row.normalizer_version,
            tuple(
                (o.observation_id, o.observed_at.isoformat())
                for o in sorted(
                    lineage[(selected.source_id, digest)], key=lambda o: o.observation_id
                )
            ),
            row.decision_type if isinstance(row, DecisionObservation) else None,
            row.decision_status if isinstance(row, DecisionObservation) else None,
            row.cancelled if isinstance(row, ContractObservation) else None,
        )
        for digest, row in sorted(selected.versions.items())
    )


def evaluate(
    contracts: tuple[ContractObservation, ...],
    decisions: tuple[DecisionObservation, ...],
    *,
    cutoff: datetime,
) -> CitationResult:
    """Select first, then classify exact citations; keep all lineage for selected content."""
    if not isinstance(cutoff, datetime) or cutoff.utcoffset() != timedelta(0):
        raise CitationError("citation_input")
    validate_observations(contracts, decisions)
    sources = select_latest(contracts, cutoff)
    targets = {row.source_id: row for row in select_latest(decisions, cutoff)}
    lineage: dict[tuple[str, str], list[Observation]] = {}
    observations: tuple[Observation, ...] = (*contracts, *decisions)
    for row in observations:
        if row.observed_at <= cutoff:
            lineage.setdefault((row.source_id, row.content_sha256), []).append(row)
    target_versions = {sid: _versions(row, lineage) for sid, row in targets.items()}
    selections = tuple(SourceSelection(row.source_id, _versions(row, lineage)) for row in sources)
    ambiguous: list[str] = []
    unknown: list[str] = []
    no_citation: list[str] = []
    edges: list[Edge] = []
    for selected, source in zip(sources, selections, strict=True):
        if selected.ambiguous:
            ambiguous.append(source.source_id)
            continue
        if selected.chosen.references is None:
            unknown.append(source.source_id)
            continue
        citations = sorted(
            {
                ref.target_id
                for ref in selected.chosen.references
                if ref.relation == "commitment_decision"
            }
        )
        if not citations:
            no_citation.append(source.source_id)
        for target_id in citations:
            target = targets.get(target_id)
            if target is None:
                outcome = "unresolved"
            elif target.ambiguous:
                outcome = "target_ambiguous"
            elif target.chosen.decision_type is None:
                outcome = "target_type_unknown"
            else:
                outcome = (
                    "resolved" if target.chosen.decision_type == "Β.1.3" else "target_type_mismatch"
                )
            if len(edges) >= MAX_EDGES:
                raise CitationError("citation_limit")
            edges.append(
                Edge(
                    source.source_id,
                    target_id,
                    outcome,
                    source.versions[0],
                    target_versions.get(target_id, ()),
                )
            )
    citing: dict[str, list[str]] = {}
    for edge in edges:
        citing.setdefault(edge.target_id, []).append(edge.source_id)
    status = "observed_citations" if edges else "no_observed_citations"
    if not contracts:
        status = "empty_capture"
    elif not sources:
        status = "no_observations_before_cutoff"
    result = CitationResult(
        status,
        len(sources),
        tuple(ambiguous),
        tuple(unknown),
        tuple(no_citation),
        selections,
        tuple(edges),
        len(citing),
        {s: sum(e.outcome == s for e in edges) for s in OUTCOMES},
        tuple(
            SharedTarget(target, len(ids), tuple(ids))
            for target, ids in sorted(citing.items())
            if len(ids) > 1
        ),
    )
    result.payload()
    return result


def sql_rows(
    contracts: tuple[ContractObservation, ...], decisions: tuple[DecisionObservation, ...]
) -> list[dict[str, object]]:
    """Validated typed input for reference SQL; it does not accept raw or partial SQL facts."""
    validate_observations(contracts, decisions)
    observations: tuple[Observation, ...] = (*contracts, *decisions)
    return [{**asdict(row), "observed_at": row.observed_at.isoformat()} for row in observations]


def reference_sql() -> str:
    """Two bound parameters: validated observation JSON and inclusive UTC cutoff."""
    return files("nima.semantics").joinpath("citations.sql").read_text()


def definition() -> dict[str, object]:
    return {
        "model": "explicit_procurement_citations.v1",
        "status": "draft",
        "matching": "exact_namespaced_ada_no_normalization",
        "selection": "latest_observed_before_type_status_filters_ties_ambiguous",
        "lineage": "all_observations_of_selected_content_at_or_before_cutoff",
        "relation": "cites_decision",
        "source_field": "diavgeiaADA",
        "reported_relation": "commitment_decision",
        "expected_target_type": "Β.1.3",
        "kimdis_normalizer": "kimdis-normalized-v1",
        "diavgeia_normalizers": sorted(NORMALIZERS),
        "outcomes": list(OUTCOMES),
        "scope": "reported_citations_not_identity_or_spending",
        "sql_sha256": hashlib.sha256(reference_sql().encode()).hexdigest(),
    }


def definition_sha256() -> str:
    return hashlib.sha256(
        json.dumps(definition(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
