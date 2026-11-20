"""The GEMI search response is parsed into one outcome per queried AFM, never a chosen company.

Synthetic bodies only; they follow the provider's published schema and the live behaviour seen on
2026-11-20 (the registry number as a JSON string, `resultsSize` declared as a string, and a 404
instead of an empty list when no company matches).
"""

import hashlib
import json

import pytest

from nima.sources.gemi import InvalidProfile, normalize_profile
from nima.sources.gemi_search import SearchResult, parse_search, queryable_afm

AFM = "012345678"


def company(number: object = "1001", afm: object = AFM, **changes: object) -> dict[str, object]:
    return {
        "arGemi": number,
        "afm": afm,
        "coNameEl": "Άλφα ΑΕ",
        "autoRegistered": False,
        "coNamesEn": [],
        "legalType": {"id": 0, "descr": "ΜΟΡΦΗ"},
        "activities": [
            {"activity": {"id": "1", "descr": "Δ", "kadVersion": "kad_2026"}, "type": "Κύρια"}
        ],
        **changes,
    }


def body(
    companies: list[dict[str, object]],
    *,
    total: object = None,
    offset: object = 0,
    size: object = None,
) -> bytes:
    return json.dumps(
        {
            "searchMetadata": {
                "totalCount": len(companies) if total is None else total,
                "resultsOffset": offset,
                "resultsSize": str(len(companies)) if size is None else size,
            },
            "searchResults": companies,
        },
        ensure_ascii=False,
    ).encode()


def custom(meta: object, results: object = None, *, drop_results: bool = False) -> bytes:
    document: dict[str, object] = {"searchMetadata": meta}
    if not drop_results:
        document["searchResults"] = [company()] if results is None else results
    return json.dumps(document, ensure_ascii=False).encode()


def meta(**changes: object) -> dict[str, object]:
    return {"totalCount": 1, "resultsOffset": 0, "resultsSize": "1", **changes}


def parse(raw: bytes, afm: str = AFM, status: int = 200) -> SearchResult:
    return parse_search(raw, queried_afm=afm, http_status=status)


def test_the_five_outcomes_of_the_spec_example() -> None:
    single = parse(body([company("1001")]))
    assert (single.outcome, single.truncated, single.total_count) == ("hit_single", False, 1)
    assert [(h.company.source_id, h.afm_matches) for h in single.hits] == [("gemi:1001", True)]

    multiple = parse(body([company("1001"), company("1002")]))
    assert (multiple.outcome, multiple.truncated, multiple.total_count) == (
        "hit_multiple",
        False,
        2,
    )
    assert [(h.company.source_id, h.afm_matches) for h in multiple.hits] == [
        ("gemi:1001", True),
        ("gemi:1002", True),
    ]

    missing = parse(b"", status=404)
    assert (missing.outcome, missing.hits, missing.total_count) == (
        "not_found_at_observation",
        (),
        None,
    )

    mismatch = parse(body([company("1003", afm="987654321")]))
    assert (mismatch.outcome, [h.afm_matches for h in mismatch.hits]) == ("afm_mismatch", [False])

    cut = parse(body([company("1004"), company("1005")], total=3))
    assert (cut.outcome, cut.truncated, cut.total_count) == ("truncated", True, 3)
    assert [h.afm_matches for h in cut.hits] == [True, True]


def test_the_response_hash_covers_the_exact_bytes_and_a_404_body_is_not_read() -> None:
    raw = body([company()])
    assert parse(raw).response_sha256 == hashlib.sha256(raw).hexdigest()
    odd = b"\xff not json at all"
    result = parse(odd, status=404)
    assert result.outcome == "not_found_at_observation"
    assert result.response_sha256 == hashlib.sha256(odd).hexdigest()


def test_pointers_locate_each_value_inside_the_original_search_body() -> None:
    result = parse(body([company("1001"), company("1002")]))
    second = result.hits[1].company
    assert second.fields["registry_number"].json_pointer == "/searchResults/1/arGemi"
    assert second.fields["reported_afm"].json_pointer == "/searchResults/1/afm"
    assert second.fields["legal_type_id"].json_pointer == "/searchResults/1/legalType/id"
    assert second.activities_pointer == "/searchResults/1/activities"
    assert second.activities is not None
    assert second.activities[0]["version"].json_pointer == (
        "/searchResults/1/activities/0/activity/kadVersion"
    )
    assert second.response_sha256 == result.response_sha256


@pytest.mark.parametrize("number", ["1001", 1001])
def test_the_registry_number_may_be_a_decimal_string_or_an_integer(number: object) -> None:
    hit = parse(body([company(number)])).hits[0].company
    assert hit.source_id == "gemi:1001" and hit.fields["registry_number"].value == 1001


def test_outcome_precedence_mismatch_beats_truncated_beats_multiple() -> None:
    both = parse(body([company("1001"), company("1002", afm="987654321")], total=5))
    assert (both.outcome, both.truncated) == ("afm_mismatch", True)
    assert [h.afm_matches for h in both.hits] == [True, False]
    many = parse(body([company("1001"), company("1002", afm="987654321")]))
    assert many.outcome == "afm_mismatch"


@pytest.mark.parametrize(
    ("reported", "matches"),
    [(" 012345678 ", True), ("\t012345678\n", True), ("12345678", False), (None, False)],
)
def test_the_reported_afm_is_compared_after_trimming_ascii_whitespace_only(
    reported: object, matches: bool
) -> None:
    assert parse(body([company(afm=reported)])).hits[0].afm_matches is matches


def test_an_empty_200_is_quarantined_not_read_as_no_company() -> None:
    result = parse(body([]))
    assert (result.outcome, result.quarantine_path, result.hits) == (
        "quarantined",
        "empty_results",
        (),
    )


@pytest.mark.parametrize(
    ("raw", "path"),
    [
        (b"\xff", "json"),
        (b"[]", "json"),
        (b'{"searchResults":[],"searchResults":[]}', "json"),
        (b'{"searchMetadata":{"totalCount":NaN},"searchResults":[]}', "json"),
        (b'{"searchResults":[]}', "/searchMetadata"),
        (custom({}), "/searchMetadata/totalCount"),
        (custom(meta(), drop_results=True), "/searchResults"),
        (custom(meta(totalCount=True)), "/searchMetadata/totalCount"),
        (custom(meta(totalCount=-1)), "/searchMetadata/totalCount"),
        (custom(meta(totalCount="1")), "/searchMetadata/totalCount"),
        (body([company(), company("1002")], total=1), "/searchMetadata/totalCount"),
        (custom(meta(resultsOffset=1)), "/searchMetadata/resultsOffset"),
        (custom(meta(resultsOffset=True)), "/searchMetadata/resultsOffset"),
        (custom(meta(resultsSize="2")), "/searchMetadata/resultsSize"),
        (custom(meta(resultsSize="x")), "/searchMetadata/resultsSize"),
        (custom(meta(resultsSize="9" * 5000)), "/searchMetadata/resultsSize"),
        (custom(meta(resultsSize="١")), "/searchMetadata/resultsSize"),
        (custom(meta(resultsSize=True)), "/searchMetadata/resultsSize"),
        (custom(meta(resultsSize="1000000")), "/searchMetadata/resultsSize"),
        (custom(meta(resultsSize=-1)), "/searchMetadata/resultsSize"),
        (custom(meta(resultsSize=None)), "/searchMetadata/resultsSize"),
        (custom(meta(), {}), "/searchResults"),
        (custom(meta(), [1]), "/searchResults/0"),
        (body([company(True)]), "/searchResults/0/arGemi"),
        (body([company("01")]), "/searchResults/0/arGemi"),
        (body([company(0)]), "/searchResults/0/arGemi"),
        (body([company(afm=1234567)]), "/searchResults/0/afm"),
        (body([company(), company(isBranch="no")]), "/searchResults/1/isBranch"),
    ],
)
def test_a_body_that_does_not_match_the_schema_is_quarantined_with_a_path_only(
    raw: bytes, path: str
) -> None:
    result = parse(raw)
    assert (result.outcome, result.quarantine_path, result.hits) == ("quarantined", path, ())
    assert result.response_sha256 == hashlib.sha256(raw).hexdigest()


def test_more_than_the_requested_page_size_is_quarantined() -> None:
    many = [company(str(1000 + n)) for n in range(21)]
    result = parse(body(many))
    assert (result.outcome, result.quarantine_path) == ("quarantined", "/searchResults")


def test_an_oversized_body_is_quarantined_before_decoding() -> None:
    result = parse(b" " * (8 * 1024 * 1024 + 1))
    assert (result.outcome, result.quarantine_path) == ("quarantined", "body_size")


@pytest.mark.parametrize("status", [0, 199, 201, 400, 401, 429, 500, 503, True])
def test_only_200_and_404_are_parsed_other_statuses_belong_to_the_collector(status: int) -> None:
    with pytest.raises(ValueError, match="^status$"):
        parse(b"{}", status=status)


@pytest.mark.parametrize("afm", ["012345678", "123456789", "999999999"])
def test_a_queryable_afm_is_nine_ascii_digits_and_not_all_zero(afm: str) -> None:
    assert queryable_afm(afm) == afm


@pytest.mark.parametrize(
    "afm",
    [
        "",
        "12345678",
        "1234567890",
        "000000000",
        " 012345678",
        "012345678\n",
        "01234567a",
        "０１２３４５６７８",
        "0123456 8",
        None,
        12345678,
        True,
    ],
)
def test_anything_else_is_never_sent_to_the_provider(afm: object) -> None:
    with pytest.raises(ValueError, match="^afm$"):
        queryable_afm(afm)


def test_a_query_with_an_ineligible_afm_is_refused_by_the_parser_too() -> None:
    with pytest.raises(ValueError, match="^afm$"):
        parse(b"{}", afm="12345")


def test_a_single_profile_is_still_normalized_exactly_as_before() -> None:
    raw = json.dumps(company("1001")).encode()
    profile = normalize_profile(raw, "1001")
    assert profile.fields["reported_afm"].json_pointer == "/afm"
    assert profile.activities_pointer == "/activities"
    with pytest.raises(InvalidProfile):
        normalize_profile(raw, "1002")


def test_the_results_size_may_also_be_a_plain_integer() -> None:
    assert parse(custom(meta(resultsSize=1))).outcome == "hit_single"


def test_exactly_the_requested_page_size_is_accepted() -> None:
    many = [company(str(1000 + n)) for n in range(20)]
    result = parse(body(many))
    assert (result.outcome, len(result.hits), result.truncated) == ("hit_multiple", 20, False)
