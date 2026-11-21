"""Hand-labelled U3 counts: how concentrated one buyer's captured supplier participation is.

Record-participation counts, never money and never market share: a record with two eligible
suppliers counts once for each, so supplier counts overlap and are not summed to the denominator.
Every scenario also runs the packaged reference SQL on real PostgreSQL and requires the same
complete result.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.semantics.buyer_concentration import (
    MetricResult,
    definition,
    definition_sha256,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.semantics.participation import Observation, SemanticError, Supplier

S1, S2, S3, S4 = "012345678", "123456780", "234567891", "345678902"
S5, S6 = "456789013", "567890124"
CUTOFF = datetime(2026, 1, 10, tzinfo=UTC)
NS = "kimdis.buyer-key:"


def day(number: int) -> datetime:
    return datetime(2026, 1, number, tzinfo=UTC)


def sup(*taxes: str, country: str = "GR") -> tuple[Supplier, ...]:
    return tuple(Supplier(i, tax, country) for i, tax in enumerate(taxes))


def obs(
    observation_id: int,
    record: str,
    version: str,
    observed: datetime,
    buyer: str | None,
    suppliers: tuple[Supplier, ...] | None,
    cancelled: bool | None = False,
) -> Observation:
    return Observation(
        observation_id,
        f"kimdis:{record}",
        "kimdis-normalized-v1",
        hashlib.sha256(version.encode()).hexdigest(),
        observed,
        buyer,
        cancelled,
        suppliers,
    )


def example() -> tuple[Observation, ...]:
    """The spec's synthetic example for one buyer, B1, with five selected records."""
    return (
        obs(1, "R1", "r1", day(1), "B1", sup(S1), False),
        obs(2, "R2", "r2", day(1), "B1", sup(S1, S2), True),
        obs(3, "R3", "r3", day(1), "B1", sup(S2), False),
        obs(4, "R4", "r4", day(1), "B1", None, None),
        obs(5, "R5", "r5", day(1), "B1", (Supplier(0, "12345", "GR"),), False),
    )


def sql_result(dsn: str, rows: tuple[Observation, ...], buyer: str, cutoff: datetime) -> Any:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            reference_sql(), (Jsonb(sql_rows(rows, limit=5000)), cutoff, buyer.strip(" \t\r\n\f\v"))
        ).fetchone()
    assert row is not None
    return row[0]


def both(
    dsn: str, rows: tuple[Observation, ...], buyer: str = "B1", cutoff: datetime = CUTOFF
) -> dict[str, Any]:
    payload = cast(dict[str, Any], evaluate(rows, buyer=buyer, cutoff=cutoff).payload())
    assert sql_result(dsn, rows, buyer, cutoff) == payload
    return payload


def counts(payload: dict[str, Any]) -> dict[str, int]:
    return {row["supplier_key"]: row["record_count"] for row in payload["suppliers"]}


def test_the_spec_example_is_counted_by_hand_and_by_sql(pg_dsn: str) -> None:
    payload = both(pg_dsn, example())
    assert payload["status"] == "observed_concentration"
    assert payload["buyer_key"] == f"{NS}B1"
    assert (payload["buyer_records"], payload["resolved_records"]) == (5, 3)
    assert payload["unresolved_records"] == 2
    assert payload["unresolved_share"] == {"numerator": 2, "denominator": 5}
    assert counts(payload) == {f"GR:{S1}": 2, f"GR:{S2}": 2}
    assert payload["participation_total"] == 4 and payload["joint_records"] == 1
    assert payload["distinct_suppliers"] == 2
    assert payload["top_supplier_keys"] == [f"GR:{S1}", f"GR:{S2}"]
    assert payload["top_record_count"] == 2
    assert payload["top_share"] == {"numerator": 2, "denominator": 3}
    by_supplier = {row["supplier_key"]: row for row in payload["suppliers"]}
    assert by_supplier[f"GR:{S1}"]["source_ids"] == ["kimdis:R1", "kimdis:R2"]
    assert by_supplier[f"GR:{S1}"]["cancelled_count"] == 1
    assert by_supplier[f"GR:{S2}"]["source_ids"] == ["kimdis:R2", "kimdis:R3"]
    reasons = {r["source_id"]: r["resolution"] for r in payload["records"]}
    assert reasons == {
        "kimdis:R1": "resolved",
        "kimdis:R2": "resolved",
        "kimdis:R3": "resolved",
        "kimdis:R4": "unknown_suppliers",
        "kimdis:R5": "no_eligible_supplier",
    }
    assert payload["ambiguous_source_ids"] == [] and payload["partial_source_ids"] == []


def test_supplier_counts_overlap_and_exceed_the_denominator(pg_dsn: str) -> None:
    payload = both(pg_dsn, example())
    assert payload["participation_total"] > payload["resolved_records"]


def test_other_buyers_records_are_not_counted_for_this_buyer(pg_dsn: str) -> None:
    rows = (*example(), obs(6, "Q1", "q1", day(1), "B2", sup(S3), False))
    assert both(pg_dsn, rows) == both(pg_dsn, example())
    other = both(pg_dsn, rows, buyer="B2")
    assert (other["buyer_records"], other["resolved_records"]) == (1, 1)
    assert counts(other) == {f"GR:{S3}": 1}
    assert other["top_share"] == {"numerator": 1, "denominator": 1}


def test_the_requested_and_reported_buyer_keys_are_compared_after_ascii_trimming(
    pg_dsn: str,
) -> None:
    rows = (
        obs(1, "R1", "r1", day(1), " B1\t", sup(S1)),
        obs(2, "R2", "r2", day(1), "B1 ", sup(S2)),
    )
    assert both(pg_dsn, rows, buyer="\tB1 ")["resolved_records"] == 2
    unlike = (obs(1, "R1", "r1", day(1), "b1", sup(S1)),)
    assert both(pg_dsn, unlike)["status"] == "no_observed_buyer_records"


def test_an_unknown_buyer_is_not_attributed_to_the_requested_buyer(pg_dsn: str) -> None:
    rows = (obs(1, "R1", "r1", day(1), None, sup(S1)), obs(2, "R2", "r2", day(1), "  ", sup(S1)))
    assert both(pg_dsn, rows)["status"] == "no_observed_buyer_records"


def test_a_supplier_is_counted_once_per_record_even_if_listed_twice_or_in_two_countries(
    pg_dsn: str,
) -> None:
    both_codes = (Supplier(0, S1, "GR"), Supplier(1, S1, "EL"), Supplier(2, f" {S1}\t", "GR"))
    rows = (
        obs(1, "R1", "r1", day(1), "B1", both_codes),
        obs(2, "R2", "r2", day(1), "B1", sup(S1, country="EL")),
    )
    payload = both(pg_dsn, rows)
    assert counts(payload) == {f"GR:{S1}": 2}
    assert payload["joint_records"] == 0 and payload["participation_total"] == 2


def test_ineligible_suppliers_leave_a_record_partly_resolved_and_are_disclosed(
    pg_dsn: str,
) -> None:
    mixed = (
        Supplier(0, S1, "GR"),
        Supplier(1, S3, "DE"),
        Supplier(2, S4, "gr"),
        Supplier(3, "000000000", "GR"),
        Supplier(4, "12345", "GR"),
        Supplier(5, "", None),
    )
    rows = (obs(1, "R1", "r1", day(1), "B1", mixed),)
    payload = both(pg_dsn, rows)
    assert counts(payload) == {f"GR:{S1}": 1}
    assert payload["partial_source_ids"] == ["kimdis:R1"]
    assert payload["records"][0]["ineligible_occurrences"] == 5
    assert payload["records"][0]["supplier_keys"] == [f"GR:{S1}"]


def test_unknown_and_empty_supplier_lists_are_different_unresolved_reasons(pg_dsn: str) -> None:
    rows = (
        obs(1, "U", "u", day(1), "B1", None),
        obs(2, "E", "e", day(1), "B1", ()),
        obs(3, "F", "f", day(1), "B1", sup(S3, country="DE")),
    )
    payload = both(pg_dsn, rows)
    assert {r["source_id"]: r["resolution"] for r in payload["records"]} == {
        "kimdis:E": "empty_suppliers",
        "kimdis:F": "no_eligible_supplier",
        "kimdis:U": "unknown_suppliers",
    }
    assert {r["source_id"]: r["ineligible_occurrences"] for r in payload["records"]} == {
        "kimdis:E": 0,
        "kimdis:F": 1,
        "kimdis:U": 0,
    }
    assert payload["status"] == "buyer_records_unresolved"
    assert payload["resolved_records"] == 0 and payload["suppliers"] == []
    assert payload["top_share"] is None and payload["top_supplier_keys"] == []
    assert payload["top_record_count"] is None
    assert payload["unresolved_share"] == {"numerator": 3, "denominator": 3}


def test_one_supplier_in_every_record_is_a_full_share(pg_dsn: str) -> None:
    rows = tuple(obs(i, f"R{i}", f"r{i}", day(1), "B1", sup(S1)) for i in (1, 2, 3))
    payload = both(pg_dsn, rows)
    assert payload["top_share"] == {"numerator": 3, "denominator": 3}
    assert payload["top_supplier_keys"] == [f"GR:{S1}"]
    assert payload["unresolved_share"] == {"numerator": 0, "denominator": 3}


def test_a_unique_top_supplier_is_named_and_ties_list_every_supplier(pg_dsn: str) -> None:
    rows = (
        obs(1, "R1", "r1", day(1), "B1", sup(S2)),
        obs(2, "R2", "r2", day(1), "B1", sup(S2)),
        obs(3, "R3", "r3", day(1), "B1", sup(S1)),
        obs(4, "R4", "r4", day(1), "B1", sup(S3)),
    )
    payload = both(pg_dsn, rows)
    assert payload["top_supplier_keys"] == [f"GR:{S2}"] and payload["top_record_count"] == 2
    assert [row["supplier_key"] for row in payload["suppliers"]] == [
        f"GR:{S2}",
        f"GR:{S1}",
        f"GR:{S3}",
    ]


def test_equal_counts_are_ordered_by_supplier_key_not_by_arrival(pg_dsn: str) -> None:
    rows = (
        obs(1, "R1", "r1", day(1), "B1", sup(S2)),
        obs(2, "R2", "r2", day(1), "B1", sup(S1)),
    )
    payload = both(pg_dsn, rows)
    assert [row["supplier_key"] for row in payload["suppliers"]] == [f"GR:{S1}", f"GR:{S2}"]
    assert payload["top_supplier_keys"] == [f"GR:{S1}", f"GR:{S2}"]


def test_a_many_way_tie_is_ordered_by_supplier_key_whatever_the_arrival_order(
    pg_dsn: str,
) -> None:
    arrival = (S6, S5, S4, S3, S2, S1)
    rows = tuple(
        obs(i + 1, f"R{i}", f"r{i}", day(1), "B1", sup(tax)) for i, tax in enumerate(arrival)
    )
    payload = both(pg_dsn, rows)
    expected = [f"GR:{tax}" for tax in (S1, S2, S3, S4, S5, S6)]
    assert [row["supplier_key"] for row in payload["suppliers"]] == expected
    assert payload["top_supplier_keys"] == expected


def test_the_latest_observed_version_decides_the_suppliers_and_the_cutoff_applies(
    pg_dsn: str,
) -> None:
    rows = (
        obs(1, "X", "v1", day(1), "B1", sup(S1)),
        obs(2, "X", "v2", day(2), "B1", sup(S3)),
    )
    assert counts(both(pg_dsn, rows)) == {f"GR:{S3}": 1}
    assert counts(both(pg_dsn, rows, cutoff=day(1))) == {f"GR:{S1}": 1}


def test_a_later_version_can_move_a_record_to_another_buyer(pg_dsn: str) -> None:
    rows = (obs(1, "X", "v1", day(1), "B1", sup(S1)), obs(2, "X", "v2", day(2), "B2", sup(S1)))
    assert both(pg_dsn, rows)["status"] == "no_observed_buyer_records"
    assert both(pg_dsn, rows, buyer="B2")["buyer_records"] == 1
    assert both(pg_dsn, rows, cutoff=day(1))["buyer_records"] == 1


def test_a_b_a_reuses_the_last_observed_version(pg_dsn: str) -> None:
    rows = (
        obs(1, "X", "a", day(1), "B1", sup(S1)),
        obs(2, "X", "b", day(2), "B1", sup(S3)),
        obs(3, "X", "a", day(3), "B1", sup(S1)),
    )
    payload = both(pg_dsn, rows)
    assert counts(payload) == {f"GR:{S1}": 1}
    assert payload["records"][0]["observation_ids"] == [3]


def test_different_versions_tied_at_the_latest_time_are_ambiguous_and_never_counted(
    pg_dsn: str,
) -> None:
    rows = (
        obs(1, "X", "v1", day(1), "B1", sup(S1)),
        obs(2, "X", "v2", day(1), "B1", sup(S3)),
        obs(3, "Y", "y", day(1), "B1", sup(S2)),
    )
    payload = both(pg_dsn, rows)
    assert payload["ambiguous_source_ids"] == ["kimdis:X"]
    assert (payload["buyer_records"], payload["resolved_records"]) == (1, 1)
    assert counts(payload) == {f"GR:{S2}": 1}


def test_an_ambiguous_record_alone_leaves_the_selection_unresolved(pg_dsn: str) -> None:
    rows = (obs(1, "X", "v1", day(1), "B1", sup(S1)), obs(2, "X", "v2", day(1), "B1", sup(S3)))
    assert both(pg_dsn, rows)["status"] == "selection_unresolved"


def test_repeated_observation_of_one_version_counts_once(pg_dsn: str) -> None:
    rows = (obs(1, "X", "x", day(1), "B1", sup(S1)), obs(2, "X", "x", day(2), "B1", sup(S1)))
    payload = both(pg_dsn, rows)
    assert payload["buyer_records"] == 1 and payload["records"][0]["observation_ids"] == [2]


def test_cancellation_is_included_with_a_breakdown(pg_dsn: str) -> None:
    rows = (
        obs(1, "A", "a", day(1), "B1", sup(S1), True),
        obs(2, "B", "b", day(1), "B1", sup(S1), None),
        obs(3, "C", "c", day(1), "B1", sup(S1), False),
    )
    row = both(pg_dsn, rows)["suppliers"][0]
    assert (row["record_count"], row["cancelled_count"], row["unknown_cancellation_count"]) == (
        3,
        1,
        1,
    )


def test_the_statuses_of_an_empty_or_early_capture_and_a_buyer_without_records(
    pg_dsn: str,
) -> None:
    assert both(pg_dsn, ())["status"] == "empty_capture"
    early = datetime(2025, 12, 31, tzinfo=UTC)
    assert both(pg_dsn, example(), cutoff=early)["status"] == "no_observations_before_cutoff"
    assert both(pg_dsn, example(), buyer="NOBODY")["status"] == "no_observed_buyer_records"


def test_the_order_of_the_observations_does_not_change_the_result(pg_dsn: str) -> None:
    rows = example()
    forward = both(pg_dsn, rows)
    assert both(pg_dsn, tuple(reversed(rows))) == forward
    extra = replace(rows[0], observation_id=9)
    assert both(pg_dsn, (*reversed(rows), extra))["suppliers"] == forward["suppliers"]


@pytest.mark.parametrize("buyer", ["", " \t\r\n", 5, None])
def test_a_blank_or_non_text_buyer_is_refused(buyer: object) -> None:
    with pytest.raises(SemanticError, match="^semantic_selection$"):
        evaluate(example(), buyer=cast(str, buyer), cutoff=CUTOFF)


@pytest.mark.parametrize(
    "cutoff",
    [
        datetime(2026, 1, 10),
        datetime(2026, 1, 10, tzinfo=timezone(timedelta(hours=2))),
        "2026-01-10",
        None,
    ],
)
def test_a_naive_or_non_datetime_cutoff_is_refused(cutoff: object) -> None:
    with pytest.raises(SemanticError, match="^semantic_selection$"):
        evaluate(example(), buyer="B1", cutoff=cast(datetime, cutoff))


def test_observations_use_the_shared_validation_with_a_higher_bound() -> None:
    row = example()[0]
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(cast(tuple[Observation, ...], [row]), buyer="B1", cutoff=CUTOFF)
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate((row, row), buyer="B1", cutoff=CUTOFF)
    exactly = tuple(replace(row, observation_id=i + 1) for i in range(5000))
    assert evaluate(exactly, buyer="B1", cutoff=CUTOFF).status == "observed_concentration"
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(
            tuple(replace(row, observation_id=i + 1) for i in range(5001)),
            buyer="B1",
            cutoff=CUTOFF,
        )
    changed = replace(row, observation_id=2, cancelled=True)
    with pytest.raises(SemanticError, match="^semantic_version_conflict$"):
        evaluate((row, changed), buyer="B1", cutoff=CUTOFF)


def test_the_definition_is_bound_to_the_sql() -> None:
    value = definition()
    assert value["metric"] == "buyer_supplier_record_concentration.v1"
    assert value["status"] == "draft" and value["identity"] == "reported_identifier_only"
    assert value["measure"] == "record_participation_counts_not_money_not_market_share"
    assert value["sql_sha256"] == hashlib.sha256(reference_sql().encode()).hexdigest()
    assert definition_sha256() == definition_sha256() and len(definition_sha256()) == 64


def test_the_payload_is_plain_json() -> None:
    result: MetricResult = evaluate(example(), buyer="B1", cutoff=CUTOFF)
    text = json.dumps(result.payload(), allow_nan=False, sort_keys=True)
    assert json.loads(text) == result.payload()


def test_the_provider_imports_only_the_shared_pure_semantic_modules() -> None:
    from tests.test_semantics import imported_modules

    allowed = {
        "nima.semantics.selection",
        "nima.semantics.parties",
        "nima.semantics.participation",
    }
    for module in imported_modules("buyer_concentration.py"):
        assert module in allowed or not module.startswith(("nima.", "psycopg", "prefect", "httpx"))
    assert imported_modules("buyer_concentration.py") & allowed == allowed
