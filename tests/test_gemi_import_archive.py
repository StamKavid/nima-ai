"""Synthetic collector archives, never live company fixtures or credentials."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from nima.ingestion.gemi import collect
from nima.storage.gemi_archive import ImportFailure, verify_run
from tests.test_collection import Clock
from tests.test_gemi_contracts import profile


def archive_run(root: Path, raw: bytes | None = None, *, retry: bool = False) -> UUID:
    attempts = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if retry and attempts == 1:
            return httpx.Response(429, content=b"retry", headers={"retry-after": "0"})
        if request.url.path.endswith("/2"):
            return httpx.Response(404, content=b"missing")
        return httpx.Response(
            200,
            content=profile() if raw is None else raw,
            headers={"content-type": "application/json"},
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = collect(
            ("0001", "1", "2"),
            root,
            api_key="synthetic-credential",
            client=client,
            clock=Clock(),
        )
    assert result.status == "complete"
    return UUID(result.run_id)


def manifest_path(root: Path, run: UUID) -> Path:
    return root / "runs" / run.hex / "manifest.json"


def snapshot(root: Path) -> dict[str, tuple[bytes, int, int]]:
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_verified_run_uses_raw_evidence_and_preserves_archive(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run = archive_run(root, retry=True)
    manifest_path(root, run).with_name("normalized.jsonl").write_text("not an authority")
    before = snapshot(root)
    result = verify_run(root, run)
    assert result.run_id == run and result.archive_root == str(root)
    assert result.manifest_sha256 == hashlib.sha256(result.manifest).hexdigest()
    assert len(result.responses) == 3 and len(result.observations) == 2
    first, missing = result.observations
    assert first.number == "1" and first.attempt == 2 and first.profile is not None
    fields = json.loads(first.profile)["fields"]
    assert fields["reported_afm"] == {"value": "001234567", "json_pointer": "/afm"}
    assert first.outcome == "found" and missing.outcome == "not_found_at_observation"
    assert missing.profile is None
    assert snapshot(root) == before


def test_corrupt_body_rejected_even_for_retry_evidence(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run = archive_run(root, retry=True)
    digest = hashlib.sha256(b"retry").hexdigest()
    (root / "objects" / digest[:2] / f"{digest}.body").write_bytes(b"wrong")
    with pytest.raises(ImportFailure, match="archive_integrity"):
        verify_run(root, run)


def test_missing_archive_is_not_created(tmp_path: Path) -> None:
    root = tmp_path / "absent"
    with pytest.raises(ImportFailure):
        verify_run(root, UUID(int=1))
    assert not root.exists()


def edit(root: Path, run: UUID, path: str, value: object) -> None:
    filename = manifest_path(root, run)
    original = json.loads(filename.read_bytes())
    parts = path.split(".")
    target = original
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target[int(parts[-1]) if isinstance(target, list) else parts[-1]] = value
    filename.write_text(json.dumps(original))


@pytest.mark.parametrize(
    "path,value",
    [
        ("format_version", True),
        ("format_version", 2),
        ("connector_version", "other"),
        ("normalizer_version", "other"),
        ("endpoint", "https://example.invalid"),
        ("license", "unknown"),
        ("schema_sha256", "0" * 64),
        ("source", "unknown"),
        ("publisher", "unknown"),
        ("inputs", ["3"]),
        ("registry_numbers", ["1", "1"]),
        ("registry_numbers", []),
        ("registry_numbers", ["01", "2"]),
        ("summary.status", "failed"),
        ("summary.status", "quarantined"),
        ("summary.collection_complete", False),
        ("summary.normalization_complete", 1),
        ("summary.requested", True),
        ("summary.found", 2),
        ("summary.not_found", 0),
        ("summary.quarantined", 1),
        ("summary.attempts", 3),
        ("summary.failure", "private error"),
        ("summary.run_id", "other"),
        ("started_at", "2026-01-01"),
        ("finished_at", "2000-01-01T00:00:00+00:00"),
        ("limits.max_attempts", 4),
        ("limits.request_timeout", float("inf")),
        ("outcomes.2", "found"),
        ("attempts", []),
        ("attempts.0.registry_number", 1),
        ("attempts.0.attempt", True),
        ("attempts.0.attempt", 2),
        ("attempts.0.state", "started"),
        ("attempts.0.body_complete", 1),
        ("attempts.0.bytes", True),
        ("attempts.0.status", True),
        ("attempts.0.observed_at", "2026-01-01"),
        ("attempts.0.finished_at", "2000-01-01T00:00:00+00:00"),
        ("attempts.0.status", 429),
        ("attempts.0.failure", "transport"),
        ("attempts.1.registry_number", "1"),
    ],
)
def test_inconsistent_manifest_is_rejected(tmp_path: Path, path: str, value: object) -> None:
    root = tmp_path / "raw"
    run = archive_run(root)
    edit(root, run, path, value)
    with pytest.raises(ImportFailure):
        verify_run(root, run)


@pytest.mark.parametrize("kind", ["root", "manifest", "body", "fifo", "duplicate", "marker"])
def test_unsafe_or_malformed_archive_is_rejected(tmp_path: Path, kind: str) -> None:
    import os

    root = tmp_path / "raw"
    run = archive_run(root)
    target = manifest_path(root, run)
    if kind == "root":
        link = tmp_path / "linked"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif kind in {"manifest", "body"}:
        if kind == "body":
            target = next((root / "objects").glob("*/*.body"))
        copy = tmp_path / "copy"
        target.rename(copy)
        target.symlink_to(copy)
    elif kind == "fifo":
        target.unlink()
        os.mkfifo(target)
    elif kind == "duplicate":
        target.write_bytes(b'{"format_version":1,"format_version":1}')
    else:
        (root / ".nima-archive").write_text("unrelated")
    with pytest.raises(ImportFailure):
        verify_run(root, run)


@pytest.mark.parametrize("budget", ["MAX_MANIFEST", "MAX_BODY", "MAX_TOTAL_BODY", "MAX_PROFILES"])
def test_each_budget_fails_without_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: str
) -> None:
    root = tmp_path / "raw"
    run = archive_run(root)
    monkeypatch.setattr("nima.storage.gemi_archive." + budget, 1)
    with pytest.raises(ImportFailure, match="archive_budget"):
        verify_run(root, run)


def test_transport_retry_retains_bodyless_attempt(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        if count == 1:
            raise httpx.ReadError("synthetic", request=request)
        return httpx.Response(404, content=b"missing")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = collect(("1",), root, api_key="synthetic", client=client, clock=Clock())
    verified = verify_run(root, UUID(result.run_id))
    assert verified.responses[0].failure == "transport"
    assert verified.responses[0].sha256 is None
    assert verified.observations[0].attempt == 2 and verified.observations[0].profile is None


def test_successful_manifest_cannot_hide_bad_profile(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run = archive_run(root)
    data = json.loads(manifest_path(root, run).read_bytes())
    raw = profile(99)
    digest = hashlib.sha256(raw).hexdigest()
    from nima.ingestion.archive import Archive

    Archive(root).store(raw)
    data["attempts"][0].update(sha256=digest, bytes=len(raw))
    manifest_path(root, run).write_text(json.dumps(data))
    with pytest.raises(ImportFailure, match="profile_invalid"):
        verify_run(root, run)
