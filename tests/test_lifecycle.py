"""Lifecycle references (M4): explicit edges between captured records, never inferred chains.

A reference records that one record *cites* another; it does not say the cited record is
superseded. Targets are `resolved` only when observed in the cohort. On real data most award and
payment targets are other procurement stages that this feed does not collect, so `unresolved` is
expected and not a defect.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from nima.semantics.lifecycle import (
    Cited,
    LifecycleResult,
    Reference,
    definition,
    definition_sha256,
    evaluate,
)
from nima.semantics.participation import SemanticError

CUTOFF = datetime(2026, 1, 10, tzinfo=UTC)


def day(number: int) -> datetime:
    return datetime(2026, 1, number, tzinfo=UTC)


def award(target: str) -> Reference:
    return Reference("award", f"kimdis:{target}", "auctionRefNo")


def previous(target: str) -> Reference:
    return Reference("previous_record", f"kimdis:{target}", "prevReferenceNo")


def payment(target: str) -> Reference:
    return Reference("payment_order", f"kimdis:{target}", "paymentRefNo")


def decision(target: str) -> Reference:
    return Reference("commitment_decision", f"diavgeia:{target}", "diavgeiaADA")


def cite(
    observation_id: int,
    record: str,
    version: str,
    observed: datetime,
    references: tuple[Reference, ...] | None,
) -> Cited:
    return Cited(
        observation_id,
        f"kimdis:{record}",
        hashlib.sha256(version.encode()).hexdigest(),
        observed,
        references,
    )


def run(rows: tuple[Cited, ...], **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("cutoff", CUTOFF)
    return cast(dict[str, Any], evaluate(rows, **kwargs).payload())


def edge(payload: dict[str, Any], source: str, relation: str, target: str) -> dict[str, Any]:
    matches = [
        e
        for e in payload["edges"]
        if e["source_id"] == f"kimdis:{source}"
        and e["relation"] == relation
        and target in e["target_id"]
    ]
    assert len(matches) == 1, (source, relation, target)
    return cast(dict[str, Any], matches[0])


def example() -> tuple[Cited, ...]:
    return (
        cite(1, "A", "a", day(1), (previous("B"), award("X"), decision("Z"))),
        cite(2, "B", "b", day(1), ()),
        cite(3, "C", "c", day(1), (payment("P"),)),
        cite(4, "D", "d", day(1), (previous("D"),)),
        cite(5, "E", "e1", day(1), ()),
        cite(6, "E", "e2", day(1), ()),
        cite(7, "F", "f", day(1), (previous("E"),)),
        cite(8, "G", "g", day(1), (previous("H"),)),
        cite(9, "H", "h", day(11), ()),
    )


def test_each_kind_of_edge_gets_its_own_status() -> None:
    payload = run(example())
    assert edge(payload, "A", "previous_record", "B")["status"] == "resolved"
    assert edge(payload, "A", "award", "X")["status"] == "unresolved"
    assert edge(payload, "A", "commitment_decision", "Z")["status"] == "external"
    assert edge(payload, "C", "payment_order", "P")["status"] == "unresolved"
    assert edge(payload, "D", "previous_record", "D")["status"] == "self_reference"
    assert edge(payload, "F", "previous_record", "E")["status"] == "target_ambiguous"
    assert edge(payload, "G", "previous_record", "H")["status"] == "unresolved"


def test_a_target_observed_only_after_the_cutoff_is_unresolved_until_it_is_in_the_cohort() -> None:
    assert edge(run(example()), "G", "previous_record", "H")["status"] == "unresolved"
    later = run(example(), cutoff=day(12))
    assert edge(later, "G", "previous_record", "H")["status"] == "resolved"


def test_relations_are_summarised_with_counts_in_relation_order() -> None:
    payload = run(example())
    by_relation = {row["relation"]: row for row in payload["relations"]}
    assert [row["relation"] for row in payload["relations"]] == [
        "award",
        "commitment_decision",
        "payment_order",
        "previous_record",
    ]
    assert by_relation["previous_record"] == {
        "relation": "previous_record",
        "references": 4,
        "distinct_targets": 4,
        "resolved": 1,
        "unresolved": 1,
        "external": 0,
        "target_ambiguous": 1,
        "self_reference": 1,
        "max_citing_records": 1,
    }
    assert by_relation["commitment_decision"]["external"] == 1
    assert by_relation["award"]["unresolved"] == 1


def test_an_ambiguous_record_is_excluded_listed_and_its_own_references_are_unknown() -> None:
    rows = (
        cite(1, "E", "e1", day(1), (award("X"),)),
        cite(2, "E", "e2", day(1), (award("Y"),)),
    )
    payload = run(rows)
    assert payload["ambiguous_source_ids"] == ["kimdis:E"] and payload["edges"] == []
    assert payload["status"] == "no_references"


def test_the_latest_observed_version_decides_the_references_and_a_b_a_reuses_the_last() -> None:
    rows = (
        cite(1, "A", "v1", day(1), (award("X"),)),
        cite(2, "A", "v2", day(2), (award("Y"),)),
    )
    assert [e["target_id"] for e in run(rows)["edges"]] == ["kimdis:Y"]
    assert [e["target_id"] for e in run(rows, cutoff=day(1))["edges"]] == ["kimdis:X"]
    aba = (*rows, cite(3, "A", "v1", day(3), (award("X"),)))
    payload = run(aba)
    assert [e["target_id"] for e in payload["edges"]] == ["kimdis:X"]
    assert payload["edges"][0]["observation_ids"] == [3]


def test_repeated_observation_of_one_version_gives_one_edge_and_keeps_both_observations() -> None:
    rows = (cite(1, "A", "v", day(1), (award("X"),)), cite(2, "A", "v", day(2), (award("X"),)))
    payload = run(rows)
    assert len(payload["edges"]) == 1 and payload["edges"][0]["observation_ids"] == [2]


def test_duplicate_references_inside_one_record_collapse_to_one_edge() -> None:
    payload = run((cite(1, "A", "a", day(1), (award("X"), award("X"), payment("X"))),))
    assert [e["relation"] for e in payload["edges"]] == ["award", "payment_order"]
    assert payload["relations"][0]["references"] == 1


def test_unknown_and_empty_reference_lists_are_different() -> None:
    rows = (cite(1, "U", "u", day(1), None), cite(2, "E", "e", day(1), ()))
    payload = run(rows)
    assert payload["unknown_reference_source_ids"] == ["kimdis:U"]
    assert payload["edges"] == [] and payload["status"] == "no_references"


def test_shared_targets_are_disclosed_and_an_umbrella_needs_more_citers_than_the_threshold() -> (
    None
):
    rows = tuple(cite(i, f"R{i}", f"r{i}", day(1), (award("X"),)) for i in (1, 2, 3))
    rows = (*rows, cite(4, "R4", "r4", day(1), (award("Y"),)))
    none = run(rows)
    assert none["umbrella_threshold"] is None and none["umbrella_targets"] == []
    assert none["shared_targets"] == [
        {
            "relation": "award",
            "target_id": "kimdis:X",
            "citing_records": 3,
            "source_ids": ["kimdis:R1", "kimdis:R2", "kimdis:R3"],
        }
    ]
    assert none["relations"][0]["max_citing_records"] == 3
    assert none["relations"][0]["references"] == 4
    assert none["relations"][0]["distinct_targets"] == 2
    assert not any(e["umbrella"] for e in none["edges"])
    exactly = run(rows, umbrella_threshold=3)
    assert exactly["umbrella_targets"] == [] and not any(e["umbrella"] for e in exactly["edges"])
    over = run(rows, umbrella_threshold=2)
    assert over["umbrella_targets"] == [
        {"relation": "award", "target_id": "kimdis:X", "citing_records": 3}
    ]
    assert [e["umbrella"] for e in over["edges"]] == [True, True, True, False]


def test_a_target_cited_by_exactly_two_records_is_shared() -> None:
    rows = (
        cite(1, "A", "a", day(1), (award("X"),)),
        cite(2, "B", "b", day(1), (award("X"),)),
    )
    shared = run(rows)["shared_targets"]
    assert [(s["target_id"], s["citing_records"]) for s in shared] == [("kimdis:X", 2)]


def test_edge_observation_ids_are_ascending_whatever_the_input_order() -> None:
    rows = (
        cite(9, "A", "v", day(1), (award("X"),)),
        cite(3, "A", "v", day(1), (award("X"),)),
        cite(5, "A", "v", day(1), (award("X"),)),
    )
    assert run(rows)["edges"][0]["observation_ids"] == [3, 5, 9]


def test_the_same_target_under_two_relations_is_counted_separately() -> None:
    rows = (
        cite(1, "A", "a", day(1), (award("X"),)),
        cite(2, "B", "b", day(1), (payment("X"),)),
    )
    assert run(rows)["shared_targets"] == []


def test_a_cited_record_is_not_removed_or_changed_by_being_cited() -> None:
    payload = run(example())
    assert edge(payload, "A", "previous_record", "B")["status"] == "resolved"
    assert "kimdis:B" not in payload["ambiguous_source_ids"]
    # A, B, C, D, F and G are selected; E is ambiguous and H is observed after the cutoff.
    assert payload["records"] == 6


def test_the_statuses_of_an_empty_or_early_capture_and_one_without_references() -> None:
    assert run(())["status"] == "empty_capture"
    assert run(example(), cutoff=datetime(2025, 12, 31, tzinfo=UTC))["status"] == (
        "no_observations_before_cutoff"
    )
    assert run((cite(1, "A", "a", day(1), ()),))["status"] == "no_references"
    assert run(example())["status"] == "observed_references"


def test_the_order_of_the_observations_does_not_change_the_result() -> None:
    rows = example()
    assert run(tuple(reversed(rows))) == run(rows)


def test_edges_are_ordered_by_source_relation_and_target_bytewise() -> None:
    rows = (
        cite(1, "b", "b", day(1), (award("2"), award("1"))),
        cite(2, "B", "b2", day(1), (payment("9"), award("1"))),
    )
    keys = [(e["source_id"], e["relation"], e["target_id"]) for e in run(rows)["edges"]]
    assert keys == sorted(keys)


@pytest.mark.parametrize(
    "bad",
    [
        Reference("award", "kimdis:X", "prevReferenceNo"),
        Reference("previous_record", "kimdis:X", "auctionRefNo"),
        Reference("unknown", "kimdis:X", "auctionRefNo"),
        Reference("award", "X", "auctionRefNo"),
        Reference("award", "kimdis:", "auctionRefNo"),
        Reference("award", "kimdis:   ", "auctionRefNo"),
        Reference("award", ":X", "auctionRefNo"),
        Reference("award", "Kimdis:X", "auctionRefNo"),
        Reference(cast(str, 5), "kimdis:X", "auctionRefNo"),
        Reference("award", cast(str, None), "auctionRefNo"),
        Reference("award", "kimdis:X", cast(str, None)),
    ],
)
def test_a_malformed_reference_is_refused_with_a_fixed_reason(bad: Reference) -> None:
    with pytest.raises(SemanticError, match="^semantic_input$"):
        run((cite(1, "A", "a", day(1), (bad,)),))


@pytest.mark.parametrize(
    "change",
    [
        {"observation_id": 0},
        {"observation_id": True},
        {"source_id": "gemi:1"},
        {"source_id": "kimdis:"},
        {"source_id": "kimdis:  "},
        {"content_sha256": "xyz"},
        {"content_sha256": "A" * 64},
        {"observed_at": datetime(2026, 1, 1)},
        {"references": [award("X")]},
        {"references": ("x",)},
    ],
)
def test_a_malformed_observation_is_refused_with_a_fixed_reason(change: dict[str, Any]) -> None:
    row = replace(cite(1, "A", "a", day(1), ()), **change)
    with pytest.raises(SemanticError, match="^semantic_input$"):
        run((row,))


def test_duplicate_observation_ids_and_conflicting_versions_are_refused() -> None:
    row = cite(1, "A", "a", day(1), (award("X"),))
    with pytest.raises(SemanticError, match="^semantic_input$"):
        run((row, row))
    other = replace(row, observation_id=2, references=(award("Y"),))
    with pytest.raises(SemanticError, match="^semantic_version_conflict$"):
        run((row, other))


def test_the_bounds_are_exact() -> None:
    row = cite(1, "A", "a", day(1), ())
    exactly = tuple(
        replace(row, observation_id=i + 1, source_id=f"kimdis:R{i}") for i in range(5000)
    )
    assert run(exactly)["status"] == "no_references"
    with pytest.raises(SemanticError, match="^semantic_input$"):
        run((*exactly, replace(row, observation_id=9000, source_id="kimdis:extra")))
    many = tuple(award(f"T{i}") for i in range(1000))
    assert run((replace(row, references=many),))["status"] == "observed_references"
    with pytest.raises(SemanticError, match="^semantic_input$"):
        run((replace(row, references=(*many, award("T1000"))),))
    with pytest.raises(SemanticError, match="^semantic_input$"):
        run(cast(tuple[Cited, ...], [row]))


@pytest.mark.parametrize("threshold", [0, -1, True, 1.5, "2"])
def test_an_invalid_threshold_is_refused(threshold: object) -> None:
    with pytest.raises(SemanticError, match="^semantic_selection$"):
        run(example(), umbrella_threshold=threshold)


@pytest.mark.parametrize("cutoff", [datetime(2026, 1, 10), "2026-01-10", None])
def test_an_invalid_cutoff_is_refused(cutoff: object) -> None:
    with pytest.raises(SemanticError, match="^semantic_selection$"):
        evaluate(example(), cutoff=cast(datetime, cutoff))


def test_the_definition_names_its_rules_and_adopts_no_default_threshold() -> None:
    value = definition()
    assert value["model"] == "lifecycle_references.v1" and value["status"] == "draft"
    assert value["umbrella"] == "no_default_threshold_disclose_sharing_and_flag_only_when_asked"
    assert value["cites"] == "a_reference_records_a_citation_not_supersession"
    assert definition_sha256() == definition_sha256() and len(definition_sha256()) == 64


def test_the_payload_is_plain_json() -> None:
    result: LifecycleResult = evaluate(example(), cutoff=CUTOFF)
    text = json.dumps(result.payload(), allow_nan=False, sort_keys=True)
    assert json.loads(text) == result.payload()


def test_the_provider_imports_only_the_shared_pure_semantic_modules() -> None:
    from tests.test_semantics import imported_modules

    allowed = {"nima.semantics.selection", "nima.semantics.participation"}
    for module in imported_modules("lifecycle.py"):
        assert module in allowed or not module.startswith(("nima.", "psycopg", "prefect", "httpx"))
    assert imported_modules("lifecycle.py") & allowed == allowed
