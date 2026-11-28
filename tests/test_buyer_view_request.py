"""Closed operator configuration; no credential or browser path input."""

import json
from pathlib import Path

import pytest

from nima.views.request import ViewError, decode_config, read_config


def configuration(**changes: object) -> bytes:
    value: dict[str, object] = {
        "version": "nima-buyer-evidence-view-request-v1",
        "entries": [
            {
                "label": "Δοκιμή",
                "request_path": "/private/request.json",
                "report_path": "/private/" + "a" * 64 + ".json",
            }
        ],
    }
    return json.dumps({**value, **changes}, ensure_ascii=False).encode()


def test_decodes_a_saved_selection_and_preserves_untrusted_unicode() -> None:
    entries = decode_config(configuration())
    assert len(entries) == 1 and entries[0].label == "Δοκιμή"
    assert entries[0].request_path == Path("/private/request.json")
    assert entries[0].report_path.stem == "a" * 64


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "next"},
        {"extra": True},
        {"entries": []},
        {"entries": {}},
        {"entries": [None]},
        {"entries": [True]},
    ],
)
def test_refuses_unknown_fields_versions_and_entry_shapes(changes: dict[str, object]) -> None:
    with pytest.raises(ViewError, match="^view_input$"):
        decode_config(configuration(**changes))


@pytest.mark.parametrize(
    "field,value",
    [
        ("label", ""),
        ("label", "  "),
        ("label", "x" * 81),
        ("label", 1),
        ("label", "private\ntext"),
        ("label", "\ud800"),
        ("request_path", "relative.json"),
        ("request_path", "/private/.git/request"),
        ("request_path", "/private/../request"),
        ("report_path", "/private/not-a-hash.json"),
        ("report_path", "/private/" + "a" * 64 + ".html"),
        ("report_path", None),
    ],
)
def test_refuses_unsafe_labels_and_paths(field: str, value: object) -> None:
    config = json.loads(configuration())
    config["entries"][0][field] = value
    with pytest.raises(ViewError, match="^view_input$"):
        decode_config(json.dumps(config).encode())


def test_two_distinct_entries_are_allowed_but_duplicates_and_excess_are_refused() -> None:
    config = json.loads(configuration())
    one = config["entries"][0]
    two = {**one, "label": "Other", "request_path": "/private/other.json"}
    assert len(decode_config(configuration(entries=[one, two]))) == 2
    for entries in ([one, one], [one, {**one, "label": "Other"}], [one, two, two]):
        with pytest.raises(ViewError, match="^view_input$"):
            decode_config(configuration(entries=entries))


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"[]",
        b'{"version":NaN}',
        b'{"version":1,"version":2}',
        b'"\xff"',
        b'"' + b"x" * 16384 + b'"',
    ],
)
def test_strict_bounded_json(body: bytes) -> None:
    with pytest.raises(ViewError):
        decode_config(body)


def test_private_reader_checks_real_file_and_maps_failures(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    file = tmp_path / "view.json"
    file.write_bytes(configuration())
    file.chmod(0o600)
    assert read_config(file) == decode_config(file.read_bytes())
    file.chmod(0o644)
    with pytest.raises(ViewError, match="^view_input$"):
        read_config(file)


def test_error_codes_are_closed() -> None:
    assert str(ViewError("private secret")) == "view_contract"
