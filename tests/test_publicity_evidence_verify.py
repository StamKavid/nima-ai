"""Independent archive verification and replay against real filesystem boundaries."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from nima.evidence import EvidenceError
from nima.evidence.intake import intake
from nima.evidence.publicity import encode
from nima.evidence.verify import verify
from tests.test_publicity_evidence_intake import PDF, ingest, inputs


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_verification_is_read_only_and_not_identity_confirmation(tmp_path: Path) -> None:
    archive, request_id, _ = ingest(tmp_path)
    before = snapshot(archive)
    result = verify(request_id, archive)
    assert result["status"] == "verified"
    assert result["origin_verified"] is result["identity_verified"] is False
    assert snapshot(archive) == before


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "body",
        "symlink",
        "manifest",
        "version",
        "channel",
        "request",
        "size",
        "pointer",
        "time",
        "ignore",
        "marker",
        "permission",
        "objects_permission",
    ],
)
def test_damaged_archive_fails_verification_and_replay_without_repair(
    tmp_path: Path, damage: str
) -> None:
    archive, request_id, _ = ingest(tmp_path)
    path = archive / "bundles" / f"{request_id.hex}.json"
    data = json.loads(path.read_bytes())
    blob = archive / "objects" / f"{data['objects'][0]['sha256']}.body"
    if damage == "missing":
        blob.unlink()
    elif damage == "body":
        blob.write_bytes(PDF + b"tamper")
    elif damage == "symlink":
        blob.unlink()
        blob.symlink_to(tmp_path / "input/αρχεία/capture.pdf")
    elif damage == "manifest":
        path.write_bytes(b"{")
    elif damage == "ignore":
        (archive / ".gitignore").unlink()
    elif damage == "marker":
        (archive / ".nima-publicity").write_bytes(b"other archive")
    elif damage == "permission":
        path.chmod(0o644)
    elif damage == "objects_permission":
        (archive / "objects").chmod(0o755)
    else:
        if damage == "version":
            data["version"] = "gemi-api"
        elif damage == "channel":
            data["acquisition_channel"] = "api"
        elif damage == "request":
            data["request_id"] = uuid4().hex
        elif damage == "size":
            data["objects"][0]["bytes"] = True
        elif damage == "pointer":
            data["objects"][0]["input_pointer"] = "/records/9"
        else:
            data["imported_at"] = "2026-11-12"
        path.write_bytes(encode(data))
    before = snapshot(archive)
    with pytest.raises(EvidenceError):
        verify(request_id, archive)
    source = tmp_path / "input"
    with pytest.raises(EvidenceError):
        intake(request_id, source / "input.json", source, archive)
    assert snapshot(archive) == before


def test_concurrent_same_request_retains_one_completion(tmp_path: Path) -> None:
    metadata, source, archive = inputs(tmp_path)
    request_id = uuid4()
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(lambda _: intake(request_id, metadata, source, archive), range(2))
        )
    assert {r["reused"] for r in results} == {False, True}
    assert len(list((archive / "bundles").glob("*.json"))) == 1
    assert verify(request_id, archive)["records"] == 1


def test_missing_archive_verification_creates_nothing(tmp_path: Path) -> None:
    archive = tmp_path / "not-there"
    with pytest.raises(EvidenceError):
        verify(uuid4(), archive)
    assert not archive.exists()
