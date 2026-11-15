"""Independent graph keys/sets and evidence semantics from complete typed inputs."""

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType
from typing import cast
from uuid import UUID

import pytest

from nima.graph import GraphError, build
from nima.graph.snapshot import ContractFacts, ContractKey, GraphSnapshot
from nima.identity.artifacts import encode
from nima.identity.review_export import build_resolution
from nima.identity.review_snapshot import EntityAnchor, RecordedEvent
from nima.identity.review_state import fold_events
from nima.identity.review_types import ReviewCandidate, ReviewEvent, ReviewRequest
from tests.test_identity_review_evidence import report as comparison_report
from tests.test_identity_review_export import unreviewed
from tests.test_identity_review_reversal import revoke


def identifier(kind: str, key: object) -> str:
    body = json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"nima:graph:v1:{kind}:" + hashlib.sha256(body).hexdigest()


def inputs() -> GraphSnapshot:
    review = unreviewed()
    party = review.report.cohort.parties[0]
    fact = ContractFacts(
        ContractKey(
            review.report.cohort.projection_version,
            party.source_id,
            party.normalizer_version,
            party.content_sha256,
        ),
        "d" * 64,
        " Σύμβαση ",
        Decimal("0.100000000000000001"),
        None,
        None,
        None,
        None,
        party.source_submitted_at,
        party.source_updated_at,
        2,
    )
    return GraphSnapshot(review, (fact,))


def reviewed(*, reversed_link: bool = False) -> GraphSnapshot:
    data = inputs()
    original = data.review
    subject = original.heads[1].subject
    registry = original.report.cohort.registry[0]
    chosen = ReviewRequest(
        UUID(int=100),
        "accept",
        subject,
        ReviewCandidate(registry.claim.import_id, registry.claim.registry_number),
        0,
        " Ερευνητική κρίση ",
        original.report.sha256,
        UUID(int=200),
    )
    events = [ReviewEvent(chosen, 1)]
    if reversed_link:
        events.append(ReviewEvent(replace(revoke(chosen, 1), request_id=UUID(int=101)), 2))
    return replace(
        data,
        review=replace(
            original,
            heads=(original.heads[0], fold_events(subject, events)),
            events=tuple(
                RecordedEvent(
                    e, "local_operator", "2026-11-15T10:00:00+00:00", MappingProxyType({})
                )
                for e in events
            ),
            entities=(EntityAnchor(UUID(int=200), chosen.request_id, registry),),
        ),
    )


def test_exact_unresolved_graph_sets_keep_repeated_observations_and_shared_version() -> None:
    data = inputs()
    actual = build.build_graph(data)
    contract_key = {
        "projection_version": data.contracts[0].key.projection_version,
        "source_id": "kimdis:1",
        "normalizer_version": "kimdis-normalized-v1",
        "content_sha256": "b" * 64,
    }
    contract = identifier("contract_version", contract_key)
    evidence = "nima:graph:v1:evidence_object:" + "c" * 64
    occurrences = {
        identifier("party_occurrence", head.subject.payload()): head.subject.payload()
        for head in data.review.heads
    }
    assert {node["id"] for node in actual["nodes"]} == {contract, evidence, *occurrences}
    expected_edges = set()
    for occurrence, subject in occurrences.items():
        for kind, target in (("reported_supplier_in", contract), ("supported_by", evidence)):
            expected_edges.add(
                identifier(
                    "edge:" + kind,
                    {
                        "kind": kind,
                        "source": occurrence,
                        "target": target,
                        "assertion_key": subject,
                    },
                )
            )
    assert {edge["id"] for edge in actual["edges"]} == expected_edges
    assert {edge["kind"] for edge in actual["edges"]} == {"reported_supplier_in", "supported_by"}
    assert all(node["kind"] != "entity_handle" for node in actual["nodes"])
    assert actual["reviewed_accepted_links"] == actual["automatic_identity_links"] == 0
    assert actual["focus"]["state"] == "omitted"


def test_canonical_embedded_resolution_exact_money_and_original_source_dates() -> None:
    data = inputs()
    actual = build.build_graph(data)
    resolution = build_resolution(data.review)
    assert actual["reviewed_resolution"] == resolution
    assert actual["reviewed_resolution_sha256"] == hashlib.sha256(encode(resolution)).hexdigest()
    assert actual["graph_format"] == "nima-investigation-graph-v1"
    assert actual["graph_policy_version"] == "investigation-graph-v1"
    assert actual["comparison_report_sha256"] == data.review.report.sha256
    assert actual["archive_integrity"] == "not_checked"
    assert actual["coverage_assurance"] == "unverified_report_context"
    assert actual["attribution_assurance"] == "database_principal_only"
    fact = next(n["data"] for n in actual["nodes"] if n["kind"] == "contract_version")
    assert fact["net_amount"] == "0.100000000000000001"
    assert fact["gross_amount"] is None and fact["currency"] is None
    assert fact["source_submitted_at"] == "2020-01-01"
    assert fact["source_updated_at"] is None and fact["supplier_count"] == 2
    assert all("amount" not in key for edge in actual["edges"] for key in edge["data"])
    assert "generated_at" not in actual and "spend_total" not in actual
    assert encode(actual) == encode(build.build_graph(data))
    assert [n["id"] for n in actual["nodes"]] == sorted(n["id"] for n in actual["nodes"])
    assert [e["id"] for e in actual["edges"]] == sorted(e["id"] for e in actual["edges"])


def test_reviewed_edges_have_exact_events_anchor_fields_and_original_locators() -> None:
    data = reviewed()
    actual = build.build_graph(data)
    nodes = {n["id"]: n for n in actual["nodes"]}
    assert len(nodes) == len(actual["nodes"]) == 7 and len(actual["edges"]) == 7
    assert all(e["source"] in nodes and e["target"] in nodes for e in actual["edges"])
    link = next(e for e in actual["edges"] if e["kind"] == "reviewed_as")
    assert link["target"] == "nima:graph:v1:entity_handle:" + str(UUID(int=200))
    assert link["assertion_key"]["acceptance_event_id"] == str(UUID(int=100))
    assert link["assertion_key"]["subject_revision"] == 1
    registry = next(n for n in actual["nodes"] if n["kind"] == "registry_observation")
    fields = cast(dict[str, dict[str, object]], registry["data"]["fields"])
    assert fields["reported_afm"]["json_pointer"] == "/afm"
    supports = [e for e in actual["edges"] if e["kind"] == "supported_by"]
    assert {e["data"]["json_pointer"] for e in supports} == {"", "/content/0"}
    assert all(e["data"]["observed_at"] for e in supports)
    handle = nodes[link["target"]]
    assert handle["data"]["entity_kind"] == "unclassified"


@pytest.mark.parametrize("part", ["contracts", "heads", "entities"])
def test_duplicate_complete_input_keys_fail_closed(part: str) -> None:
    data = reviewed()
    if part == "contracts":
        data = replace(data, contracts=data.contracts * 2)
    else:
        data = replace(data, review=replace(data.review, **{part: getattr(data.review, part) * 2}))
    with pytest.raises(GraphError, match="^graph_state$"):
        build.build_graph(data)


def test_missing_contract_and_active_anchor_are_rejected() -> None:
    for data in (
        replace(inputs(), contracts=()),
        replace(reviewed(), review=replace(reviewed().review, entities=())),
    ):
        with pytest.raises(GraphError, match="^graph_state$"):
            build.build_graph(data)


def test_composite_id_collision_and_exact_node_edge_budgets_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = inputs()
    actual = build.build_graph(data)
    with monkeypatch.context() as patch:
        patch.setattr(build, "_hash", lambda value: "0" * 64)
        with pytest.raises(GraphError, match="^graph_state$"):
            build.build_graph(data)
    monkeypatch.setattr(build, "MAX_NODES", len(actual["nodes"]))
    monkeypatch.setattr(build, "MAX_EDGES", len(actual["edges"]))
    assert build.build_graph(data) == actual
    monkeypatch.setattr(build, "MAX_NODES", len(actual["nodes"]) - 1)
    with pytest.raises(GraphError, match="^graph_limit$"):
        build.build_graph(data)
    monkeypatch.setattr(build, "MAX_NODES", 600)
    monkeypatch.setattr(build, "MAX_EDGES", len(actual["edges"]) - 1)
    with pytest.raises(GraphError, match="^graph_limit$"):
        build.build_graph(data)


def test_changed_versions_remain_distinct_and_source_dates_are_not_validity_intervals() -> None:
    data = inputs()
    review = data.review
    second = review.heads[1].subject
    changed = replace(second, content_sha256="e" * 64)
    parties = tuple(
        replace(p, content_sha256="e" * 64, source_updated_at="not-a-date")
        if p.observation_id == second.observation_id
        else p
        for p in review.report.cohort.parties
    )
    parsed = comparison_report(replace(review.report.cohort, parties=parties))
    later = replace(
        data.contracts[0],
        key=replace(data.contracts[0].key, content_sha256="e" * 64),
        source_updated_at="not-a-date",
    )
    data = replace(
        data,
        contracts=(*data.contracts, later),
        review=replace(
            review,
            report=parsed,
            heads=(review.heads[0], fold_events(changed, ())),
        ),
    )
    actual = build.build_graph(data)
    contracts = [n for n in actual["nodes"] if n["kind"] == "contract_version"]
    assert len(contracts) == 2 and contracts[0]["id"] != contracts[1]["id"]
    assert {n["data"]["source_updated_at"] for n in contracts} == {None, "not-a-date"}
    assert all(e["kind"] != "supersedes" for e in actual["edges"])
    assert all(
        e["data"]["legal_valid_from"] is None
        for e in actual["edges"]
        if e["kind"] == "reported_supplier_in"
    )
    assert build.build_graph(replace(data, contracts=tuple(reversed(data.contracts)))) == actual


def test_rejection_does_not_create_handle_or_remove_unresolved_members() -> None:
    data = reviewed()
    recorded = data.review.events[0]
    event = replace(
        recorded.event, request=replace(recorded.event.request, operation="reject", entity_id=None)
    )
    data = replace(
        data,
        review=replace(
            data.review,
            entities=(),
            events=(replace(recorded, event=event),),
            heads=(data.review.heads[0], fold_events(event.request.subject, (event,))),
        ),
    )
    actual = build.build_graph(data)
    assert len(actual["nodes"]) == 4 and len(actual["edges"]) == 4
    assert actual["reviewed_accepted_links"] == 0
    assert actual["reviewed_resolution"]["occurrences"][1]["review_status"] == "unresolved"


def test_selected_supplier_occurrences_do_not_replace_source_reported_supplier_count() -> None:
    data = inputs()
    review = data.review
    selected_party = review.report.cohort.parties[0]
    parsed = comparison_report(replace(review.report.cohort, parties=(selected_party,)))
    selected = replace(data, review=replace(review, report=parsed, heads=(review.heads[0],)))
    actual = build.build_graph(selected)
    contract = next(n for n in actual["nodes"] if n["kind"] == "contract_version")
    assert contract["data"]["supplier_count"] == 2
    assert contract["data"]["selected_supplier_occurrence_count"] == 1
    assert len([n for n in actual["nodes"] if n["kind"] == "party_occurrence"]) == 1


def test_outside_catalog_anchor_retains_exact_key_without_expanding_report_catalog() -> None:
    data = reviewed()
    anchor = data.review.entities[0]
    outside = replace(anchor.evidence, claim=replace(anchor.evidence.claim, import_id=UUID(int=99)))
    data = replace(
        data,
        review=replace(
            data.review,
            entities=(replace(anchor, creating_event_id=UUID(int=999), evidence=outside),),
        ),
    )
    actual = build.build_graph(data)
    registry = [n for n in actual["nodes"] if n["kind"] == "registry_observation"]
    assert [n["key"] for n in registry] == [
        {"import_id": str(UUID(int=99)), "registry_number": "1"}
    ]
    catalog = actual["reviewed_resolution"]["comparison_report"]["registry_observations"]
    assert len(cast(list[object], catalog)) == 3


def test_empty_selected_graph_retains_embedded_catalog_and_bounds_still_apply() -> None:
    data = inputs()
    parsed = comparison_report(replace(data.review.report.cohort, parties=()))
    empty = replace(data, contracts=(), review=replace(data.review, report=parsed, heads=()))
    actual = build.build_graph(empty)
    assert actual["nodes"] == [] and actual["edges"] == []
    assert actual["reviewed_resolution"]["comparison_report"]["registry_observations"]
    oversized = replace(data, review=replace(data.review, heads=(data.review.heads[0],) * 101))
    with pytest.raises(GraphError, match="^graph_limit$"):
        build.build_graph(oversized)
