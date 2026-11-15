"""Pure graph/focus construction from the complete, validated source snapshot.

No SQL, collection or identity inference. The embedded resolution is produced by
the existing review layer; graph links point to its exact active acceptance events.
"""

import hashlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import TypedDict
from uuid import UUID

from nima.graph import GraphError
from nima.graph.snapshot import MAX_OCCURRENCES, ContractKey, GraphSnapshot
from nima.identity import MAX_REGISTRY_OBSERVATIONS, AssessmentError
from nima.identity.artifacts import encode
from nima.identity.review_export import Resolution, build_resolution
from nima.identity.review_state import MAX_REVIEW_EVENTS

MAX_NODES = 600
MAX_EDGES = 500
_NAMESPACE = "nima:graph:v1"


class Node(TypedDict):
    id: str
    kind: str
    key: dict[str, object]
    data: dict[str, object]


class Edge(TypedDict):
    id: str
    kind: str
    source: str
    target: str
    assertion_key: dict[str, object]
    data: dict[str, object]


class FocusOccurrence(TypedDict):
    occurrence_id: str
    contract_version_id: str
    reviewed_as_edge_id: str
    subject_revision: int
    acceptance_event_id: str
    candidate: dict[str, object]


class FocusContract(TypedDict):
    contract_version_id: str
    facts: dict[str, object]
    buyer_selection: str
    buyer_occurrence_ids: list[str]


class Focus(TypedDict):
    state: str
    entity_id: str | None
    entity_handle_id: str | None
    anchor_observation_id: str | None
    active_occurrences: list[FocusOccurrence]
    contracts: list[FocusContract]


class InvestigationGraph(TypedDict):
    graph_format: str
    graph_policy_version: str
    comparison_report_sha256: str
    projection_version: str
    reviewed_resolution_sha256: str
    reviewed_resolution: Resolution
    coverage_assurance: str
    attribution_assurance: str
    archive_integrity: str
    automatic_identity_links: int
    reviewed_accepted_links: int
    nodes: list[Node]
    edges: list[Edge]
    focus: Focus


def _hash(value: object) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


@dataclass
class _Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)

    def node(
        self,
        kind: str,
        key: dict[str, object],
        data: dict[str, object],
        *,
        identity: str | None = None,
    ) -> str:
        identifier = f"{_NAMESPACE}:{kind}:{identity if identity is not None else _hash(key)}"
        node: Node = {"id": identifier, "kind": kind, "key": key, "data": data}
        prior = self.nodes.get(identifier)
        if prior is not None and prior != node:
            raise GraphError("graph_state")
        self.nodes[identifier] = node
        if len(self.nodes) > MAX_NODES:
            raise GraphError("graph_limit")
        return identifier

    def evidence(self, digest: str) -> str:
        return self.node(
            "evidence_object",
            {"raw_sha256": digest},
            {"archive_integrity": "not_checked"},
            identity=digest,
        )

    def edge(
        self,
        kind: str,
        source: str,
        target: str,
        assertion_key: dict[str, object],
        data: dict[str, object],
    ) -> str:
        assertion = {
            "kind": kind,
            "source": source,
            "target": target,
            "assertion_key": assertion_key,
        }
        identifier = f"{_NAMESPACE}:edge:{kind}:{_hash(assertion)}"
        if identifier in self.edges:
            raise GraphError("graph_state")
        self.edges[identifier] = {
            "id": identifier,
            "kind": kind,
            "source": source,
            "target": target,
            "assertion_key": assertion_key,
            "data": data,
        }
        if len(self.edges) > MAX_EDGES:
            raise GraphError("graph_limit")
        return identifier


def build_graph(snapshot: GraphSnapshot, *, entity_id: UUID | None = None) -> InvestigationGraph:
    if entity_id is not None and not isinstance(entity_id, UUID):
        raise ValueError("graph_configuration")
    try:
        return _build(snapshot, entity_id)
    except AssessmentError:
        raise GraphError("graph_limit") from None
    except (KeyError, TypeError, ValueError, AttributeError):
        raise GraphError("graph_state") from None


def _build(snapshot: GraphSnapshot, entity_id: UUID | None) -> InvestigationGraph:
    review = snapshot.review
    cohort = review.report.cohort
    if (
        len(review.heads) > MAX_OCCURRENCES
        or len(cohort.parties) > MAX_OCCURRENCES
        or len(snapshot.contracts) > MAX_OCCURRENCES
        or len(review.events) > MAX_REVIEW_EVENTS
        or len(
            {(r.claim.import_id, r.claim.registry_number) for r in cohort.registry}
            | {
                (a.evidence.claim.import_id, a.evidence.claim.registry_number)
                for a in review.entities
            }
        )
        > MAX_REGISTRY_OBSERVATIONS
    ):
        raise GraphError("graph_limit")
    parties = {(p.observation_id, p.role, p.ordinal): p for p in cohort.parties}
    heads = {(h.subject.observation_id, h.subject.role, h.subject.ordinal): h for h in review.heads}
    contracts = {f.key: f for f in snapshot.contracts}
    anchors = {a.entity_id: a for a in review.entities}
    events = {e.event.event_id: e.event for e in review.events}
    if (
        set(parties) != set(heads)
        or len(parties) != len(cohort.parties)
        or len(heads) != len(review.heads)
        or len(contracts) != len(snapshot.contracts)
        or len(anchors) != len(review.entities)
        or len(events) != len(review.events)
    ):
        raise GraphError("graph_state")
    required = {
        ContractKey(
            h.subject.projection_version,
            h.subject.source_id,
            h.subject.normalizer_version,
            h.subject.content_sha256,
        )
        for h in review.heads
    }
    if set(contracts) != required:
        raise GraphError("graph_state")
    resolution = build_resolution(review)
    graph = _Graph()
    selected_suppliers = Counter(
        ContractKey(cohort.projection_version, p.source_id, p.normalizer_version, p.content_sha256)
        for p in cohort.parties
        if p.role == "supplier"
    )
    contract_nodes = {}
    for key, fact in contracts.items():
        values = asdict(fact)
        del values["key"]
        values["net_amount"] = str(fact.net_amount) if fact.net_amount is not None else None
        values["gross_amount"] = str(fact.gross_amount) if fact.gross_amount is not None else None
        values["selected_supplier_occurrence_count"] = selected_suppliers[key]
        contract_nodes[key] = graph.node("contract_version", asdict(key), values)
    handle_nodes: dict[UUID, tuple[str, str]] = {}
    registry_support: set[str] = set()
    for entity, anchor in anchors.items():
        row = anchor.evidence
        registry_key: dict[str, object] = {
            "import_id": str(row.claim.import_id),
            "registry_number": row.claim.registry_number,
        }
        registry_node = graph.node(
            "registry_observation",
            registry_key,
            {
                "outcome": row.claim.outcome,
                "attempt": row.attempt,
                "status": row.status,
                "raw_sha256": row.raw_sha256,
                "observed_at": row.observed_at,
                "source_id": row.source_id,
                "normalizer_version": row.normalizer_version,
                "fields": {name: asdict(value) for name, value in row.fields.items()},
            },
        )
        # Shared exact anchors/evidence are one node and one source assertion.
        if registry_node not in registry_support:
            graph.edge(
                "supported_by",
                registry_node,
                graph.evidence(row.raw_sha256),
                registry_key,
                {
                    "raw_sha256": row.raw_sha256,
                    "json_pointer": "",
                    "observed_at": row.observed_at,
                    "locator_granularity": "response",
                },
            )
            registry_support.add(registry_node)
        handle = graph.node(
            "entity_handle",
            {"entity_id": str(entity)},
            {"entity_kind": "unclassified", "creating_event_id": str(anchor.creating_event_id)},
            identity=str(entity),
        )
        graph.edge(
            "anchored_to",
            handle,
            registry_node,
            {"entity_id": str(entity), "creating_event_id": str(anchor.creating_event_id)},
            {"legal_valid_from": None, "legal_valid_to": None},
        )
        handle_nodes[entity] = handle, registry_node
    links: dict[UUID, list[FocusOccurrence]] = defaultdict(list)
    buyers: dict[str, list[str]] = defaultdict(list)
    for head, resolved in zip(review.heads, resolution["occurrences"], strict=True):
        subject = head.subject
        party = parties[(subject.observation_id, subject.role, subject.ordinal)]
        key = ContractKey(
            subject.projection_version,
            subject.source_id,
            subject.normalizer_version,
            subject.content_sha256,
        )
        if (
            subject.run_id != cohort.run_id
            or subject.projection_version != cohort.projection_version
            or (party.source_id, party.normalizer_version, party.content_sha256)
            != (subject.source_id, subject.normalizer_version, subject.content_sha256)
        ):
            raise GraphError("graph_state")
        source = graph.node(
            "party_occurrence",
            subject.payload(),
            {
                **asdict(party),
                "subject_revision": head.revision,
                "review_status": resolved["review_status"],
                "latest_event_id": resolved["latest_event_id"],
            },
        )
        contract = contract_nodes[key]
        location: dict[str, object] = {
            "raw_sha256": party.raw_sha256,
            "json_pointer": party.json_pointer,
            "observed_at": party.observed_at,
            "locator_granularity": "record",
        }
        graph.edge(
            "reported_" + subject.role + "_in",
            source,
            contract,
            subject.payload(),
            {
                **location,
                "role": subject.role,
                "ordinal": subject.ordinal,
                "legal_valid_from": None,
                "legal_valid_to": None,
            },
        )
        graph.edge(
            "supported_by", source, graph.evidence(party.raw_sha256), subject.payload(), location
        )
        if subject.role == "buyer":
            buyers[contract].append(source)
        accepted = [p for p in head.pairs if p.state == "accepted"]
        if len(accepted) > 1:
            raise GraphError("graph_state")
        for pair in accepted:
            if pair.entity_id is None or pair.event_id is None:
                raise GraphError("graph_state")
            event = events[pair.event_id]
            if (
                event.request.operation != "accept"
                or event.request.subject != subject
                or event.request.candidate != pair.candidate
                or event.request.entity_id != pair.entity_id
                or event.subject_revision > head.revision
            ):
                raise GraphError("graph_state")
            assertion = {
                "subject": subject.payload(),
                "subject_revision": head.revision,
                "acceptance_event_id": str(pair.event_id),
                "candidate": pair.candidate.payload(),
            }
            edge = graph.edge(
                "reviewed_as",
                source,
                handle_nodes[pair.entity_id][0],
                assertion,
                {
                    "review_policy_version": event.policy_version,
                    "legal_valid_from": None,
                    "legal_valid_to": None,
                },
            )
            links[pair.entity_id].append(
                {
                    "occurrence_id": source,
                    "contract_version_id": contract,
                    "reviewed_as_edge_id": edge,
                    "subject_revision": head.revision,
                    "acceptance_event_id": str(pair.event_id),
                    "candidate": pair.candidate.payload(),
                }
            )
    if any(
        e["source"] not in graph.nodes or e["target"] not in graph.nodes
        for e in graph.edges.values()
    ):
        raise GraphError("graph_state")
    focus = _focus(entity_id, graph, handle_nodes, links, buyers)
    return {
        "graph_format": "nima-investigation-graph-v1",
        "graph_policy_version": "investigation-graph-v1",
        "comparison_report_sha256": review.report.sha256,
        "projection_version": cohort.projection_version,
        "reviewed_resolution_sha256": _hash(resolution),
        "reviewed_resolution": resolution,
        "coverage_assurance": "unverified_report_context",
        "attribution_assurance": "database_principal_only",
        "archive_integrity": "not_checked",
        "automatic_identity_links": 0,
        "reviewed_accepted_links": resolution["reviewed_accepted_links"],
        "nodes": sorted(graph.nodes.values(), key=lambda n: n["id"]),
        "edges": sorted(graph.edges.values(), key=lambda e: e["id"]),
        "focus": focus,
    }


def _focus(
    entity_id: UUID | None,
    graph: _Graph,
    handles: dict[UUID, tuple[str, str]],
    links: dict[UUID, list[FocusOccurrence]],
    buyers: dict[str, list[str]],
) -> Focus:
    focus: Focus = {
        "state": "omitted",
        "entity_id": str(entity_id) if entity_id is not None else None,
        "entity_handle_id": None,
        "anchor_observation_id": None,
        "active_occurrences": [],
        "contracts": [],
    }
    if entity_id is None:
        return focus
    if entity_id not in handles:
        focus["state"] = "not_in_selected_history"
        return focus
    focus["entity_handle_id"], focus["anchor_observation_id"] = handles[entity_id]
    selected = sorted(links.get(entity_id, []), key=lambda link: link["occurrence_id"])
    focus["state"] = "active_links" if selected else "no_active_links"
    focus["active_occurrences"] = selected
    focus["contracts"] = [
        {
            "contract_version_id": key,
            "facts": graph.nodes[key]["data"],
            "buyer_selection": "selected" if buyers.get(key) else "not_selected",
            "buyer_occurrence_ids": sorted(buyers.get(key, [])),
        }
        for key in sorted({link["contract_version_id"] for link in selected})
    ]
    return focus
