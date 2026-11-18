"""Reference matches are annotations, never source corrections or sector facts."""

import hashlib
import json
from typing import Any, cast

import pytest

from nima.identity.artifacts import encode
from nima.metadata.cpv_match import match_metadata
from nima.metadata.extract import VERSION, MetadataError, kimdis_metadata
from tests.test_collection import body
from tests.test_cpv_reference import genericode, prepare


def metadata(assertions: list[dict[str, Any]] | None = None) -> bytes:
    if assertions is None:
        rows = kimdis_metadata(
            body(
                total=1,
                objectDetailsList=[{"cpvs": [{"key": "12300000-9", "value": "Original wording"}]}],
            )
        )
        assertions = [dict(a) for a in rows[0]["assertions"]]
    return encode(
        {
            "artifact_version": VERSION,
            "source": "kimdis",
            "query": {"dimension": None, "code": None},
            "coverage": {"record_count": 1},
            "records": [
                {
                    "raw_sha256": "a" * 64,
                    "observed_at": "2026-01-01T00:00:00+00:00",
                    "record_pointer": "/content/0",
                    "assertions": assertions,
                }
            ],
        }
    )


def match(raw: bytes) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(match_metadata(raw, hashlib.sha256(raw).hexdigest(), prepare(genericode()))),
    )


def test_base_match_keeps_original_source_label_version_and_evidence() -> None:
    raw = metadata()
    original = json.loads(raw)
    report = match(raw)
    assert report["metadata"] == original
    assert encode(report["metadata"]) == raw
    assert report["metadata_snapshot_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["reference_sha256"] == hashlib.sha256(prepare(genericode()).body()).hexdigest()
    assert report["check_digit_validation"] == "not_checked"
    assert report["match_scope"] == "cpv_main_base_code"
    assert report["reference"]["language"] == "ell"
    assert len(report["annotations"]) == 1
    annotation = report["annotations"][0]
    assert annotation == {
        "record_ordinal": 0,
        "assertion_ordinal": 3,
        "status": "base_code_match",
        "base_code": "12300000",
        "reference_entry": {
            "code": "12300000",
            "label": "  Δοκιμή φύλλου  ",
            "parent_code": "12000000",
            "row_ordinal": 1,
        },
    }
    source = report["metadata"]["records"][0]["assertions"][3]
    assert source["code"] == "12300000-9"  # Deliberately no checksum correctness claim.
    assert source["label"] == "Original wording"
    assert source["taxonomy_version"] is None
    assert source["taxonomy_validation"] == "not_checked"
    assert source["json_pointer"] == "/content/0/objectDetailsList/0/cpvs/0"
    assert report["coverage"] == {"cpv_assertion_count": 1, "statuses": {"base_code_match": 1}}
    assert match_metadata(raw, hashlib.sha256(raw).hexdigest(), prepare(genericode())) == encode(
        report
    )


@pytest.mark.parametrize(
    ("row", "status", "code"),
    [
        ({"status": "reported", "code": "99999999-1"}, "not_found_in_selected_release", "99999999"),
        ({"status": "invalid", "code": "12300000-9"}, "source_ineligible", None),
        ({"status": "missing", "code": None}, "source_ineligible", None),
        ({"status": "reported", "code": "12300000"}, "source_ineligible", None),
        (
            {"status": "reported", "code": "12300000-9", "taxonomy_version": "2025"},
            "version_conflict",
            "12300000",
        ),
        (
            {"status": "reported", "code": "12300000-9", "taxonomy_version": "2008"},
            "base_code_match",
            "12300000",
        ),
    ],
)
def test_distinct_match_unknown_and_conflict_outcomes(
    row: dict[str, Any], status: str, code: str | None
) -> None:
    report = match(metadata([{"dimension": "procurement_cpv", **row}]))
    a = report["annotations"][0]
    assert a["status"] == status and a["base_code"] == code
    assert (a["reference_entry"] is not None) == (status == "base_code_match")
    assert report["coverage"] == {"cpv_assertion_count": 1, "statuses": {status: 1}}


def test_keeps_duplicate_occurrences_and_non_cpv_assertions_without_annotations() -> None:
    row = {"dimension": "procurement_cpv", "status": "reported", "code": "12300000-9"}
    raw = metadata([{"dimension": "buyer_function", "code": "1"}, row, row])
    report = match(raw)
    assert [a["assertion_ordinal"] for a in report["annotations"]] == [1, 2]
    assert report["coverage"]["statuses"] == {"base_code_match": 2}
    assert encode(report["metadata"]) == raw
    assert match(metadata([]))["annotations"] == []


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(artifact_version="future"),
        lambda d: d.update(source="gemi"),
        lambda d: d.update(query={"dimension": "procurement_cpv", "code": None}),
        lambda d: d.update(records={}),
        lambda d: d.update(records=[None]),
        lambda d: d["records"][0].update(assertions=None),
        lambda d: d["records"][0].update(assertions=[None]),
        lambda d: d["records"][0].update(assertions=[{}]),
    ],
)
def test_unrecognized_metadata_shapes_fail(change: Any) -> None:
    doc = json.loads(metadata())
    change(doc)
    with pytest.raises(MetadataError, match="^reference_metadata$"):
        match(encode(doc))


def test_mismatched_snapshot_selection_and_noncanonical_json_fail() -> None:
    raw = metadata()
    with pytest.raises(MetadataError, match="^reference_selection$"):
        match_metadata(raw, "0" * 64, prepare(genericode()))
    noncanonical = json.dumps(json.loads(raw)).encode()
    with pytest.raises(MetadataError, match="^reference_metadata$"):
        match(noncanonical)


def test_match_limits_and_invalid_json_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from nima.metadata import cpv_match

    raw = metadata()
    with pytest.raises(MetadataError, match="^reference_input$"):
        match_metadata(raw, "bad", prepare(genericode()))
    with pytest.raises(MetadataError, match="^reference_metadata$"):
        match(b'{"records":NaN}')
    monkeypatch.setattr(cpv_match, "MAX_ASSERTIONS", 0)
    with pytest.raises(MetadataError, match="^reference_limit$"):
        match(raw)
    monkeypatch.setattr(cpv_match, "MAX_REPORT_BYTES", 1)
    with pytest.raises(MetadataError, match="^reference_limit$"):
        match(raw)


def test_unexpected_numeric_payload_is_a_fixed_metadata_failure() -> None:
    raw = metadata()
    document = json.loads(raw)
    document["unexpected"] = 1.25
    with pytest.raises(MetadataError, match="^reference_metadata$"):
        match(encode(document))
