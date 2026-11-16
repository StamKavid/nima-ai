"""Hand-labelled publication counts, independently checked by real PostgreSQL."""

import ast
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest
from psycopg.types.json import Jsonb

from nima.semantics.participation import (
    Observation,
    SemanticError,
    Supplier,
    definition,
    definition_sha256,
    evaluate,
    reference_sql,
    sql_rows,
    valid_tax_id,
)

TAX = "012345678"
CUTOFF = datetime(2026, 1, 3, tzinfo=UTC)


def fixture() -> tuple[Observation, ...]:
    value = json.loads(Path("tests/fixtures/participation.json").read_text())
    return tuple(
        Observation(
            row["id"],
            f"kimdis:{row['record']}",
            "kimdis-normalized-v1",
            hashlib.sha256(row["version"].encode()).hexdigest(),
            datetime(2026, 1, row["day"], tzinfo=UTC),
            row["buyer"],
            row["cancelled"],
            tuple(Supplier(i, tax, country) for i, (tax, country) in enumerate(row["suppliers"])),
        )
        for row in value["observations"]
    )


def sql_result(dsn: str, rows: tuple[Observation, ...], cutoff: datetime = CUTOFF) -> Any:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(reference_sql(), (Jsonb(sql_rows(rows)), cutoff, TAX)).fetchone()
    assert row is not None
    return row[0]


def test_known_answer_and_evidence_sets(pg_dsn: str) -> None:
    rows = fixture()
    result = cast(dict[str, Any], evaluate(rows, tax_id=TAX, cutoff=CUTOFF).payload())
    expected = json.loads(Path("tests/fixtures/participation.json").read_text())["expected"]
    assert {row["buyer_key"]: row["source_ids"] for row in result["buyers"]} == expected["buyers"]
    assert result["unassigned_source_ids"] == expected["unassigned"]
    assert result["total"] == 5
    assert result["cancelled_count"] == 1
    assert result["unknown_cancellation_count"] == 1
    assert result["not_cancelled_count"] == 3
    assert result["unassessed_source_ids"] == expected["unassessed"]
    assert result["ambiguous_source_ids"] == expected["ambiguous"]
    decisions = {row["source_id"]: row for row in result["records"]}
    assert decisions["kimdis:C"]["matching_ordinals"] == [0, 2]
    assert decisions["kimdis:A"]["observation_ids"] == [3]
    assert decisions["kimdis:B"]["matching_ordinals"] == []
    assert sql_result(pg_dsn, rows) == result


def test_cutoff_is_applied_before_revision_selection(pg_dsn: str) -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    result = cast(dict[str, Any], evaluate(fixture(), tax_id=TAX, cutoff=cutoff).payload())
    assert result["total"] == 2
    assert result["buyers"][0]["source_ids"] == ["kimdis:A", "kimdis:B"]
    assert sql_result(pg_dsn, fixture(), cutoff) == result


def test_order_and_reobservation_do_not_change_count(pg_dsn: str) -> None:
    rows = fixture()
    extra = replace(rows[2], observation_id=12)
    extended = (*reversed(rows), extra)
    result = evaluate(extended, tax_id=TAX, cutoff=CUTOFF).payload()
    assert result["total"] == 5
    assert sql_result(pg_dsn, extended) == result
    assert evaluate(tuple(reversed(extended)), tax_id=TAX, cutoff=CUTOFF).payload() == result


def test_a_b_a_reuses_the_last_captured_version(pg_dsn: str) -> None:
    rows = fixture()
    original, changed = rows[1], rows[-1]
    reverted = replace(original, observation_id=20, observed_at=CUTOFF)
    sequence = (original, replace(changed, observed_at=datetime(2026, 1, 2, tzinfo=UTC)), reverted)
    result = cast(dict[str, Any], evaluate(sequence, tax_id=TAX, cutoff=CUTOFF).payload())
    assert result["total"] == 1
    assert result["records"][0]["version_hashes"] == [original.content_sha256]
    assert sql_result(pg_dsn, sequence) == result


@pytest.mark.parametrize(
    ("tax", "country", "buyer", "cancelled", "total", "unassessed", "invalid"),
    [
        (" \t012345678\r\n\f\v", " EL\t", " B1\t", None, 1, False, 0),
        (TAX, "GR", " \t", False, 1, False, 0),
        (TAX, "gr", "B1", False, 0, True, 0),
        (TAX, "DE", "B1", False, 0, True, 0),
        (TAX, None, "B1", False, 0, True, 0),
        ("\u00a0" + TAX, "GR", "B1", False, 0, False, 1),
        ("０１２３４５６７８", "GR", "B1", False, 0, False, 1),
        ("000000000", "GR", "B1", False, 0, False, 1),
        (None, "GR", "B1", False, 0, False, 1),
    ],
)
def test_reported_key_rules_match_sql(
    pg_dsn: str,
    tax: str | None,
    country: str | None,
    buyer: str,
    cancelled: bool | None,
    total: int,
    unassessed: bool,
    invalid: int,
) -> None:
    row = replace(
        fixture()[0], buyer_key=buyer, cancelled=cancelled, suppliers=(Supplier(0, tax, country),)
    )
    result = evaluate((row,), tax_id=TAX, cutoff=CUTOFF)
    assert result.total == total
    assert bool(result.unassessed_source_ids) == unassessed
    assert result.invalid_supplier_count == invalid
    assert sql_result(pg_dsn, (row,)) == result.payload()


@pytest.mark.parametrize(
    "suppliers,status", [(None, "selection_unresolved"), ((), "no_observed_participation")]
)
def test_unknown_and_empty_lists_are_distinct(
    pg_dsn: str,
    suppliers: None | tuple[Supplier, ...],
    status: str,
) -> None:
    rows = (replace(fixture()[0], suppliers=suppliers),)
    result = evaluate(rows, tax_id=TAX, cutoff=CUTOFF)
    assert result.status == status
    assert result.unknown_supplier_source_ids == (("kimdis:A",) if suppliers is None else ())
    assert result.empty_supplier_source_ids == (("kimdis:A",) if suppliers == () else ())
    assert sql_result(pg_dsn, rows) == result.payload()


def test_empty_capture_and_no_capture_before_cutoff(pg_dsn: str) -> None:
    for rows, cutoff, status in [
        ((), CUTOFF, "empty_capture"),
        (fixture(), datetime(2025, 1, 1, tzinfo=UTC), "no_observations_before_cutoff"),
    ]:
        result = evaluate(rows, tax_id=TAX, cutoff=cutoff)
        assert result.status == status
        assert sql_result(pg_dsn, rows, cutoff) == result.payload()


def test_tied_unrelated_revisions_are_visible_without_selected_key_claim(pg_dsn: str) -> None:
    original = replace(fixture()[0], suppliers=(Supplier(0, "987654321", "GR"),))
    tied = replace(original, observation_id=2, content_sha256="b" * 64)
    rows = (original, tied)
    result = evaluate(rows, tax_id=TAX, cutoff=CUTOFF)
    assert result.status == "no_observed_participation"
    assert result.ambiguous_source_ids == ("kimdis:A",)
    assert result.records[0].buyer_key is None
    assert sql_result(pg_dsn, rows) == result.payload()


@pytest.mark.parametrize(
    "tax", [True, 123456789, None, "000000000", "０１２３４５６７８", "12345678", TAX + "\n"]
)
def test_request_identifier_must_be_exact_ascii_nonzero(tax: object) -> None:
    assert not valid_tax_id(tax)
    with pytest.raises(SemanticError, match="^semantic_selection$"):
        evaluate((), tax_id=cast(str, tax), cutoff=CUTOFF)


@pytest.mark.parametrize(
    "changes",
    [
        {"observation_id": True},
        {"observation_id": 0},
        {"source_id": "other:A"},
        {"source_id": "kimdis:"},
        {"normalizer_version": "future"},
        {"content_sha256": "bad"},
        {"observed_at": datetime(2026, 1, 1)},
        {"buyer_key": 1},
        {"cancelled": 0},
        {"suppliers": []},
        {"suppliers": (Supplier(1, TAX, "GR"),)},
        {"suppliers": (Supplier(0, cast(str, 1), "GR"),)},
        {"suppliers": (Supplier(0, TAX, cast(str, 1)),)},
    ],
)
def test_invalid_domain_rows_fail_with_fixed_reason(changes: dict[str, Any]) -> None:
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate((replace(fixture()[0], **changes),), tax_id=TAX, cutoff=CUTOFF)


def test_conflicting_versions_and_duplicate_observation_ids_are_refused() -> None:
    row = fixture()[0]
    with pytest.raises(SemanticError, match="^semantic_version_conflict$"):
        evaluate(
            (row, replace(row, observation_id=2, buyer_key="changed")), tax_id=TAX, cutoff=CUTOFF
        )
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate((row, row), tax_id=TAX, cutoff=CUTOFF)


def test_definition_and_packaged_sql_are_bound_to_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    from nima.semantics import participation

    assert definition()["status"] == "draft"
    assert definition()["metric"] == "captured_contract_record_count.v1"
    assert reference_sql() == files("nima.semantics").joinpath("participation.sql").read_text()
    digest = definition_sha256()
    assert len(digest) == 64 and digest == definition_sha256()
    sql = reference_sql()
    monkeypatch.setattr(participation, "reference_sql", lambda: sql + "\n-- changed definition\n")
    assert definition_sha256() != digest


def test_provider_bounds_and_dependency_direction() -> None:
    row = fixture()[0]
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate(cast(tuple[Observation, ...], []), tax_id=TAX, cutoff=CUTOFF)
    with pytest.raises(SemanticError, match="^semantic_input$"):
        evaluate((row,) * 501, tax_id=TAX, cutoff=CUTOFF)
    source = files("nima.semantics").joinpath("participation.py").read_text()
    imports = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    for node in imports:
        modules = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        assert all(
            not module.startswith(("nima.", "psycopg", "prefect", "httpx")) for module in modules
        )


def test_matching_and_unassessed_occurrences_can_coexist(pg_dsn: str) -> None:
    row = replace(fixture()[0], suppliers=(Supplier(0, TAX, "GR"), Supplier(1, TAX, None)))
    result = evaluate((row,), tax_id=TAX, cutoff=CUTOFF)
    assert result.total == 1 and result.unassessed_source_ids == ("kimdis:A",)
    assert result.records[0].matching_ordinals == (0,)
    assert sql_result(pg_dsn, (row,)) == result.payload()


def test_unicode_source_and_buyer_keys_have_deterministic_order(pg_dsn: str) -> None:
    rows = tuple(
        replace(fixture()[0], observation_id=i + 1, source_id=f"kimdis:{key}", buyer_key="Α")
        for i, key in enumerate(("Ω", "A", "α", "Z"))
    )
    result = evaluate(rows, tax_id=TAX, cutoff=CUTOFF)
    assert result.buyers[0].source_ids == ("kimdis:A", "kimdis:Z", "kimdis:Ω", "kimdis:α")
    assert sql_result(pg_dsn, rows) == result.payload()
