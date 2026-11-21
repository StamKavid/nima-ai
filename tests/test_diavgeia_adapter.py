"""Diavgeia adapter rules beyond the shared conformance suite, on synthetic pages only."""

import json
from typing import Any

import pytest

from nima.sources.base import QueryPayload, SourcePageError, checked_request
from nima.sources.diavgeia import DiavgeiaAdapter, DiavgeiaQuery
from tests.diavgeia_samples import award, decision, search_page

ADAPTER = DiavgeiaAdapter(DiavgeiaQuery("99999", "2026-01-01", "2026-01-30"))


def page(*decisions: Any, total: int | None = None, number: int = 0, size: int = 100) -> bytes:
    count = len(decisions) if total is None else total
    return search_page(number, count, size, list(decisions))


def only(raw: bytes) -> dict[str, Any]:
    result = ADAPTER.normalize_page(raw)
    assert len(result.records) == 1 and not result.issues
    return dict(result.records[0].normalized)


def reason(raw: bytes) -> str:
    result = ADAPTER.normalize_page(raw)
    assert not result.records and len(result.issues) == 1
    return result.issues[0].reason


def test_all_three_statuses_are_kept_as_observed() -> None:
    for status in ("PUBLISHED", "PENDING_REVOCATION", "REVOKED"):
        assert only(page(decision(status=status)))["status"] == status


@pytest.mark.parametrize("status", ["revoked", "", None, 3, "ALL"])
def test_any_other_status_is_quarantined_with_a_fixed_reason(status: object) -> None:
    assert reason(page(decision(status=status))) == "unsupported_status"


def test_the_ada_is_kept_exactly_and_look_alike_letters_stay_different() -> None:
    greek, latin = "ΒΛΕΖΝ-Ρ7Ν", "BΛEZN-P7N"
    assert greek != latin
    ids = ADAPTER.normalize_page(page(decision(greek), decision(latin))).source_ids
    assert ids == (f"diavgeia:{greek}", f"diavgeia:{latin}")


@pytest.mark.parametrize(
    "ada", [None, "", " ", " ΑΒ-1", "ΑΒ-1 ", "ΑΒ 1", "ΑΒ/1", "ΑΒ--1", "-ΑΒ", "ΑΒ-", "A" * 65, 7]
)
def test_an_ada_with_whitespace_or_odd_shape_is_quarantined(ada: object) -> None:
    assert reason(page(decision(ada=ada))) == "invalid_ada"


def test_a_valid_ada_of_a_quarantined_record_still_counts_as_seen() -> None:
    result = ADAPTER.normalize_page(page(decision("ΑΒ-1", status="BOGUS"), decision(ada=None)))
    assert result.source_ids == ("diavgeia:ΑΒ-1",)
    assert [issue.index for issue in result.issues] == [0, 1]


def test_the_exact_digits_of_an_amount_are_part_of_the_content_hash() -> None:
    hashes = {
        ADAPTER.normalize_page(page(decision(extraFieldValues=award(text))))
        .records[0]
        .content_sha256
        for text in ("12.5", "12.50", "12.500")
    }
    assert len(hashes) == 3


def test_a_new_version_is_the_same_record_with_new_content() -> None:
    first = ADAPTER.normalize_page(page(decision(versionId="v1"))).records[0]
    second = ADAPTER.normalize_page(page(decision(versionId="v2"))).records[0]
    assert first.source_id == second.source_id
    assert first.content_sha256 != second.content_sha256
    assert second.normalized["version_id"] == "v2"


def test_persons_are_reduced_to_a_count_and_their_tax_number_types() -> None:
    extra = {
        "person": [
            {"afm": "123456789", "afmType": "T1", "name": "Secret Name A", "afmCountry": "GR"},
            {"afm": "987654321", "afmType": "T2", "name": "Secret Name B"},
            {"afm": "555555555", "afmType": "T1", "name": "Secret Name C"},
        ]
    }
    record = only(page(decision(extraFieldValues=extra)))
    assert record["person_count"] == 3 and record["person_types"] == ["T1", "T2"]
    text = json.dumps(record, ensure_ascii=False)
    for leaked in ("123456789", "987654321", "555555555", "Secret Name", "afmCountry"):
        assert leaked not in text


@pytest.mark.parametrize("persons", ["x", {"a": 1}, [1], [None]])
def test_a_malformed_person_list_is_quarantined(persons: object) -> None:
    assert reason(page(decision(extraFieldValues={"person": persons}))) == "invalid_persons"


def test_an_award_without_persons_or_amount_keeps_unknowns_unknown() -> None:
    record = only(page(decision()))
    assert record["award_amount"] is None and record["award_currency"] is None
    assert record["person_count"] == 0 and record["person_types"] == []
    assert record["related_ada"] is None and record["corrected_version_id"] is None


def test_the_amount_is_exact_decimal_text_with_its_currency() -> None:
    record = only(page(decision(extraFieldValues=award("123456789012345678.90"))))
    assert record["award_amount"] == "123456789012345678.90"
    assert record["award_currency"] == "EUR"
    assert only(page(decision(extraFieldValues=award("5"))))["award_amount"] == "5"


@pytest.mark.parametrize("amount", ["12.5", True, None, [1]])
def test_a_non_numeric_amount_is_quarantined(amount: object) -> None:
    raw = page(decision(extraFieldValues={"awardAmount": {"amount": amount}}))
    assert reason(raw) == "invalid_award_amount"


def test_an_amount_with_an_extreme_exponent_is_quarantined_not_expanded() -> None:
    for text in ("1e999999999", "1e31", "1e-31"):
        raw = page(decision(extraFieldValues=award(text)))
        assert reason(raw) == "invalid_award_amount"
    assert only(page(decision(extraFieldValues=award("1e30"))))["award_amount"] == "1" + "0" * 30


def test_an_award_amount_that_is_not_an_object_is_quarantined() -> None:
    assert reason(page(decision(extraFieldValues={"awardAmount": 5}))) == "invalid_award_amount"


def test_the_private_data_flag_is_kept_and_must_be_boolean() -> None:
    assert only(page(decision(privateData=True)))["private_data"] is True
    assert only(page(decision(privateData=None)))["private_data"] is None
    assert reason(page(decision(privateData="yes"))) == "invalid_private_data"


@pytest.mark.parametrize("field", ["issueDate", "submissionTimestamp"])
@pytest.mark.parametrize("value", [-1, 1.5, "1767225600000", True])
def test_timestamps_must_be_non_negative_integers(field: str, value: object) -> None:
    assert reason(page(decision(**{field: value}))) == "invalid_timestamp"


def test_absent_timestamps_and_texts_are_unknown_not_errors() -> None:
    record = only(page({"ada": "ΑΒ-1", "status": "PUBLISHED", "versionId": "v1"}))
    assert record["issue_timestamp_ms"] is None and record["organization_id"] is None
    assert record["decision_type"] is None and record["private_data"] is None


@pytest.mark.parametrize("field", ["decisionTypeId", "organizationId", "correctedVersionId"])
def test_present_text_fields_must_be_nonblank_text(field: str) -> None:
    for value in ("", "  ", 5):
        assert reason(page(decision(**{field: value}))) == "invalid_text_field"


@pytest.mark.parametrize("version", [None, "", " ", 3])
def test_the_version_id_is_required(version: object) -> None:
    assert reason(page(decision(versionId=version))) == "invalid_version_id"


def test_a_related_ada_is_a_reference_and_must_be_a_valid_ada() -> None:
    record = only(page(decision(extraFieldValues={"textRelatedADA": "ΓΔ-2"})))
    assert record["related_ada"] == "ΓΔ-2"
    assert reason(page(decision(extraFieldValues={"textRelatedADA": "bad ada"}))) == "invalid_ada"
    assert reason(page(decision(extraFieldValues=[1]))) == "invalid_extra_fields"


def test_a_decision_that_is_not_an_object_is_quarantined_not_fatal() -> None:
    result = ADAPTER.normalize_page(page("text", None, decision("ΑΒ-1")))
    assert [i.reason for i in result.issues] == ["record_not_an_object"] * 2
    assert [r.index for r in result.records] == [2]
    assert len(result.record_hashes) == 3


def test_an_empty_result_is_one_valid_empty_page() -> None:
    result = ADAPTER.normalize_page(search_page(0, 0, 100, []))
    assert (result.total_records, result.total_pages, result.last, result.record_count) == (
        0,
        0,
        True,
        0,
    )


def test_a_short_last_page_and_a_middle_page_report_their_position() -> None:
    last = ADAPTER.normalize_page(search_page(1, 3, 2, [decision("ΑΒ-3")]))
    assert (last.number, last.total_pages, last.last) == (1, 2, True)
    middle = ADAPTER.normalize_page(search_page(0, 3, 2, [decision("ΑΒ-1"), decision("ΑΒ-2")]))
    assert (middle.number, middle.total_pages, middle.last) == (0, 2, False)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"[]",
        b"3",
        b'{"info": 1, "decisions": []}',
        b'{"info": {"page": 0, "size": 1, "total": 0}}',
        b'{"decisions": []}',
        b'{"info": {"page": 0, "size": 1, "total": 0}, "decisions": {}}',
        b'{"info": {"page": 0, "size": 1, "total": NaN}, "decisions": []}',
        b'{"info": {"page": 0, "size": 1, "total": 0}, "decisions": [], "decisions": []}',
        search_page(5, 2, 1, []),
        search_page(0, 1, 1, [decision("ΑΒ-1"), decision("ΑΒ-2")]),
        search_page(0, 2, 1, []),
        search_page(2, 2, 1, [decision("ΑΒ-1")]),
        search_page(0, 0, 0, []),
        search_page(-1, 0, 1, []),
        search_page(0, -1, 1, []),
        search_page(0, 1, True, [decision("ΑΒ-1")]),
        search_page(0, 1.5, 1, [decision("ΑΒ-1")]),
    ],
)
def test_a_damaged_envelope_stops_the_page(raw: bytes) -> None:
    with pytest.raises(SourcePageError):
        ADAPTER.normalize_page(raw)


def test_a_deeply_nested_record_stops_the_page() -> None:
    nested = "[" * 80 + "]" * 80
    raw = (
        '{"info": {"page": 0, "size": 1, "total": 1}, "decisions": [{"ada": "ΑΒ-1", "x": '
        + nested
        + "}]}"
    ).encode()
    with pytest.raises(SourcePageError):
        ADAPTER.normalize_page(raw)


def test_the_size_limit_is_inclusive() -> None:
    raw = page(decision("ΑΒ-1"))
    assert ADAPTER.normalize_page(raw, max_bytes=len(raw)).record_count == 1
    with pytest.raises(SourcePageError):
        ADAPTER.normalize_page(raw, max_bytes=len(raw) - 1)


def test_the_request_is_the_documented_search_for_one_organisation_and_window() -> None:
    request = checked_request(ADAPTER, 3)
    assert request.method == "GET" and request.json is None
    assert request.params == {
        "org": "99999",
        "type": "Δ.2.2",
        "from_issue_date": "2026-01-01",
        "to_issue_date": "2026-01-30",
        "status": "all",
        "page": 3,
        "size": 100,
    }


def test_an_adapter_without_a_query_refuses_to_describe_or_request_one() -> None:
    with pytest.raises(ValueError, match="without a query"):
        DiavgeiaAdapter().query_payload()


@pytest.mark.parametrize(
    ("first", "last"),
    [("2026-01-01", "2026-01-30"), ("2026-02-15", "2026-02-15"), ("2026-01-31", "2026-03-01")],
)
def test_a_window_of_one_to_thirty_days_is_accepted(first: str, last: str) -> None:
    assert DiavgeiaQuery("9", first, last).payload()["fromIssueDate"] == first


@pytest.mark.parametrize(
    ("first", "last"),
    [
        ("2026-01-01", "2026-01-31"),
        ("2026-01-02", "2026-01-01"),
        ("2026-1-01", "2026-01-02"),
        ("2026-02-30", "2026-03-01"),
        ("20260101", "20260102"),
        ("", "2026-01-02"),
    ],
)
def test_a_window_that_is_long_reversed_or_malformed_is_refused(first: str, last: str) -> None:
    with pytest.raises(ValueError):
        DiavgeiaQuery("9", first, last)


def test_a_date_that_is_not_text_is_refused() -> None:
    with pytest.raises(ValueError, match="date"):
        DiavgeiaQuery("9", 20260101, "2026-01-02")  # type: ignore[arg-type]


@pytest.mark.parametrize("organization", ["", "a b", "x" * 33, "../1", "é"])
def test_an_unsafe_organisation_is_refused(organization: str) -> None:
    with pytest.raises(ValueError, match="organization"):
        DiavgeiaQuery(organization, "2026-01-01", "2026-01-02")


def test_a_saved_run_is_rebuilt_only_from_its_exact_canonical_payload() -> None:
    saved = DiavgeiaQuery("99999", "2026-01-01", "2026-01-30").payload()
    rebuilt = DiavgeiaAdapter.from_payload(saved)
    assert rebuilt.query_payload() == saved
    assert rebuilt.request_for(0) == ADAPTER.request_for(0)
    for bad in (
        {**saved, "extra": 1},
        {**saved, "size": 500},
        {**saved, "status": "published"},
        {**saved, "decisionType": "Β.1.3"},
        {k: v for k, v in saved.items() if k != "size"},
        {**saved, "organization": 5},
        {**saved, "fromIssueDate": 5},
        {**saved, "toIssueDate": None},
    ):
        with pytest.raises(ValueError):
            DiavgeiaAdapter.from_payload(bad)


def test_the_query_payload_is_copied_so_a_caller_cannot_change_a_run() -> None:
    adapter = DiavgeiaAdapter(QueryPayload(ADAPTER.query_payload()))
    adapter.query_payload()["organization"] = "other"
    assert adapter.query_payload()["organization"] == "99999"
