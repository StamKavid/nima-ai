"""Closed readout selections and private-file intake, without a source/SQL route."""

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Never

import psycopg
import pytest

from nima.analytics.request import RequestError, decode_request, read_request

FIRST = "11111111-1111-4111-8111-11111111111a"
SECOND = "22222222-2222-4222-8222-22222222222b"


def value() -> dict[str, Any]:
    return {
        "version": "nima-participation-request-v1",
        "source": "kimdis.contract",
        "run_ids": [SECOND, FIRST],
        "observation_cutoff": "2026-01-03T00:00:00Z",
        "supplier_country": "GR",
        "supplier_tax_id": "012345678",
        "archive_bindings": [
            {"run_id": SECOND, "root": "/private/two"},
            {"run_id": FIRST, "root": "/private/one"},
        ],
    }


def encoded(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode()


def private_file(root: Path) -> Path:
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    path = root / "request.json"
    path.write_bytes(encoded(value()))
    path.chmod(0o600)
    return path


def test_semantic_identity_ignores_archive_locations_and_order() -> None:
    original = decode_request(encoded(value()))
    changed = value()
    changed["run_ids"].reverse()
    changed["archive_bindings"].reverse()
    changed["archive_bindings"][0]["root"] = "/private/relocated"
    changed["observation_cutoff"] = "2026-01-03T00:00:00+00:00"
    moved = decode_request(encoded(changed))
    assert moved.request_sha256 == original.request_sha256
    assert moved.semantic_payload() == original.semantic_payload()
    assert moved.supplier_tax_id == "012345678"
    assert len(moved.archive_bindings) == 2
    assert "/private/" not in json.dumps(moved.semantic_payload())


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[]",
        b"null",
        b"\xff",
        b'{"version":NaN}',
        b'{"a":1,"a":2}',
        b'{"x":{"a":1,"a":2}}',
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_malformed_and_duplicate_json_is_rejected_without_source_values(body: bytes) -> None:
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_request(body)


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("version", "future"),
        ("source", "gemi"),
        ("supplier_tax_id", "000000000"),
        ("supplier_tax_id", 123456789),
        ("supplier_tax_id", "０１２３４５６７８"),
        ("supplier_tax_id", " 012345678"),
        ("supplier_country", "EL"),
        ("run_ids", []),
        ("run_ids", [FIRST, FIRST]),
        ("run_ids", [FIRST.upper()]),
        ("run_ids", [1]),
        ("run_ids", [FIRST] * 11),
        ("observation_cutoff", "2026-01-03"),
        ("observation_cutoff", "2026-01-03T00:00:00+02:00"),
        ("observation_cutoff", "2026-01-03T00:00:00.1234567Z"),
        ("observation_cutoff", "2026-01-03T00:00:00-00:00"),
        ("archive_bindings", []),
    ],
)
def test_unsupported_request_fields_fail_closed(field: str, replacement: object) -> None:
    document = value()
    document[field] = replacement
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_request(encoded(document))


@pytest.mark.parametrize(
    "path",
    [
        "relative",
        "/tmp/../escape",
        "/tmp/.git/object",
        "/tmp/./archive",
        "/tmp/archive/",
        "//tmp/archive",
        "/tmp/\x00archive",
        "https://example.org/archive",
    ],
)
def test_binding_paths_are_explicit_canonical_local_paths(path: str) -> None:
    document = value()
    document["archive_bindings"][0]["root"] = path
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_request(encoded(document))


def test_exact_body_limit() -> None:
    body = encoded(value())
    assert decode_request(body + b" " * (16384 - len(body))).supplier_tax_id == "012345678"
    with pytest.raises(RequestError, match="^analytics_limit$"):
        decode_request(body + b" " * (16385 - len(body)))


def test_private_intake_and_unsafe_files(tmp_path: Path) -> None:
    path = private_file(tmp_path / "private")
    assert read_request(path) == decode_request(path.read_bytes())
    path.chmod(0o644)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(path)
    path.chmod(0o600)
    alias = path.parent / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(alias)
    alias.unlink()
    os.link(path, alias)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(path)


def test_decode_has_no_filesystem_or_network_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    body = encoded(value())

    def forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("unexpected side effect")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", forbidden)
        patch.setattr(os, "stat", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(psycopg, "connect", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        result = decode_request(body)
        assert result.supplier_country == "GR"


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_keys_in_otherwise_valid_input_are_refused(nested: bool) -> None:
    body = encoded(value())
    if nested:
        original = b'"root": "/private/two"'
        assert original in body
        body = body.replace(original, b'"root": "/unaccepted", "root": "/private/two"')
    else:
        body = b'{"supplier_tax_id":"987654321",' + body[1:]
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_request(body)


@pytest.mark.parametrize(
    "change",
    [
        "extra",
        "missing",
        "extra_binding",
        "wrong_binding",
        "duplicate_binding",
        "bad_uuid",
        "bad_binding_type",
    ],
)
def test_closed_shape_and_binding_membership(change: str) -> None:
    document = value()
    if change == "extra":
        document["extra"] = "unaccepted"
    elif change == "missing":
        del document["source"]
    elif change == "extra_binding":
        document["archive_bindings"][0]["extra"] = True
    elif change == "wrong_binding":
        document["archive_bindings"][0]["run_id"] = "33333333-3333-4333-8333-333333333333"
    elif change == "duplicate_binding":
        document["archive_bindings"][0]["run_id"] = FIRST
    elif change == "bad_uuid":
        document["run_ids"][0] = "not-a-uuid"
    else:
        document["archive_bindings"][0] = None
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_request(encoded(document))


def test_non_unicode_scalar_path_is_rejected() -> None:
    document = value()
    document["archive_bindings"][0]["root"] = "/private/\ud800"
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_request(json.dumps(document).encode())


def test_missing_nonprivate_parent_and_oversized_file_are_fixed(tmp_path: Path) -> None:
    path = private_file(tmp_path / "private")
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(path.parent / "missing")
    path.parent.chmod(0o755)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(path)
    path.parent.chmod(0o700)
    path.write_bytes(b" " * 16385)
    with pytest.raises(RequestError, match="^analytics_limit$"):
        read_request(path)


def test_changed_file_between_metadata_and_read_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.evidence import artifacts

    path = private_file(tmp_path / "private")
    original = artifacts.read

    def changed(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        path.write_bytes(encoded(value()) + b" ")
        return original(parent, name, limit=limit, private=private)

    monkeypatch.setattr(artifacts, "read", changed)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(path)


def test_a_body_longer_than_the_checked_file_is_refused_without_any_timestamp_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The file itself is never touched, so inode and ctime stay equal; only the size comparison
    # between the metadata check and the bytes read can notice the difference.
    from nima.evidence import artifacts

    path = private_file(tmp_path / "private")
    original = artifacts.read

    def longer(parent: int, name: str, *, limit: int, private: bool = False) -> bytes:
        return original(parent, name, limit=limit, private=private) + b" "

    monkeypatch.setattr(artifacts, "read", longer)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(path)


def test_fifo_and_symlinked_parent_are_refused(tmp_path: Path) -> None:
    path = private_file(tmp_path / "private")
    fifo = path.parent / "pipe"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(fifo)
    alias = tmp_path / "alias"
    alias.symlink_to(path.parent, target_is_directory=True)
    with pytest.raises(RequestError, match="^analytics_input_file$"):
        read_request(alias / path.name)


def test_known_answer_through_real_ingestion_projection_request_and_snapshot(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from nima.analytics.snapshot import read_snapshot
    from nima.ingestion.archive import Archive
    from nima.ingestion.config import Limits, Summary
    from nima.projections.worker import drain
    from nima.storage.postgres import migrate
    from nima.storage.runs import RunStore
    from tests.test_analytics_snapshot import reader
    from tests.test_collection import QUERY

    fixture = json.loads(Path("tests/fixtures/participation.json").read_text())
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    seen: dict[tuple[int, str], int] = {}
    for row in fixture["observations"]:
        key = (row["day"], row["record"])
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        groups.setdefault((row["day"], occurrence), []).append(row)
    migrate(pg_dsn)
    selected = value()
    selected["run_ids"] = []
    selected["archive_bindings"] = []
    for (day, _), rows in sorted(groups.items()):
        run = uuid4()
        root = tmp_path / str(run)
        store = RunStore(pg_dsn, Archive(root), run, Limits())
        content = [
            {
                "referenceNumber": row["record"],
                "title": "Synthetic publication",
                "organization": None
                if row["buyer"] is None
                else {"key": row["buyer"], "value": "Synthetic buyer"},
                "cancelled": row["cancelled"],
                "contractingDataDetails": {
                    "contractingMembersDataList": [
                        {"vatNumber": tax, "country": None if country is None else {"key": country}}
                        for tax, country in row["suppliers"]
                    ]
                },
            }
            for row in rows
        ]
        raw = json.dumps(
            {
                "content": content,
                "number": 0,
                "size": len(rows),
                "totalElements": len(rows),
                "totalPages": 1,
                "last": True,
            }
        ).encode()
        with store.lease():
            store.begin(QUERY)
            store.commit_page(
                run, raw, observed_at=datetime(2026, 1, day, tzinfo=UTC), owner=store.owner
            )
            store.finish(Summary(status="complete"))
        drain(pg_dsn, run_id=run)
        selected["run_ids"].append(str(run))
        selected["archive_bindings"].append({"run_id": str(run), "root": str(root)})
    path = private_file(tmp_path / "selection")
    path.write_bytes(encoded(selected))
    request = read_request(path)
    with reader(pg_dsn) as (dsn, _):
        snapshot = read_snapshot(
            dsn, request.run_ids, tax_id=request.supplier_tax_id, cutoff=request.observation_cutoff
        )
    assert len(snapshot.observations) == 11
    assert len(json.loads(snapshot.document_json)["pages"]) == 4
    assert snapshot.metric.total == 5
    assert [(row.buyer_key, row.record_count) for row in snapshot.metric.buyers] == [
        ("kimdis.buyer-key:B1", 3),
        ("kimdis.buyer-key:B2", 1),
    ]
    assert snapshot.metric.unassigned_source_ids == ("kimdis:E",)
    assert snapshot.metric.unassessed_source_ids == ("kimdis:F",)
    assert snapshot.metric.ambiguous_source_ids == ("kimdis:G",)
    assert (snapshot.metric.cancelled_count, snapshot.metric.unknown_cancellation_count) == (1, 1)
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM nima.record_versions").fetchone() == (10,)
