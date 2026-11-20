"""Pins what the collector sends and archives as provenance, before it becomes source-neutral.

A real three-page KIMDIS collection runs through the real collector against a mock transport (no
network, no database). Two things are fingerprinted:

* every request on the wire: method, full URL with its query string, all headers and the body;
* the archive ``manifest.json``, minus the values that differ on every run (timestamps, run id).

The expected digests were recorded from the collector on main ``0945918``, before requests and
provenance came from the adapter. They must not change: a change means KIMDIS requests or its
archived provenance changed, which this work promises never to do.
"""

import hashlib
import json
from pathlib import Path
from typing import cast

import httpx

from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from tests.test_collection import QUERY, Clock, body

PAGES = [body(page=n, total=3) for n in range(3)]

# Recorded from the unmodified collector on main 0945918.
EXPECTED_WIRE = "ea6be455ef52479cc2da1cb51d9122d648b49e5f3e82de859a7c9fbd8b2ccf44"
EXPECTED_MANIFEST = "23e702718403a5014bfe21df0b2ee8c66fe174ce5be8a2e8d70608f591cede67"
EXPECTED_MANIFEST_PROVENANCE = {
    "endpoint": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract",
    "source": "https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help",
    "license": "CC BY 4.0",
    "connector_version": "kimdis-contract-v1",
}


def digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def run_collection(root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    wire: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        wire.append(
            {
                "method": request.method,
                "url": str(request.url),
                "headers": sorted(request.headers.items()),
                "body": request.content.decode(),
            }
        )
        return httpx.Response(200, content=PAGES[int(request.url.params["page"])])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        summary = collect(QUERY, Limits(), Archive(root), client=client, clock=Clock())
    manifest = json.loads((root / "runs" / summary.run_id / "manifest.json").read_bytes())
    return wire, manifest


def stable(manifest: dict[str, object]) -> dict[str, object]:
    kept = {k: v for k, v in manifest.items() if k not in {"started_at", "finished_at"}}
    responses = cast(list[dict[str, object]], manifest["responses"])
    kept["responses"] = [{k: v for k, v in r.items() if k != "observed_at"} for r in responses]
    summary = dict(cast(dict[str, object], manifest["summary"]))
    summary.pop("run_id", None)
    kept["summary"] = summary
    return kept


def test_the_kimdis_wire_requests_are_byte_for_byte_what_main_sent(tmp_path: Path) -> None:
    wire, _ = run_collection(tmp_path / "raw")
    assert [w["method"] for w in wire] == ["POST"] * 3
    assert [w["url"] for w in wire] == [
        f"https://cerpp.eprocurement.gov.gr/khmdhs-opendata/contract?page={n}" for n in range(3)
    ]
    assert digest(wire) == EXPECTED_WIRE


def test_the_kimdis_manifest_is_byte_for_byte_what_main_wrote(tmp_path: Path) -> None:
    _, manifest = run_collection(tmp_path / "raw")
    assert {k: manifest[k] for k in EXPECTED_MANIFEST_PROVENANCE} == EXPECTED_MANIFEST_PROVENANCE
    assert list(manifest)[:6] == [
        "format_version",
        "connector_version",
        "endpoint",
        "query",
        "limits",
        "source",
    ]
    assert digest(stable(manifest)) == EXPECTED_MANIFEST
