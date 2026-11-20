"""Pins of the first metric's exact output, taken from unmodified main (f574266).

V1-05 S3 moves record selection and party keys out of `participation` into shared modules.
These digests must stay green unchanged through that move: each is the SHA-256 of the canonical
JSON of the full result payload for one selection of the committed synthetic fixture, so any change
to a count, an evidence list, an ordering or a diagnostic breaks it. They do not prove the metric
is right; they prove it did not move.
"""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from nima.semantics.participation import (
    MetricResult,
    Observation,
    definition,
    definition_sha256,
    evaluate,
    reference_sql,
)
from tests.test_semantics import CUTOFF, TAX, fixture

DEFINITION_SHA256 = "7d8b5f8ecf6ae366482f4b06cd245f16d23408b489ad9bcb44af493282ac043f"
SQL_SHA256 = "85134c5d800350adfedf7dce6d995a36c48b194d919912695992f83369e11d5f"


def digest(result: MetricResult) -> str:
    text = json.dumps(result.payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def day(number: int) -> datetime:
    return datetime(2026, 1, number, tzinfo=UTC)


def a_b_a() -> tuple[Observation, ...]:
    rows = fixture()
    original, changed = rows[1], rows[-1]
    return (
        original,
        replace(changed, observed_at=day(2)),
        replace(original, observation_id=20, observed_at=CUTOFF),
    )


CASES = {
    "full": ("f26a5c2af2adca52e778f7f49b0141656d3ac611c8e607b1aaee57d7b9657dfc"),
    "cutoff_day1": ("3e5411051e91d7981d9cd47f08de4a6268c61e123b70080e39200d264415d0e4"),
    "cutoff_day2": ("06eee15ca85a69aa1d6493b8ef8dcc01ac0cbd44eb9d9f7a68fbd72bdb8e51cc"),
    "before_all": ("bbad8ed584dca2b9ae9431291ccf15d833435fab0d8dabe9a6adddd0d47f7cf7"),
    "reobserved_reversed": ("f3cafb1c7dfd0996e67061752f91273e9748473cb1a72b8c61ffa74d7bfd81da"),
    "a_b_a": ("6b3ea10a0083f991208374eb0d98b35926089908db281e8924dad0ef0b650fbe"),
    "other_tax_no_match": ("9aa0fede41e39a3dd03246308afe3ded22a779db9bec387607c64f124408cef8"),
    "empty": ("c4e6c238703e1a4b866a2ba4d14e374e08c426cfb559a7cd769a8d04e73b99a0"),
}


def selection(name: str) -> MetricResult:
    rows = fixture()
    if name == "full":
        return evaluate(rows, tax_id=TAX, cutoff=CUTOFF)
    if name == "cutoff_day1":
        return evaluate(rows, tax_id=TAX, cutoff=day(1))
    if name == "cutoff_day2":
        return evaluate(rows, tax_id=TAX, cutoff=day(2))
    if name == "before_all":
        return evaluate(rows, tax_id=TAX, cutoff=datetime(2025, 12, 31, tzinfo=UTC))
    if name == "reobserved_reversed":
        extra = replace(rows[2], observation_id=12)
        return evaluate((*reversed(rows), extra), tax_id=TAX, cutoff=CUTOFF)
    if name == "a_b_a":
        return evaluate(a_b_a(), tax_id=TAX, cutoff=CUTOFF)
    if name == "other_tax_no_match":
        return evaluate(rows, tax_id="987654321", cutoff=CUTOFF)
    return evaluate((), tax_id=TAX, cutoff=CUTOFF)


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_full_result_bytes_of_each_selection_have_not_moved(name: str) -> None:
    assert digest(selection(name)) == CASES[name]


def test_the_definition_and_its_reference_sql_have_not_moved() -> None:
    assert definition_sha256() == DEFINITION_SHA256
    assert definition()["sql_sha256"] == SQL_SHA256
    assert hashlib.sha256(reference_sql().encode()).hexdigest() == SQL_SHA256
