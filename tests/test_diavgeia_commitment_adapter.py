"""The Β.1.3 commitment adapter, on synthetic pages only. No request is made."""

import json
from collections.abc import Mapping
from typing import Any

import pytest

from nima.sources.base import SourcePageError
from nima.sources.diavgeia import DiavgeiaAdapter, DiavgeiaQuery
from nima.sources.diavgeia_commitments import CommitmentAdapter, CommitmentQuery
from tests.diavgeia_samples import commitment, decision, search_page

ADA = "ΑΒΓΔΕ-ΖΗ1"


def adapter() -> CommitmentAdapter:
    return CommitmentAdapter(CommitmentQuery("6057", "2026-10-25", "2026-10-27"))


def one(extra: dict[str, Any] | None = None, **fields: Any) -> Mapping[str, object]:
    row = decision(ADA, decisionTypeId="Β.1.3", extraFieldValues=extra or {}, **fields)
    page = adapter().normalize_page(search_page(0, 1, 100, [row]))
    assert not page.issues, page.issues
    return page.records[0].normalized


def reason(extra: dict[str, Any]) -> str:
    row = decision(ADA, decisionTypeId="Β.1.3", extraFieldValues=extra)
    page = adapter().normalize_page(search_page(0, 1, 100, [row]))
    assert not page.records and len(page.issues) == 1
    return page.issues[0].reason


def test_the_query_asks_for_commitments_and_the_award_query_is_unchanged() -> None:
    assert adapter().query_payload()["decisionType"] == "Β.1.3"
    assert adapter().request_for(0).params["type"] == "Β.1.3"
    award = DiavgeiaAdapter(DiavgeiaQuery("6", "2026-10-08", "2026-11-06"))
    assert award.query_payload()["decisionType"] == "Δ.2.2"


def test_identity_keeps_the_diavgeia_namespace_with_its_own_versions() -> None:
    assert adapter().name == DiavgeiaAdapter.name == "diavgeia"
    assert CommitmentAdapter.connector_version != DiavgeiaAdapter.connector_version
    assert CommitmentAdapter.normalizer_version != DiavgeiaAdapter.normalizer_version


def test_a_saved_query_rebuilds_only_for_its_own_type() -> None:
    payload = adapter().query_payload()
    assert CommitmentAdapter.from_payload(payload).query_payload() == payload
    award_payload = DiavgeiaQuery("6057", "2026-10-25", "2026-10-27").payload()
    with pytest.raises(ValueError):
        CommitmentAdapter.from_payload(award_payload)
    with pytest.raises(ValueError):
        DiavgeiaAdapter.from_payload(payload)


def test_a_commitment_keeps_its_closed_set_of_fields() -> None:
    record = one(commitment("1234.50", relatedPartialADA="ΩΨΧΦΥ-ΤΣ2"))
    assert record["ada"] == ADA and record["decision_type"] == "Β.1.3"
    assert record["financial_year"] == 2026 and record["budget_type"] == "ΤΑΚΤΙΚΟΣ"
    assert record["entry_number"] == 17 and record["partial_ada"] is False
    assert record["amount_with_vat"] == "1234.50" and record["amount_currency"] == "EUR"
    assert record["kae_lines"] == [{"kae": "2420", "amount_with_vat": "1234.50"}]
    assert record["related_partial_ada"] == "ΩΨΧΦΥ-ΤΣ2" and record["supplier_count"] == 1


def test_suppliers_are_a_count_and_no_name_or_tax_number_is_kept() -> None:
    record = one(commitment("10", lines=3))
    assert record["supplier_count"] == 3
    text = json.dumps(record, ensure_ascii=False)
    assert "SUPPLIER NAME" not in text and "000000000" not in text and "afm" not in text.lower()


def test_only_lines_that_name_a_supplier_count() -> None:
    lines = [{"kae": "1"}, {"kae": "2", "sponsorAFMName": {"afm": "1"}}, {"kae": "3"}]
    record = one({"amountWithKae": lines})
    assert record["supplier_count"] == 1 and len(record["kae_lines"]) == 3  # type: ignore[arg-type]


def test_absent_fields_are_unknown_not_errors() -> None:
    record = one({})
    for key in (
        "financial_year",
        "budget_type",
        "entry_number",
        "partial_ada",
        "amount_with_vat",
        "amount_currency",
        "related_partial_ada",
    ):
        assert record[key] is None
    assert record["kae_lines"] == [] and record["supplier_count"] == 0


def test_an_empty_related_reference_means_none_and_a_bad_one_is_quarantined() -> None:
    assert one({"relatedPartialADA": ""})["related_partial_ada"] is None
    assert reason({"relatedPartialADA": "a b"}) == "invalid_ada"
    assert reason({"relatedPartialADA": 5}) == "invalid_ada"


def test_amounts_keep_their_exact_digits_and_a_bare_number_is_accepted() -> None:
    assert one({"amountWithVAT": "@@0.10@@"})["amount_with_vat"] == "0.10"
    assert one({"amountWithVAT": {"currency": "EUR"}})["amount_with_vat"] is None
    assert one({"amountWithVAT": {"currency": "EUR"}})["amount_currency"] == "EUR"
    big = one(commitment("123456789012345678.90"))
    assert big["amount_with_vat"] == "123456789012345678.90"


@pytest.mark.parametrize(
    "extra",
    [
        {"amountWithVAT": "ten"},
        {"amountWithVAT": True},
        {"amountWithVAT": {"amount": "@@1e99@@"}},
        {"amountWithVAT": {"amount": "5"}},
        {"amountWithKae": [{"amountWithVAT": "ten"}]},
    ],
)
def test_a_bad_amount_is_quarantined(extra: dict[str, Any]) -> None:
    assert reason(extra) == "invalid_award_amount"


@pytest.mark.parametrize(
    ("extra", "why"),
    [
        ({"partialead": "yes"}, "invalid_partial_flag"),
        ({"financialYear": True}, "invalid_financial_year"),
        ({"financialYear": -1}, "invalid_financial_year"),
        ({"entryNumber": " "}, "invalid_entry_number"),
        ({"entryNumber": 1.5}, "invalid_entry_number"),
        ({"budgettype": " "}, "invalid_text_field"),
        ({"amountWithKae": "x"}, "invalid_kae_lines"),
        ({"amountWithKae": [1]}, "invalid_kae_lines"),
        ({"amountWithKae": [{"kae": " "}]}, "invalid_text_field"),
    ],
)
def test_a_shape_that_does_not_match_quarantines_one_record_with_a_fixed_reason(
    extra: dict[str, Any], why: str
) -> None:
    assert reason(extra) == why


def test_year_and_entry_number_are_kept_as_published() -> None:
    record = one({"financialYear": "2026", "entryNumber": "17/B"})
    assert record["financial_year"] == "2026" and record["entry_number"] == "17/B"


def test_a_changed_version_is_a_new_content_hash_for_the_same_source_id() -> None:
    def hash_of(version: str) -> tuple[str, str]:
        row = decision(ADA, decisionTypeId="Β.1.3", versionId=version, extraFieldValues={})
        record = adapter().normalize_page(search_page(0, 1, 100, [row])).records[0]
        return record.source_id, record.content_sha256

    (first_id, first), (second_id, second) = hash_of("v1"), hash_of("v2")
    assert first_id == second_id == f"diavgeia:{ADA}" and first != second


def test_the_shared_envelope_rules_still_apply() -> None:
    with pytest.raises(SourcePageError):
        adapter().normalize_page(b'{"content": 1}')
    with pytest.raises(SourcePageError):
        adapter().normalize_page(search_page(0, 5, 100, []))
