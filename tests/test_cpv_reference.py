"""Synthetic genericode; the publisher catalogue remains outside Git."""

import hashlib
import json
from html import escape
from typing import Any

import pytest

from nima.metadata import cpv
from nima.metadata.extract import MetadataError

CAPTURED_AT = "2026-11-18T11:43:00+00:00"


def genericode(rows: list[dict[str, str]] | None = None) -> bytes:
    if rows is None:
        rows = [
            {"code": "12000000", "ell_label": "Δοκιμή ρίζας", "eng_label": "Test root"},
            {
                "code": "12300000",
                "ell_label": "  Δοκιμή φύλλου  ",
                "eng_label": "Test leaf",
                "parentCode": "12000000",
            },
        ]
    columns = "".join(
        f'<Column Id="{name}" Use="optional"/>'
        for name in ("code", "parentCode", "ell_label", "eng_label")
    )
    values = "".join(
        "<Row>"
        + "".join(
            f'<Value ColumnRef="{key}"><SimpleValue>{escape(value)}</SimpleValue></Value>'
            for key, value in row.items()
        )
        + "</Row>"
        for row in rows
    )
    return (
        '<gc:CodeList xmlns:gc="http://docs.oasis-open.org/codelist/ns/genericode/1.0/">'
        "<Identification><ShortName>cpv_2008_core</ShortName><Version>2008</Version>"
        "<CanonicalUri>http://publications.europa.eu/resource/dataset/cpv</CanonicalUri>"
        "</Identification><ColumnSet>"
        + columns
        + "</ColumnSet><SimpleCodeList>"
        + values
        + "</SimpleCodeList></gc:CodeList>"
    ).encode()


def prepare(body: bytes, **kwargs: Any) -> cpv.CpvReference:
    return cpv.prepare_reference(
        body,
        raw_sha256=kwargs.pop("raw_sha256", hashlib.sha256(body).hexdigest()),
        language=kwargs.pop("language", "ell"),
        retrieved_at=kwargs.pop("retrieved_at", CAPTURED_AT),
        **kwargs,
    )


def test_reference_retains_selected_language_raw_identity_and_row_locations() -> None:
    raw = genericode()
    reference = prepare(raw)
    document = json.loads(reference.body())
    assert document["artifact_version"] == "cpv-reference-v1"
    assert document["reference"]["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert document["reference"]["language"] == "ell"
    assert document["reference"]["taxonomy_version"] == "2008"
    assert document["reference"]["sdk_release"] == "1.15.1"
    assert document["reference"]["license"] == "CC-BY-4.0"
    assert document["reference"]["retrieved_at"] == CAPTURED_AT
    assert document["entries"] == [
        {"code": "12000000", "label": "Δοκιμή ρίζας", "parent_code": None, "row_ordinal": 0},
        {
            "code": "12300000",
            "label": "  Δοκιμή φύλλου  ",
            "parent_code": "12000000",
            "row_ordinal": 1,
        },
    ]
    assert prepare(raw).body() == reference.body()
    english = json.loads(prepare(raw, language="eng").body())
    assert english["entries"][1]["label"] == "Test leaf"
    assert english["reference"]["raw_sha256"] == document["reference"]["raw_sha256"]
    assert english != document


def test_sorted_codes_retain_original_row_ordinal() -> None:
    doc = json.loads(
        prepare(
            genericode(
                [
                    {"code": "22000000", "ell_label": "Β"},
                    {"code": "12000000", "ell_label": "Α"},
                ]
            )
        ).body()
    )
    assert [(r["code"], r["row_ordinal"]) for r in doc["entries"]] == [
        ("12000000", 1),
        ("22000000", 0),
    ]


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b.replace(b"cpv_2008_core", b"other"),
        lambda b: b.replace(b"<Version>2008", b"<Version>2025"),
        lambda b: b.replace(b"dataset/cpv", b"dataset/other"),
        lambda b: b.replace(b"genericode/1.0/", b"genericode/2.0/"),
        lambda b: b.replace(b"<ColumnSet>", b"<Extra/><ColumnSet>"),
        lambda b: b.replace(
            b"<Version>2008</Version>", b"<Version>2008</Version><Version>2008</Version>"
        ),
        lambda b: b.replace(b'<Column Id="code"', b'<Column Id="ell_label"'),
        lambda b: b.replace(b'ColumnRef="code"', b'ColumnRef="unknown"', 1),
        lambda b: b.replace(b"<Row>", b"<Extra/><Row>", 1),
        lambda b: b.replace(b"<SimpleValue>12000000", b"<SimpleValue><Nested/>12000000", 1),
        lambda b: b.replace(
            b"</Row>",
            b'<Value ColumnRef="code"><SimpleValue>12000000</SimpleValue></Value></Row>',
            1,
        ),
        lambda b: b[:-20],
        lambda b: b"<!DOCTYPE gc:CodeList>" + b,
        lambda b: b'<!DOCTYPE x [<!ENTITY e "expanded">]>' + b,
        lambda b: b'<!DOCTYPE x SYSTEM "https://example.invalid/dtd">' + b,
        lambda b: b"",
        lambda b: b"<html>not a catalogue</html>",
    ],
)
def test_refuses_invalid_envelopes_or_xml_without_partial_success(change: Any) -> None:
    with pytest.raises(MetadataError, match="^reference_evidence$"):
        prepare(change(genericode()))


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"code": "12300000", "eng_label": "No Greek"}],
        [{"code": "12300000", "ell_label": "  "}],
        [{"code": "12300000-1", "ell_label": "Test"}],
        [{"ell_label": "No code"}],
        [{"code": "12300000", "ell_label": "A"}, {"code": "12300000", "ell_label": "B"}],
        [{"code": "12300000", "ell_label": "Test", "parentCode": "11100000"}],
        [{"code": "12300000", "ell_label": "Test", "parentCode": "12300000"}],
        [
            {"code": "12300000", "ell_label": "A", "parentCode": "12400000"},
            {"code": "12400000", "ell_label": "B", "parentCode": "12300000"},
        ],
    ],
)
def test_refuses_missing_coverage_invalid_codes_and_parent_graphs(
    rows: list[dict[str, str]],
) -> None:
    with pytest.raises(MetadataError, match="^reference_evidence$"):
        prepare(genericode(rows))


@pytest.mark.parametrize(
    "options",
    [
        {"language": "el"},
        {"language": "fra"},
        {"raw_sha256": "f" * 64},
        {"raw_sha256": "bad"},
        {"retrieved_at": "2026-11-18"},
        {"retrieved_at": "yesterday"},
    ],
)
def test_requires_explicit_selection_and_aware_capture_time(options: dict[str, str]) -> None:
    with pytest.raises(MetadataError, match="^reference_(input|selection)$"):
        prepare(genericode(), **options)


@pytest.mark.parametrize(
    ("constant", "value"),
    [
        ("MAX_BYTES", 10),
        ("MAX_ROWS", 1),
        ("MAX_ELEMENTS", 4),
        ("MAX_DEPTH", 3),
        ("MAX_TEXT", 4),
    ],
)
def test_bounds_fail_closed(monkeypatch: pytest.MonkeyPatch, constant: str, value: int) -> None:
    monkeypatch.setattr(cpv, constant, value)
    with pytest.raises(MetadataError, match="^reference_limit$"):
        prepare(genericode())
