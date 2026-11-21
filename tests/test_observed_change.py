"""Hand-labelled U4 results: what two captures of one declared query did and did not contain.

Every scenario also runs the packaged reference SQL on real PostgreSQL and requires the same
complete result. The metric abstains (`incomparable`, no categories) unless both captures are
complete, ask the same question and are strictly ordered in time.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.semantics.observed_change import (
    Capture,
    CapturedVersion,
    MetricResult,
    RunFacts,
    definition,
    definition_sha256,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.semantics.participation import SemanticError


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


QUERY = sha("query")
DAY_ONE = datetime(2026, 1, 1, tzinfo=UTC)
DAY_ONE_END = datetime(2026, 1, 1, 6, tzinfo=UTC)


def at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


def run(
    run_id: str = "r",
    *,
    query: str = QUERY,
    complete: bool = True,
    normalized: bool = True,
    quarantined: int = 0,
    start: datetime = DAY_ONE,
    end: datetime = DAY_ONE_END,
) -> RunFacts:
    return RunFacts(run_id, query, complete, normalized, quarantined, start, end)


def ver(observation_id: int, record: str, version: str, observed: datetime) -> CapturedVersion:
    return CapturedVersion(observation_id, f"kimdis:{record}", sha(version), observed)


def example() -> tuple[Capture, Capture]:
    """The spec's example: X unchanged, Y changed, Z missing from the later capture, W added."""
    earlier = Capture(
        (run("a", start=at(1), end=at(1, 6)),),
        (ver(1, "X", "x1", at(1, 1)), ver(2, "Y", "y1", at(1, 1)), ver(3, "Z", "z1", at(1, 1))),
    )
    later = Capture(
        (run("b", start=at(3), end=at(3, 6)),),
        (ver(4, "X", "x1", at(3, 1)), ver(5, "Y", "y2", at(3, 1)), ver(6, "W", "w1", at(3, 1))),
    )
    return earlier, later


def sql_result(dsn: str, earlier: Capture, later: Capture) -> Any:
    runs, versions = sql_rows(earlier, later)
    with psycopg.connect(dsn) as connection:
        row = connection.execute(reference_sql(), (Jsonb(runs), Jsonb(versions))).fetchone()
    assert row is not None
    return row[0]


def both(dsn: str, earlier: Capture, later: Capture) -> dict[str, Any]:
    payload = cast(dict[str, Any], evaluate(earlier, later).payload())
    assert sql_result(dsn, earlier, later) == payload
    return payload


def ids(payload: dict[str, Any], category: str) -> list[str]:
    rows = payload[category]
    return [row if isinstance(row, str) else row["source_id"] for row in rows]


def test_the_spec_example_is_counted_by_hand_and_by_sql(pg_dsn: str) -> None:
    payload = both(pg_dsn, *example())
    assert payload["status"] == "observed_changes" and payload["reasons"] == []
    assert payload["counts"] == {
        "added": 1,
        "changed": 1,
        "missing_from_later_capture": 1,
        "unchanged": 1,
    }
    assert payload["added"] == [
        {"source_id": "kimdis:W", "later_version": sha("w1"), "later_observation_ids": [6]}
    ]
    assert payload["changed"] == [
        {
            "source_id": "kimdis:Y",
            "earlier_version": sha("y1"),
            "later_version": sha("y2"),
            "earlier_observation_ids": [2],
            "later_observation_ids": [5],
        }
    ]
    assert payload["missing_from_later_capture"] == [
        {"source_id": "kimdis:Z", "earlier_version": sha("z1"), "earlier_observation_ids": [3]}
    ]
    assert payload["unchanged"] == ["kimdis:X"]
    assert payload["earlier"] == {
        "run_ids": ["a"],
        "query_hashes": [QUERY],
        "records": 3,
        "ambiguous_source_ids": [],
    }
    assert payload["later"]["records"] == 3


def test_an_incomplete_later_capture_makes_the_comparison_incomparable(pg_dsn: str) -> None:
    earlier, later = example()
    for broken in (
        replace(later.runs[0], collection_complete=False),
        replace(later.runs[0], normalization_complete=False),
    ):
        payload = both(pg_dsn, earlier, replace(later, runs=(broken,)))
        assert payload["status"] == "incomparable" and payload["reasons"] == ["run_incomplete"]
        assert payload["counts"] == {
            "added": 0,
            "changed": 0,
            "missing_from_later_capture": 0,
            "unchanged": 0,
        }
        assert all(payload[c] == [] for c in ("added", "changed", "missing_from_later_capture"))
        assert payload["unchanged"] == []
        assert payload["later"]["records"] == 3


def test_each_reason_to_abstain_is_reported_alone_and_together_in_sorted_order(
    pg_dsn: str,
) -> None:
    earlier, later = example()
    other = sha("another query")
    cases = {
        "run_incomplete": (replace(earlier.runs[0], collection_complete=False), later.runs[0]),
        "quarantined_records": (earlier.runs[0], replace(later.runs[0], quarantined=1)),
        "query_mismatch": (earlier.runs[0], replace(later.runs[0], query_sha256=other)),
        "not_later": (earlier.runs[0], replace(later.runs[0], observed_from=at(1, 6))),
    }
    for reason, (first, second) in cases.items():
        payload = both(pg_dsn, replace(earlier, runs=(first,)), replace(later, runs=(second,)))
        assert payload["reasons"] == [reason], reason
    nothing = both(pg_dsn, replace(earlier, runs=()), later)
    assert nothing["reasons"] == ["no_runs"] and nothing["earlier"]["run_ids"] == []
    assert both(pg_dsn, earlier, replace(later, runs=()))["reasons"] == ["no_runs"]
    everything = both(
        pg_dsn,
        replace(earlier, runs=(replace(earlier.runs[0], quarantined=2, query_sha256=other),)),
        replace(
            later,
            runs=(replace(later.runs[0], normalization_complete=False, observed_from=at(1)),),
        ),
    )
    assert everything["reasons"] == [
        "not_later",
        "quarantined_records",
        "query_mismatch",
        "run_incomplete",
    ]


def test_the_later_capture_must_start_strictly_after_the_earlier_one_ends(pg_dsn: str) -> None:
    earlier, later = example()
    touching = replace(later.runs[0], observed_from=earlier.runs[0].observed_to)
    assert both(pg_dsn, earlier, replace(later, runs=(touching,)))["reasons"] == ["not_later"]
    just_after = replace(
        later.runs[0], observed_from=earlier.runs[0].observed_to + timedelta(seconds=1)
    )
    assert both(pg_dsn, earlier, replace(later, runs=(just_after,)))["status"] == "observed_changes"


def test_several_runs_of_one_query_form_one_capture(pg_dsn: str) -> None:
    earlier, later = example()
    two = replace(
        earlier,
        runs=(run("a1", start=at(1), end=at(1, 3)), run("a2", start=at(1, 4), end=at(1, 6))),
    )
    payload = both(pg_dsn, two, later)
    assert payload["earlier"]["run_ids"] == ["a1", "a2"] and payload["status"] == "observed_changes"
    spread = replace(
        later,
        runs=(
            run("b1", start=at(3), end=at(3, 2)),
            run("b2", query=sha("q2"), start=at(3), end=at(3, 4)),
        ),
    )
    assert both(pg_dsn, two, spread)["reasons"] == ["query_mismatch"]
    assert both(pg_dsn, two, spread)["later"]["query_hashes"] == sorted([QUERY, sha("q2")])


def test_two_empty_complete_captures_are_compared_and_unchanged(pg_dsn: str) -> None:
    earlier, later = example()
    payload = both(pg_dsn, replace(earlier, versions=()), replace(later, versions=()))
    assert payload["status"] == "no_observed_change"
    assert payload["counts"]["unchanged"] == 0


def test_an_empty_earlier_capture_makes_everything_added_and_the_reverse_makes_it_missing(
    pg_dsn: str,
) -> None:
    earlier, later = example()
    grown = both(pg_dsn, replace(earlier, versions=()), later)
    assert grown["counts"]["added"] == 3 and ids(grown, "added") == [
        "kimdis:W",
        "kimdis:X",
        "kimdis:Y",
    ]
    shrunk = both(pg_dsn, earlier, replace(later, versions=()))
    assert shrunk["counts"]["missing_from_later_capture"] == 3


def test_identical_captures_have_no_observed_change(pg_dsn: str) -> None:
    earlier, later = example()
    mirrored = replace(
        later,
        versions=tuple(
            replace(v, observation_id=v.observation_id + 10, observed_at=at(3, 1))
            for v in earlier.versions
        ),
    )
    payload = both(pg_dsn, earlier, mirrored)
    assert payload["status"] == "no_observed_change"
    assert payload["counts"] == {
        "added": 0,
        "changed": 0,
        "missing_from_later_capture": 0,
        "unchanged": 3,
    }
    assert payload["unchanged"] == ["kimdis:X", "kimdis:Y", "kimdis:Z"]


def test_the_latest_version_within_a_capture_is_the_one_compared(pg_dsn: str) -> None:
    earlier, later = example()
    mid_capture = replace(
        later,
        versions=(*later.versions, ver(7, "X", "x2", at(3, 4))),
    )
    payload = both(pg_dsn, earlier, mid_capture)
    changed = {row["source_id"]: row for row in payload["changed"]}
    assert changed["kimdis:X"]["later_version"] == sha("x2")
    assert changed["kimdis:X"]["later_observation_ids"] == [7]
    assert "kimdis:X" not in payload["unchanged"]


def test_a_repeated_observation_of_one_version_counts_once_and_keeps_both_observations(
    pg_dsn: str,
) -> None:
    earlier, later = example()
    repeated = replace(later, versions=(*later.versions, ver(8, "X", "x1", at(3, 1))))
    payload = both(pg_dsn, earlier, repeated)
    assert payload["unchanged"] == ["kimdis:X"] and payload["counts"]["unchanged"] == 1


def test_a_record_with_tied_different_versions_is_ambiguous_and_excluded_everywhere(
    pg_dsn: str,
) -> None:
    earlier, later = example()
    tied = replace(later, versions=(*later.versions, ver(9, "Y", "y3", at(3, 1))))
    payload = both(pg_dsn, earlier, tied)
    assert payload["later"]["ambiguous_source_ids"] == ["kimdis:Y"]
    assert payload["later"]["records"] == 2
    assert "kimdis:Y" not in ids(payload, "changed") and "kimdis:Y" not in payload["unchanged"]
    assert payload["counts"] == {
        "added": 1,
        "changed": 0,
        "missing_from_later_capture": 1,
        "unchanged": 1,
    }
    both_sides = replace(earlier, versions=(*earlier.versions, ver(10, "Y", "y0", at(1, 1))))
    payload = both(pg_dsn, both_sides, tied)
    assert payload["earlier"]["ambiguous_source_ids"] == ["kimdis:Y"]


def test_a_record_ambiguous_in_one_capture_is_not_added_or_missing_in_the_other(
    pg_dsn: str,
) -> None:
    earlier, later = example()
    only_later = replace(
        later,
        versions=(*later.versions, ver(11, "Z", "z2", at(3, 1)), ver(12, "Z", "z3", at(3, 1))),
    )
    payload = both(pg_dsn, earlier, only_later)
    assert payload["later"]["ambiguous_source_ids"] == ["kimdis:Z"]
    assert "kimdis:Z" not in ids(payload, "missing_from_later_capture")
    assert payload["counts"]["missing_from_later_capture"] == 0


def test_a_record_ambiguous_only_in_the_earlier_capture_is_not_added_by_the_later_one(
    pg_dsn: str,
) -> None:
    earlier, later = example()
    tied_earlier = replace(earlier, versions=(*earlier.versions, ver(13, "Y", "y0", at(1, 1))))
    payload = both(pg_dsn, tied_earlier, later)
    assert payload["earlier"]["ambiguous_source_ids"] == ["kimdis:Y"]
    assert payload["later"]["ambiguous_source_ids"] == []
    assert "kimdis:Y" not in ids(payload, "added") and "kimdis:Y" not in ids(payload, "changed")
    assert payload["counts"] == {
        "added": 1,
        "changed": 0,
        "missing_from_later_capture": 1,
        "unchanged": 1,
    }


def test_observation_ids_are_listed_in_ascending_order_whatever_the_input_order(
    pg_dsn: str,
) -> None:
    earlier, later = example()
    repeated = replace(
        later,
        versions=(ver(21, "Y", "y2", at(3, 1)), ver(5, "Y", "y2", at(3, 1)), *later.versions[2:]),
    )
    repeated_earlier = replace(
        earlier,
        versions=(*earlier.versions, ver(15, "Y", "y1", at(1, 1)), ver(14, "Y", "y1", at(1, 1))),
    )
    payload = both(pg_dsn, repeated_earlier, repeated)
    changed = {row["source_id"]: row for row in payload["changed"]}
    assert changed["kimdis:Y"]["later_observation_ids"] == [5, 21]
    assert changed["kimdis:Y"]["earlier_observation_ids"] == [2, 14, 15]


def test_the_counts_reconcile_with_the_selected_records_of_each_capture(pg_dsn: str) -> None:
    earlier, later = example()
    tied = replace(later, versions=(*later.versions, ver(9, "Y", "y3", at(3, 1))))
    for payload in (both(pg_dsn, earlier, later), both(pg_dsn, earlier, tied)):
        c = payload["counts"]
        assert (
            payload["earlier"]["records"]
            >= c["missing_from_later_capture"] + c["changed"] + c["unchanged"]
        )
        assert payload["later"]["records"] >= c["added"] + c["changed"] + c["unchanged"]
    plain = both(pg_dsn, earlier, later)["counts"]
    assert plain["missing_from_later_capture"] + plain["changed"] + plain["unchanged"] == 3
    assert plain["added"] + plain["changed"] + plain["unchanged"] == 3


def test_the_order_of_the_inputs_does_not_change_the_result(pg_dsn: str) -> None:
    earlier, later = example()
    forward = both(pg_dsn, earlier, later)
    flipped = both(
        pg_dsn,
        replace(
            earlier, runs=tuple(reversed(earlier.runs)), versions=tuple(reversed(earlier.versions))
        ),
        replace(later, versions=tuple(reversed(later.versions))),
    )
    assert flipped == forward


def test_source_ids_are_ordered_bytewise_in_every_category(pg_dsn: str) -> None:
    earlier = Capture(
        (run("a"),),
        tuple(ver(i + 1, name, "v", at(1, 1)) for i, name in enumerate(("b", "B", "a"))),
    )
    later = Capture((run("b", start=at(3), end=at(3, 6)),), ())
    payload = both(pg_dsn, earlier, later)
    assert ids(payload, "missing_from_later_capture") == ["kimdis:B", "kimdis:a", "kimdis:b"]


def test_the_definition_is_bound_to_the_sql() -> None:
    value = definition()
    assert value["metric"] == "observed_change_between_captures.v1" and value["status"] == "draft"
    assert value["abstains"] == "incomparable_unless_both_complete_same_query_strictly_ordered"
    assert value["sql_sha256"] == hashlib.sha256(reference_sql().encode()).hexdigest()
    assert definition_sha256() == definition_sha256() and len(definition_sha256()) == 64


def test_the_payload_is_plain_json() -> None:
    result: MetricResult = evaluate(*example())
    text = json.dumps(result.payload(), allow_nan=False, sort_keys=True)
    assert json.loads(text) == result.payload()


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": ""},
        {"run_id": 5},
        {"run_id": "x" * 65},
        {"query_sha256": "xyz"},
        {"query_sha256": "A" * 64},
        {"collection_complete": 1},
        {"normalization_complete": "yes"},
        {"quarantined": -1},
        {"quarantined": True},
        {"quarantined": 1.5},
        {"observed_from": datetime(2026, 1, 1)},
        {"observed_to": datetime(2026, 1, 1, 6, tzinfo=timezone(timedelta(hours=2)))},
        {"observed_from": at(2), "observed_to": at(1)},
    ],
)
def test_malformed_run_facts_are_refused_with_a_fixed_reason(change: dict[str, Any]) -> None:
    earlier, later = example()
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(replace(earlier, runs=(replace(earlier.runs[0], **change),)), later)


@pytest.mark.parametrize(
    "change",
    [
        {"observation_id": 0},
        {"observation_id": True},
        {"source_id": "gemi:1"},
        {"source_id": "kimdis:"},
        {"source_id": "kimdis:   "},
        {"content_sha256": "xyz"},
        {"content_sha256": "A" * 64},
        {"observed_at": datetime(2026, 1, 1)},
        {"observed_at": datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))},
    ],
)
def test_malformed_versions_are_refused_with_a_fixed_reason(change: dict[str, Any]) -> None:
    earlier, later = example()
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(earlier, replace(later, versions=(replace(later.versions[0], **change),)))


def test_captures_must_be_tuples_with_unique_observation_ids_across_both() -> None:
    earlier, later = example()
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(cast(Capture, "nope"), later)
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(replace(earlier, runs=cast(tuple[RunFacts, ...], list(earlier.runs))), later)
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(
            replace(earlier, versions=cast(tuple[CapturedVersion, ...], list(earlier.versions))),
            later,
        )
    duplicate = replace(
        later, versions=(replace(later.versions[0], observation_id=1), *later.versions[1:])
    )
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(earlier, duplicate)
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(replace(earlier, runs=(cast(RunFacts, "run"),)), later)
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(earlier, replace(later, versions=(cast(CapturedVersion, "v"),)))


def test_the_bounds_are_exact() -> None:
    earlier, later = example()
    many = tuple(ver(100 + i, f"R{i}", "v", at(3, 1)) for i in range(5000))
    assert evaluate(earlier, replace(later, versions=many)).later.records == 5000
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(earlier, replace(later, versions=(*many, ver(9000, "extra", "v", at(3, 1)))))
    runs = tuple(run(f"r{i}", start=at(3), end=at(3, 6)) for i in range(100))
    assert evaluate(earlier, replace(later, runs=runs)).later.run_ids[0] == "r0"
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(earlier, replace(later, runs=(*runs, run("r100", start=at(3), end=at(3, 6)))))


def test_the_provider_imports_only_the_shared_pure_semantic_modules() -> None:
    from tests.test_semantics import imported_modules

    allowed = {"nima.semantics.selection", "nima.semantics.participation"}
    for module in imported_modules("observed_change.py"):
        assert module in allowed or not module.startswith(("nima.", "psycopg", "prefect", "httpx"))
    assert imported_modules("observed_change.py") & allowed == allowed
