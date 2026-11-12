"""Synthetic manual evidence claims; never registry-verified identities."""

import json

import pytest

from nima.evidence import EvidenceError
from nima.evidence.publicity import INPUT_VERSION, MAX_MANIFEST, parse_manifest


def capture(**changes: object) -> dict[str, object]:
    return {
        "gemi_number": "000123",
        "file": "αρχεία/capture.pdf",
        "media_type": "application/pdf",
        "source_url": "https://publicity.businessportal.gr/company/123",
        "claimed_captured_at": "2026-11-12T14:00:00+02:00",
        "capture_method": "print-to-pdf",
        "capture_context": "remote-browser",
        **changes,
    }


def manifest(*records: dict[str, object]) -> bytes:
    return json.dumps({"version": INPUT_VERSION, "records": records or [capture()]}).encode()


def test_preserves_operator_claims_without_verifying_origin() -> None:
    record = parse_manifest(manifest())[0]
    assert record.gemi_number == "000123"
    assert record.canonical_gemi_number == "123"
    assert record.claimed_captured_at == "2026-11-12T14:00:00+02:00"
    assert record.captured_at_utc == "2026-11-12T12:00:00+00:00"
    assert record.file == "αρχεία/capture.pdf"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gemi_number", "0"),
        ("gemi_number", "1" * 65),
        ("gemi_number", 123),
        ("gemi_number", "１２３"),
        ("gemi_number", " 123"),
        ("file", "../capture.pdf"),
        ("file", "/capture.pdf"),
        ("file", "a//b.pdf"),
        ("file", "./capture.pdf"),
        ("file", "a\\b.pdf"),
        ("file", ".git/a"),
        ("file", "a\x00.pdf"),
        ("file", "a" * 513),
        ("media_type", "text/html"),
        ("media_type", "image/svg+xml"),
        ("capture_method", "screenshot"),
        ("capture_context", "unprotected"),
        ("claimed_captured_at", "2026-11-12"),
        ("claimed_captured_at", "2026-11-12T12:00:00"),
        ("claimed_captured_at", "2026-99-12T12:00:00Z"),
        ("source_url", "http://publicity.businessportal.gr/"),
        ("source_url", "https://publicity.businessportal.gr.evil.test/"),
        ("source_url", "https://user:password@publicity.businessportal.gr/"),
        ("source_url", "https://publicity.businessportal.gr/?token=example"),
        ("source_url", "https://publicity.businessportal.gr/#fragment"),
        ("source_url", "https://publicity.businessportal.gr:444/"),
        ("source_url", "https://publicity.businessportal.gr:bad/"),
        ("source_url", "https://publicity.businessportal.gr/\n"),
        ("source_url", "https://publicity.businessportal.gr/" + "x" * 2048),
        ("extra", "not allowed"),
    ],
)
def test_rejects_invalid_or_credential_bearing_claims(field: str, value: object) -> None:
    with pytest.raises(EvidenceError, match="^input$"):
        parse_manifest(manifest(capture(**{field: value})))


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[]",
        b"{}",
        b"null",
        b"\xff",
        b'{"x":NaN}',
        b'{"version":1,"version":2}',
        b"[" * 2000,
        b" " * (MAX_MANIFEST + 1),
    ],
)
def test_rejects_malformed_bounded_json(body: bytes) -> None:
    with pytest.raises(EvidenceError, match="^input$"):
        parse_manifest(body)


def test_rejects_empty_duplicate_and_oversized_cohorts() -> None:
    for records in (
        [],
        [capture(), capture(gemi_number="123", file="b.pdf")],
        [capture(), capture(gemi_number="456")],
        [capture()] * 11,
    ):
        body = json.dumps({"version": INPUT_VERSION, "records": records}).encode()
        with pytest.raises(EvidenceError, match="^input$"):
            parse_manifest(body)


def test_accepts_images_only_with_consistent_capture_method() -> None:
    record = parse_manifest(manifest(capture(media_type="image/png", capture_method="screenshot")))
    assert record[0].media_type == "image/png"
