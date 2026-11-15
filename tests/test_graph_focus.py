"""Focus stays inside selected history and keeps reviewed, reported and unknown distinct."""

from dataclasses import replace
from typing import cast
from uuid import UUID

import pytest

from nima.graph import build
from nima.identity.review_snapshot import EntityAnchor
from nima.identity.review_state import fold_events
from nima.identity.review_types import ReviewEvent
from tests.test_graph_build import inputs, reviewed


@pytest.mark.parametrize("value", ["private-sentinel", True, 1])
def test_invalid_focus_configuration_fails_with_fixed_reason(value: object) -> None:
    with pytest.raises(ValueError, match="^graph_configuration$"):
        build.build_graph(inputs(), entity_id=cast(UUID, value))


def test_focus_distinguishes_omitted_active_historical_and_unselected_handles() -> None:
    assert build.build_graph(inputs())["focus"]["state"] == "omitted"
    active = build.build_graph(reviewed(), entity_id=UUID(int=200))
    focus = active["focus"]
    assert focus["state"] == "active_links" and len(focus["active_occurrences"]) == 1
    assert len(focus["contracts"]) == 1
    contract = focus["contracts"][0]
    assert contract["buyer_selection"] == "not_selected"
    assert contract["buyer_occurrence_ids"] == []
    assert contract["facts"]["net_amount"] == "0.100000000000000001"
    assert focus["anchor_observation_id"] is not None
    historical = build.build_graph(reviewed(reversed_link=True), entity_id=UUID(int=200))
    assert historical["focus"]["state"] == "no_active_links"
    assert historical["focus"]["active_occurrences"] == []
    assert historical["focus"]["contracts"] == []
    assert historical["focus"]["anchor_observation_id"] == focus["anchor_observation_id"]
    assert not any(e["kind"] == "reviewed_as" for e in historical["edges"])
    assert any(n["kind"] == "entity_handle" for n in historical["nodes"])
    unknown = build.build_graph(reviewed(), entity_id=UUID(int=999))
    assert unknown["focus"]["state"] == "not_in_selected_history"
    assert unknown["focus"]["entity_handle_id"] is None
    assert unknown["focus"]["anchor_observation_id"] is None
    assert active["nodes"] == unknown["nodes"] and active["edges"] == unknown["edges"]


def test_selected_buyer_is_an_occurrence_without_legal_class_or_key_consolidation() -> None:
    data = reviewed()
    review = data.review
    first = review.heads[0]
    buyer = replace(first.subject, role="buyer")
    parties = tuple(
        replace(p, role="buyer") if p.observation_id == buyer.observation_id else p
        for p in review.report.cohort.parties
    )
    data = replace(
        data,
        review=replace(
            review,
            report=replace(review.report, cohort=replace(review.report.cohort, parties=parties)),
            heads=(fold_events(buyer, ()), review.heads[1]),
        ),
    )
    actual = build.build_graph(data, entity_id=UUID(int=200))
    selected = actual["focus"]["contracts"][0]
    assert selected["buyer_selection"] == "selected" and len(selected["buyer_occurrence_ids"]) == 1
    assert any(e["kind"] == "reported_buyer_in" for e in actual["edges"])
    assert not any(n["kind"] == "public_body" for n in actual["nodes"])


def test_acceptance_event_is_distinct_from_latest_review_event() -> None:
    data = reviewed()
    review = data.review
    acceptance = review.events[0].event
    rejection = ReviewEvent(
        replace(
            acceptance.request,
            request_id=UUID(int=102),
            operation="reject",
            expected_revision=1,
            entity_id=None,
            candidate=replace(acceptance.request.candidate, import_id=UUID(int=2)),
        ),
        2,
    )
    data = replace(
        data,
        review=replace(
            review,
            heads=(
                review.heads[0],
                fold_events(acceptance.request.subject, (acceptance, rejection)),
            ),
            events=(*review.events, replace(review.events[0], event=rejection)),
        ),
    )
    actual = build.build_graph(data, entity_id=UUID(int=200))
    link = actual["focus"]["active_occurrences"][0]
    assert link["subject_revision"] == 2
    assert link["acceptance_event_id"] == str(UUID(int=100))
    assert actual["reviewed_resolution"]["occurrences"][1]["latest_event_id"] == str(UUID(int=102))


def test_reassignment_preserves_duplicate_handles_without_duplicate_anchor_assertions() -> None:
    data = reviewed(reversed_link=True)
    review = data.review
    acceptance = review.events[0].event
    newer = ReviewEvent(
        replace(
            acceptance.request,
            request_id=UUID(int=102),
            expected_revision=2,
            entity_id=UUID(int=201),
        ),
        3,
    )
    data = replace(
        data,
        review=replace(
            review,
            heads=(
                review.heads[0],
                fold_events(
                    acceptance.request.subject, (*tuple(r.event for r in review.events), newer)
                ),
            ),
            events=(*review.events, replace(review.events[0], event=newer)),
            entities=(
                *review.entities,
                EntityAnchor(UUID(int=201), UUID(int=102), review.entities[0].evidence),
            ),
        ),
    )
    actual = build.build_graph(data, entity_id=UUID(int=201))
    assert actual["focus"]["state"] == "active_links"
    assert len([n for n in actual["nodes"] if n["kind"] == "entity_handle"]) == 2
    assert len([n for n in actual["nodes"] if n["kind"] == "registry_observation"]) == 1
    assert len([e for e in actual["edges"] if e["kind"] == "anchored_to"]) == 2
    assert len([e for e in actual["edges"] if e["kind"] == "supported_by"]) == 3
    assert actual["reviewed_resolution"]["selected_handle_ambiguities"] == [
        {
            "registry_number": "1",
            "entity_ids": [str(UUID(int=200)), str(UUID(int=201))],
        }
    ]
    assert build.build_graph(data, entity_id=UUID(int=200))["focus"]["state"] == "no_active_links"
