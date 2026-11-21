"""Hand-labelled U2 counts: captured contract records by CPV base code and reported month.

Every scenario runs the pure provider and the packaged reference SQL on real PostgreSQL and
requires the same complete result. Date parsing is the shared time model (tested separately); the
SQL receives the parsed period, so parity here covers selection, placement and aggregation.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.semantics.cpv_period import (
    CpvAssertion,
    MetricResult,
    Observation,
    definition,
    definition_sha256,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.semantics.cpv_period import SemanticError as CpvSemanticError

A = "33141120-7"
A_OTHER_DIGIT = "33141120-3"
B = "45000000-7"
C = "30000000-9"
CUTOFF = datetime(2026, 4, 30, tzinfo=UTC)


def day(number: int, month: int = 4) -> datetime:
    return datetime(2026, month, number, tzinfo=UTC)


def reported(*codes: str) -> tuple[CpvAssertion, ...]:
    return tuple(CpvAssertion("reported", code) for code in codes)


NONE_REPORTED = (CpvAssertion("missing", None),)


def obs(
    observation_id: int,
    record: str,
    version: str,
    observed: datetime,
    cpv: tuple[CpvAssertion, ...] | None,
    submitted: str | None = "2026-03-10T08:00:00.123",
    cancelled: bool | None = False,
) -> Observation:
    return Observation(
        observation_id,
        f"kimdis:{record}",
        "kimdis-normalized-v1",
        hashlib.sha256(version.encode()).hexdigest(),
        observed,
        cancelled,
        submitted,
        cpv,
    )


def example() -> tuple[Observation, ...]:
    """The spec's synthetic example: R1 A in March, R2 A and B in March, R3 no CPV, R4 bad date."""
    return (
        obs(1, "R1", "r1", day(1), reported(A), "2026-03-10T08:00:00.123", False),
        obs(2, "R2", "r2", day(1), reported(A, B), "2026-03-20T09:30:00.12", True),
        obs(3, "R3", "r3", day(1), NONE_REPORTED, "2026-03-25T10:00:00.1", None),
        obs(4, "R4", "r4", day(1), reported(B), "not a date", False),
    )


def sql_result(dsn: str, rows: tuple[Observation, ...], **selection: Any) -> Any:
    parameters = (
        Jsonb(sql_rows(rows)),
        selection.get("cutoff", CUTOFF),
        selection.get("cpv_base_code"),
        selection.get("period_from"),
        selection.get("period_to"),
    )
    with psycopg.connect(dsn) as connection:
        row = connection.execute(reference_sql(), parameters).fetchone()
    assert row is not None
    return row[0]


def both(dsn: str, rows: tuple[Observation, ...], **selection: Any) -> dict[str, Any]:
    selection.setdefault("cutoff", CUTOFF)
    result = evaluate(rows, **selection)
    payload = cast(dict[str, Any], result.payload())
    assert sql_result(dsn, rows, **selection) == payload
    return payload


def cells(payload: dict[str, Any]) -> dict[tuple[str | None, str | None], list[str]]:
    return {(c["cpv_base_code"], c["period"]): c["source_ids"] for c in payload["cells"]}


def test_the_spec_example_is_counted_by_hand_and_by_sql(pg_dsn: str) -> None:
    payload = both(pg_dsn, example())
    assert payload["status"] == "observed_activity"
    assert cells(payload) == {
        ("33141120", "2026-03"): ["kimdis:R1", "kimdis:R2"],
        ("45000000", "2026-03"): ["kimdis:R2"],
        (None, "2026-03"): ["kimdis:R3"],
        ("45000000", None): ["kimdis:R4"],
    }
    assert [(c["cpv_base_code"], c["period"]) for c in payload["cells"]] == [
        ("33141120", "2026-03"),
        ("45000000", "2026-03"),
        ("45000000", None),
        (None, "2026-03"),
    ]
    assert payload["period_totals"] == [
        {"period": "2026-03", "record_count": 3},
        {"period": None, "record_count": 1},
    ]
    assert payload["coverage"] == {
        "selected_records": 4,
        "classified": 3,
        "unclassified_no_reported_code": 1,
        "unclassified_metadata_unavailable": 0,
        "period_parsed": 3,
        "period_absent": 0,
        "period_unparseable": 1,
    }
    assert payload["ambiguous_source_ids"] == []


def test_a_record_with_several_codes_is_overlapping_not_double_counted_in_a_period(
    pg_dsn: str,
) -> None:
    payload = both(pg_dsn, example())
    in_march = sum(c["record_count"] for c in payload["cells"] if c["period"] == "2026-03")
    total = {t["period"]: t["record_count"] for t in payload["period_totals"]}
    assert in_march == 4 and total["2026-03"] == 3


def test_cancellation_is_included_with_a_breakdown_per_cell(pg_dsn: str) -> None:
    payload = both(pg_dsn, example())
    by_cell = {(c["cpv_base_code"], c["period"]): c for c in payload["cells"]}
    assert by_cell[("33141120", "2026-03")]["cancelled_count"] == 1
    assert by_cell[("33141120", "2026-03")]["unknown_cancellation_count"] == 0
    assert by_cell[(None, "2026-03")]["unknown_cancellation_count"] == 1
    assert by_cell[("45000000", None)]["cancelled_count"] == 0


def test_the_cpv_filter_keeps_only_records_with_that_code_and_never_unclassified(
    pg_dsn: str,
) -> None:
    payload = both(pg_dsn, example(), cpv_base_code="45000000")
    assert cells(payload) == {
        ("45000000", "2026-03"): ["kimdis:R2"],
        ("45000000", None): ["kimdis:R4"],
    }
    assert payload["period_totals"] == [
        {"period": "2026-03", "record_count": 1},
        {"period": None, "record_count": 1},
    ]


def test_the_period_filter_keeps_only_parsed_months_in_range(pg_dsn: str) -> None:
    rows = (
        obs(1, "J", "j", day(1), reported(A), "2026-01-31T23:59:59.999"),
        obs(2, "F", "f", day(1), reported(A), "2026-02-01T00:00:00.000"),
        obs(3, "M", "m", day(1), reported(A), "2026-03-15T12:00:00.5"),
        obs(4, "X", "x", day(1), reported(A), None),
        obs(5, "Y", "y", day(1), reported(A), "15/03/2026"),
    )
    both_ends = both(pg_dsn, rows, period_from="2026-02", period_to="2026-03")
    assert cells(both_ends) == {
        ("33141120", "2026-02"): ["kimdis:F"],
        ("33141120", "2026-03"): ["kimdis:M"],
    }
    from_only = both(pg_dsn, rows, period_from="2026-02")
    assert sorted(p for (_, p) in cells(from_only) if p is not None) == ["2026-02", "2026-03"]
    assert all(p is not None for (_, p) in cells(from_only))
    to_only = both(pg_dsn, rows, period_to="2026-01")
    assert cells(to_only) == {("33141120", "2026-01"): ["kimdis:J"]}
    unfiltered = both(pg_dsn, rows)
    assert (("33141120", None)) in cells(unfiltered)
    assert unfiltered["coverage"]["period_absent"] == 1
    assert unfiltered["coverage"]["period_unparseable"] == 1


def test_unknown_period_records_are_disclosed_but_not_placed_when_a_period_is_requested(
    pg_dsn: str,
) -> None:
    rows = (obs(1, "X", "x", day(1), reported(A), None),)
    payload = both(pg_dsn, rows, period_from="2026-03", period_to="2026-03")
    assert payload["cells"] == []
    assert payload["status"] == "selection_unresolved"
    assert payload["coverage"]["selected_records"] == 1


def test_no_match_with_complete_information_is_no_observed_activity(pg_dsn: str) -> None:
    rows = (obs(1, "X", "x", day(1), reported(A), "2026-03-10T08:00:00.1"),)
    assert both(pg_dsn, rows, period_from="2026-05")["status"] == "no_observed_activity"
    assert both(pg_dsn, rows, cpv_base_code="45000000")["status"] == "no_observed_activity"


def test_an_unclassified_record_makes_a_cpv_request_unresolved_not_empty(pg_dsn: str) -> None:
    rows = (obs(1, "X", "x", day(1), NONE_REPORTED),)
    payload = both(pg_dsn, rows, cpv_base_code="45000000")
    assert payload["cells"] == [] and payload["status"] == "selection_unresolved"


def test_duplicate_codes_and_other_check_digits_of_one_base_collapse_to_one_placement(
    pg_dsn: str,
) -> None:
    rows = (obs(1, "X", "x", day(1), reported(A, A, A_OTHER_DIGIT)),)
    payload = both(pg_dsn, rows)
    assert payload["records"][0]["cpv_base_codes"] == ["33141120"]
    assert [(c["cpv_base_code"], c["record_count"]) for c in payload["cells"]] == [("33141120", 1)]


def test_only_reported_codes_place_a_record_other_statuses_do_not(pg_dsn: str) -> None:
    mixed = (
        CpvAssertion("invalid", None),
        CpvAssertion("empty", None),
        CpvAssertion("null", None),
        CpvAssertion("reported", B),
    )
    payload = both(pg_dsn, (obs(1, "X", "x", day(1), mixed),))
    assert payload["records"][0]["cpv_base_codes"] == ["45000000"]
    only_bad = (CpvAssertion("invalid", None), CpvAssertion("empty", None))
    unclassified = both(pg_dsn, (obs(1, "X", "x", day(1), only_bad),))
    assert unclassified["records"][0]["classification"] == "unclassified_no_reported_code"


def test_an_empty_assertion_list_is_no_reported_code_not_unavailable_metadata(pg_dsn: str) -> None:
    payload = both(pg_dsn, (obs(1, "X", "x", day(1), ()),))
    assert payload["records"][0]["classification"] == "unclassified_no_reported_code"


def test_missing_metadata_for_a_version_is_its_own_unclassified_reason(pg_dsn: str) -> None:
    payload = both(pg_dsn, (obs(1, "X", "x", day(1), None),))
    assert payload["records"][0]["classification"] == "unclassified_metadata_unavailable"
    assert payload["coverage"]["unclassified_metadata_unavailable"] == 1
    assert cells(payload) == {(None, "2026-03"): ["kimdis:X"]}


def test_the_latest_observed_version_decides_the_placement(pg_dsn: str) -> None:
    rows = (
        obs(1, "X", "v1", day(1), reported(A), "2026-03-10T08:00:00.1"),
        obs(2, "X", "v2", day(2), reported(B), "2026-04-02T08:00:00.1"),
    )
    assert cells(both(pg_dsn, rows)) == {("45000000", "2026-04"): ["kimdis:X"]}
    assert cells(both(pg_dsn, rows, cutoff=day(1))) == {("33141120", "2026-03"): ["kimdis:X"]}


def test_a_b_a_reuses_the_last_observed_version(pg_dsn: str) -> None:
    rows = (
        obs(1, "X", "a", day(1), reported(A)),
        obs(2, "X", "b", day(2), reported(B)),
        obs(3, "X", "a", day(3), reported(A)),
    )
    payload = both(pg_dsn, rows)
    assert cells(payload) == {("33141120", "2026-03"): ["kimdis:X"]}
    assert payload["records"][0]["observation_ids"] == [3]


def test_different_versions_tied_at_the_latest_time_are_ambiguous_and_not_placed(
    pg_dsn: str,
) -> None:
    rows = (
        obs(1, "X", "v1", day(1), reported(A)),
        obs(2, "X", "v2", day(1), reported(B)),
        obs(3, "Y", "y", day(1), reported(A)),
    )
    payload = both(pg_dsn, rows)
    assert payload["ambiguous_source_ids"] == ["kimdis:X"]
    assert cells(payload) == {("33141120", "2026-03"): ["kimdis:Y"]}
    ambiguous = next(r for r in payload["records"] if r["source_id"] == "kimdis:X")
    assert (ambiguous["ambiguous"], ambiguous["period"], ambiguous["classification"]) == (
        True,
        None,
        None,
    )


def test_an_ambiguous_record_alone_makes_the_selection_unresolved(pg_dsn: str) -> None:
    rows = (obs(1, "X", "v1", day(1), reported(A)), obs(2, "X", "v2", day(1), reported(B)))
    assert both(pg_dsn, rows)["status"] == "selection_unresolved"


def test_repeated_observation_of_one_version_counts_once(pg_dsn: str) -> None:
    rows = (obs(1, "X", "x", day(1), reported(A)), obs(2, "X", "x", day(2), reported(A)))
    payload = both(pg_dsn, rows)
    assert [c["record_count"] for c in payload["cells"]] == [1]
    assert payload["records"][0]["observation_ids"] == [2]


def test_the_statuses_of_an_empty_or_early_capture(pg_dsn: str) -> None:
    assert both(pg_dsn, ())["status"] == "empty_capture"
    assert both(pg_dsn, example(), cutoff=datetime(2026, 3, 1, tzinfo=UTC))["status"] == (
        "no_observations_before_cutoff"
    )


def test_the_order_of_the_observations_does_not_change_the_result(pg_dsn: str) -> None:
    rows = example()
    forward = both(pg_dsn, rows)
    assert both(pg_dsn, tuple(reversed(rows))) == forward
    extra = replace(rows[0], observation_id=9)
    assert both(pg_dsn, (*reversed(rows), extra))["cells"] == forward["cells"]


def test_cells_are_ordered_with_unknowns_last_and_codes_as_text(pg_dsn: str) -> None:
    rows = (
        obs(1, "A", "a", day(1), reported(C), "2026-04-01T00:00:00.1"),
        obs(2, "B", "b", day(1), reported(A), "2026-03-01T00:00:00.1"),
        obs(3, "C", "c", day(1), reported(A), None),
        obs(4, "D", "d", day(1), NONE_REPORTED, "2026-03-01T00:00:00.1"),
        obs(5, "E", "e", day(1), reported(A), "2026-04-01T00:00:00.1"),
    )
    order = [(c["cpv_base_code"], c["period"]) for c in both(pg_dsn, rows)["cells"]]
    assert order == [
        ("30000000", "2026-04"),
        ("33141120", "2026-03"),
        ("33141120", "2026-04"),
        ("33141120", None),
        (None, "2026-03"),
    ]


def test_another_normalizer_or_source_namespace_is_refused() -> None:
    row = example()[0]
    for bad in (replace(row, normalizer_version="other"), replace(row, source_id="gemi:1")):
        with pytest.raises(CpvSemanticError, match="^semantic_input$"):
            evaluate((bad,), cutoff=CUTOFF)


@pytest.mark.parametrize(
    "change",
    [
        {"observation_id": 0},
        {"source_id": "kimdis:"},
        {"source_id": "kimdis:   "},
        {"observation_id": True},
        {"content_sha256": "xyz"},
        {"content_sha256": "A" * 64},
        {"observed_at": datetime(2026, 4, 1)},
        {"observed_at": datetime(2026, 4, 1, tzinfo=timezone(timedelta(hours=2)))},
        {"cancelled": "no"},
        {"submitted_text": 5},
        {"cpv": [CpvAssertion("reported", A)]},
        {"cpv": (CpvAssertion("reported", None),)},
        {"cpv": (CpvAssertion("reported", "123"),)},
        {"cpv": (CpvAssertion("reported", "3314112-07"),)},
        {"cpv": (CpvAssertion("reported", "33141120-77"),)},
        {"cpv": (CpvAssertion("unknown", None),)},
        {"cpv": ("not an assertion",)},
        {"cpv": (CpvAssertion("missing", A),)},
    ],
)
def test_malformed_observations_are_refused_with_a_fixed_reason(change: dict[str, Any]) -> None:
    with pytest.raises(CpvSemanticError, match="^semantic_input$"):
        evaluate((replace(example()[0], **change),), cutoff=CUTOFF)


def test_observations_must_be_a_tuple_within_the_bounds() -> None:
    row = example()[0]
    with pytest.raises(CpvSemanticError, match="^semantic_input$"):
        evaluate(cast(tuple[Observation, ...], [row]), cutoff=CUTOFF)
    with pytest.raises(CpvSemanticError, match="^semantic_input$"):
        evaluate(tuple(replace(row, observation_id=i + 1) for i in range(5001)), cutoff=CUTOFF)
    exactly = tuple(replace(row, observation_id=i + 1) for i in range(5000))
    assert evaluate(exactly, cutoff=CUTOFF).status == "observed_activity"
    many = tuple(CpvAssertion("missing", None) for _ in range(1001))
    with pytest.raises(CpvSemanticError, match="^semantic_input$"):
        evaluate((replace(row, cpv=many),), cutoff=CUTOFF)
    just_fits = tuple(CpvAssertion("missing", None) for _ in range(1000))
    assert evaluate((replace(row, cpv=just_fits),), cutoff=CUTOFF).status == "observed_activity"


def test_duplicate_observation_ids_and_conflicting_versions_are_refused() -> None:
    row = example()[0]
    with pytest.raises(CpvSemanticError, match="^semantic_input$"):
        evaluate((row, row), cutoff=CUTOFF)
    changed = replace(row, observation_id=2, cancelled=True)
    with pytest.raises(CpvSemanticError, match="^semantic_version_conflict$"):
        evaluate((row, changed), cutoff=CUTOFF)
    different_cpv = replace(row, observation_id=3, cpv=reported(B))
    with pytest.raises(CpvSemanticError, match="^semantic_version_conflict$"):
        evaluate((row, different_cpv), cutoff=CUTOFF)
    different_date = replace(row, observation_id=4, submitted_text="2026-03-11T08:00:00.123")
    with pytest.raises(CpvSemanticError, match="^semantic_version_conflict$"):
        evaluate((row, different_date), cutoff=CUTOFF)


@pytest.mark.parametrize(
    "selection",
    [
        {"cutoff": datetime(2026, 4, 30)},
        {"cutoff": "2026-04-30"},
        {"cpv_base_code": "3314112"},
        {"cpv_base_code": "33141120-7"},
        {"cpv_base_code": "3314112a"},
        {"cpv_base_code": 33141120},
        {"period_from": "2026-3"},
        {"period_from": "2026-13"},
        {"period_from": "2026-00"},
        {"period_to": "26-03"},
        {"period_to": "2026-03-01"},
        {"period_from": "2026-05", "period_to": "2026-04"},
    ],
)
def test_an_invalid_selection_is_refused_with_a_fixed_reason(selection: dict[str, Any]) -> None:
    arguments: dict[str, Any] = {"cutoff": CUTOFF, **selection}
    with pytest.raises(CpvSemanticError, match="^semantic_selection$"):
        evaluate(example(), **arguments)


def test_equal_period_bounds_select_one_month() -> None:
    payload = evaluate(example(), cutoff=CUTOFF, period_from="2026-03", period_to="2026-03")
    assert {c.period for c in payload.cells} == {"2026-03"}


def test_the_definition_is_bound_to_the_sql_and_the_time_model() -> None:
    value = definition()
    assert value["metric"] == "captured_record_count_by_cpv_period.v1"
    assert value["status"] == "draft"
    assert value["time_model"] == "kimdis-reported-time-v1"
    assert value["taxonomy_validation"] == "not_checked"
    assert value["sql_sha256"] == hashlib.sha256(reference_sql().encode()).hexdigest()
    assert definition_sha256() == definition_sha256() and len(definition_sha256()) == 64


def test_the_payload_is_plain_json() -> None:
    result: MetricResult = evaluate(example(), cutoff=CUTOFF)
    text = json.dumps(result.payload(), allow_nan=False, sort_keys=True)
    assert json.loads(text) == result.payload()


def test_the_provider_imports_only_the_shared_pure_semantic_modules() -> None:
    from tests.test_semantics import imported_modules

    allowed = {"nima.semantics.selection", "nima.semantics.timemodel"}
    for module in imported_modules("cpv_period.py"):
        assert module in allowed or not module.startswith(("nima.", "psycopg", "prefect", "httpx"))
    assert imported_modules("cpv_period.py") & allowed == allowed
