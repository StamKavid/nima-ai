"""Source dimensions describe different subjects and preserve uncertainty."""

import json

import pytest

from nima.sources.metadata_extract import MetadataError, gemi_metadata, kimdis_metadata, select_assertions
from nima.sources.gemi import normalize_profile
from tests.test_collection import body


def test_buyer_function_does_not_classify_the_supplier_or_purchase() -> None:
    raw = body(total=1, contractingAuthorityActivity={"key": "8", "value": "Άμυνα"})
    record = kimdis_metadata(raw)[0]
    assertions = record["assertions"]
    function = select_assertions(assertions, "buyer_function", "8")
    assert len(function) == 1 and function[0]["label"] == "Άμυνα"
    assert function[0]["json_pointer"] == "/content/0/contractingAuthorityActivity"
    assert select_assertions(assertions, "procurement_cpv", "8") == []
    assert not any(a["dimension"] == "supplier_kad" for a in assertions)
    assert record["record_status"] == "normalized"


@pytest.mark.parametrize("value,status", [(None, "null"), ([], "empty"), ({}, "invalid")])
def test_empty_and_bad_cpv_collections_are_not_missing(value: object, status: str) -> None:
    rows = kimdis_metadata(body(total=1, objectDetailsList=[{"cpvs": value}]))[0]["assertions"]
    selected = select_assertions(rows, "procurement_cpv")
    assert len(selected) == 1 and selected[0]["status"] == status
    assert selected[0]["json_pointer"] == "/content/0/objectDetailsList/0/cpvs"


def test_cpv_occurrences_are_not_deduplicated_or_promoted_to_taxonomy_membership() -> None:
    raw = body(
        total=1,
        objectDetailsList=[
            {
                "cpvs": [
                    {"key": "33141120-7", "value": "Συνθετικό υλικό"},
                    {"key": "33141120-7", "value": "Συνθετικό υλικό"},
                    {"key": "bad", "value": "Κακή μορφή"},
                ]
            }
        ],
    )
    rows = kimdis_metadata(raw)[0]["assertions"]
    matched = select_assertions(rows, "procurement_cpv", "33141120-7")
    assert len(matched) == 2
    assert [r["json_pointer"] for r in matched] == [
        "/content/0/objectDetailsList/0/cpvs/0",
        "/content/0/objectDetailsList/0/cpvs/1",
    ]
    assert all(r["taxonomy_validation"] == "not_checked" for r in matched)
    assert select_assertions(rows, "procurement_cpv", "bad") == []
    assert select_assertions(rows, "procurement_cpv")[-1]["status"] == "invalid"


def test_missing_null_and_quarantined_record_remain_explicit() -> None:
    record = kimdis_metadata(body(total=1, title=None, contractingAuthorityActivity=None))[0]
    assert record["record_status"] == "quarantined"
    assert record["assertions"][0]["status"] == "null"
    missing = select_assertions(record["assertions"], "buyer_type")[0]
    assert missing["status"] == "missing" and missing["json_pointer"] is None
    assert missing["expected_pointer"] == "/content/0/typeOfContractingAuthority"


def test_kad_retains_version_and_dates_without_asserting_current_activity() -> None:
    raw = json.dumps(
        {
            "arGemi": 123,
            "activities": [
                {
                    "activity": {
                        "id": "62.01",
                        "descr": "Συνθετική δραστηριότητα",
                        "kadVersion": "2008",
                    },
                    "type": "primary",
                    "dtFrom": "2008-01-01",
                    "dtTo": "2020-01-01",
                }
            ],
        }
    ).encode()
    row = gemi_metadata(normalize_profile(raw, "123").payload())[0]
    assert row["dimension"] == "supplier_kad" and row["taxonomy_version"] == "2008"
    assert row["details"] == {"type": "primary", "date_from": "2008-01-01", "date_to": "2020-01-01"}
    assert row["json_pointer"] == "/activities/0/activity"
    assert row["status"] == "reported" and row["taxonomy_validation"] == "not_checked"


@pytest.mark.parametrize(
    "fields,status",
    [({}, "missing"), ({"activities": None}, "null"), ({"activities": []}, "empty")],
)
def test_gemi_activity_coverage(fields: dict[str, object], status: str) -> None:
    profile = normalize_profile(json.dumps({"arGemi": 123, **fields}).encode(), "123")
    assert gemi_metadata(profile.payload())[0]["status"] == status


def test_assertion_limit_fails_instead_of_truncating(monkeypatch: pytest.MonkeyPatch) -> None:
    from nima.sources import metadata_extract as extract

    monkeypatch.setattr(extract, "MAX_ASSERTIONS", 3)
    with pytest.raises(MetadataError, match="^metadata_limit$"):
        kimdis_metadata(body(total=1))


@pytest.mark.parametrize("dimension,code", [(None, "8"), ("unknown", None)])
def test_invalid_query_is_not_an_empty_result(dimension: str | None, code: str | None) -> None:
    with pytest.raises(MetadataError, match="^metadata_input$"):
        select_assertions([], dimension, code)


@pytest.mark.parametrize(
    "pair", ["8", [], {"key": True}, {"key": "0"}, {"key": "٨"}, {"key": "8", "value": []}]
)
def test_bad_buyer_shapes_remain_invalid(pair: object) -> None:
    row = kimdis_metadata(body(total=1, contractingAuthorityActivity=pair))[0]["assertions"][0]
    assert row["status"] == "invalid"
    assert row["json_pointer"] == "/content/0/contractingAuthorityActivity"


@pytest.mark.parametrize("objects", [[], None, {}, [False], [{"cpvs": [False]}]])
def test_unsupported_object_shapes_do_not_disappear(objects: object) -> None:
    rows = kimdis_metadata(body(total=1, objectDetailsList=objects))[0]["assertions"]
    assert len(select_assertions(rows, "procurement_cpv")) == 1


def test_exact_greek_labels_and_all_present_field_pointers_resolve() -> None:
    raw = body(
        total=1,
        contractingAuthorityActivity={"key": "8", "value": "  Άμυνα  "},
        objectDetailsList=[{"cpvs": [{"key": "33141120-7", "value": "Υλικό"}]}],
    )
    record = kimdis_metadata(raw)[0]
    document = json.loads(raw)
    for row in record["assertions"]:
        for field, pointer in row["field_pointers"].items():
            if pointer is None:
                continue
            value = document
            for part in pointer.split("/")[1:]:
                value = value[int(part)] if isinstance(value, list) else value[part]
            assert value == {"code": row["code"], "label": row["label"]}[field]
    assert record["assertions"][0]["label"] == "  Άμυνα  "


@pytest.mark.parametrize(
    "activity", [None, {}, {"id": None}, {"id": "62", "descr": ""}, {"id": "62", "kadVersion": ""}]
)
def test_unusable_kad_does_not_become_reported(activity: object) -> None:
    raw = json.dumps({"arGemi": 123, "activities": [{"activity": activity}]}).encode()
    assert gemi_metadata(normalize_profile(raw, "123").payload())[0]["status"] == "invalid"
