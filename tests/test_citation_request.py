"""Closed two-source selections and archive layout compatibility, without source requests."""

import json
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import pytest

from nima.analytics.citation_request import decode_citation_request, read_citation_request
from nima.analytics.request import RequestError
from nima.graph.pilot_archive import ArchiveBinding, RawReference, recover
from nima.ingestion.archive import Archive


def selection(**changes: Any) -> dict[str, Any]:
    return {
        "version": "nima-source-citations-request-v1",
        "kimdis_run_ids": [str(UUID(int=1))],
        "diavgeia_run_ids": [str(UUID(int=2))],
        "observation_cutoff": "2026-01-10T00:00:00Z",
        "archive_bindings": [
            {"source": "diavgeia", "run_id": str(UUID(int=2)), "root": "/private/decisions"},
            {"source": "kimdis", "run_id": str(UUID(int=1)), "root": "/private/contracts"},
        ],
        **changes,
    }


def test_explicit_groups_and_path_independent_hash() -> None:
    data = selection()
    request = decode_citation_request(json.dumps(data).encode())
    assert request.run_ids == (UUID(int=1), UUID(int=2))
    assert request.kimdis_run_ids == (UUID(int=1),)
    assert request.diavgeia_run_ids == (UUID(int=2),)
    assert request.semantic_payload()["observation_cutoff"] == "2026-01-10T00:00:00+00:00"
    data["archive_bindings"] = [
        {**b, "root": b["root"] + "/relocated"} for b in reversed(data["archive_bindings"])
    ]
    assert (
        decode_citation_request(json.dumps(data).encode()).request_sha256 == request.request_sha256
    )


@pytest.mark.parametrize(
    "change",
    [
        {"version": "v2"},
        {"extra": True},
        {"kimdis_run_ids": []},
        {"diavgeia_run_ids": []},
        {"kimdis_run_ids": None},
        {"diavgeia_run_ids": ["invalid"]},
        {"diavgeia_run_ids": [str(UUID(int=1))]},
        {"kimdis_run_ids": [str(UUID(int=1))] * 2},
        {"observation_cutoff": "2026-01-10"},
        {"archive_bindings": None},
        {"archive_bindings": []},
        {"kimdis_run_ids": [str(UUID(int=i)) for i in range(3, 14)]},
    ],
)
def test_invalid_closed_request(change: dict[str, Any]) -> None:
    with pytest.raises(RequestError, match="^citation_input$"):
        decode_citation_request(json.dumps(selection(**change)).encode())


@pytest.mark.parametrize(
    "change",
    [
        {"source": "gemi"},
        {"source": "kimdis"},
        {"run_id": str(UUID(int=3))},
        {"root": "relative"},
        {"root": "/private/../escape"},
        {"extra": True},
    ],
)
def test_binding_must_match_exact_source_and_run(change: dict[str, Any]) -> None:
    data = selection()
    data["archive_bindings"][0].update(change)
    with pytest.raises(RequestError, match="^citation_input$"):
        decode_citation_request(json.dumps(data).encode())


@pytest.mark.parametrize("raw", [b"[]", b"{", b"\xff", b'{"version":1,"version":2}', b"NaN"])
def test_invalid_bytes_are_fixed_reason(raw: bytes) -> None:
    with pytest.raises(RequestError, match="^citation_input$"):
        decode_citation_request(raw)


def test_private_request_file_and_limit(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(selection()))
    path.chmod(0o600)
    assert read_citation_request(path) == decode_citation_request(path.read_bytes())
    path.chmod(0o644)
    with pytest.raises(RequestError, match="^citation_input$"):
        read_citation_request(path)
    with pytest.raises(RequestError, match="^citation_limit$"):
        decode_citation_request(b" " * 16385)
    path.chmod(0o600)
    path.write_bytes(b" " * 16385)
    with pytest.raises(RequestError, match="^citation_limit$"):
        read_citation_request(path)


def test_duplicate_bindings_nonbytes_and_combined_bound() -> None:
    data = selection()
    data["archive_bindings"] = [data["archive_bindings"][0]] * 2
    for raw in [
        json.dumps(data).encode(),
        cast(bytes, None),
        json.dumps(selection(kimdis_run_ids=[str(UUID(int=i)) for i in range(3, 13)])).encode(),
    ]:
        with pytest.raises(RequestError, match="^citation_input$"):
            decode_citation_request(raw)


@pytest.mark.parametrize("source", ["kimdis", "gemi", "diavgeia"])
def test_shared_archive_layout_admits_explicit_supported_source(
    tmp_path: Path, source: Literal["kimdis", "gemi", "diavgeia"]
) -> None:
    archive = Archive(tmp_path / source)
    body = b"original"
    digest = archive.store(body)
    recovery = recover(
        (RawReference(source, UUID(int=1), digest),),
        (ArchiveBinding(source, UUID(int=1), archive.root),),
    )
    assert recovery.objects[0].body == body
    assert recovery.objects[0].references[0].source == source
