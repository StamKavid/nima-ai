"""Real killed workers at immutable evidence publication boundaries."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from nima.evidence import EvidenceError
from nima.evidence.intake import intake
from nima.evidence.verify import verify
from tests.test_postgres_crash import wait_until
from tests.test_publicity_evidence_intake import PDF, inputs
from tests.test_publicity_evidence_policy import capture, manifest

WORKER = """
import os, signal
from pathlib import Path
from uuid import UUID
from nima.evidence.intake import intake
original = os.link
def boundary(source, target, **kwargs):
    if not target.endswith('.json'):
        return original(source, target, **kwargs)
    if os.environ['NIMA_EVIDENCE_BOUNDARY'] == 'after':
        original(source, target, **kwargs)
        os.fsync(kwargs['dst_dir_fd'])
    Path(os.environ['NIMA_EVIDENCE_READY']).write_text('ready')
    signal.pause()
os.link = boundary
intake(UUID(os.environ['NIMA_EVIDENCE_ID']), Path(os.environ['NIMA_EVIDENCE_MANIFEST']),
       Path(os.environ['NIMA_EVIDENCE_INPUT']), Path(os.environ['NIMA_EVIDENCE_ARCHIVE']))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_killed_worker_leaves_only_complete_final_bundles(tmp_path: Path, boundary: str) -> None:
    metadata, source, archive = inputs(tmp_path)
    request_id, ready = uuid4(), tmp_path / "ready"
    environment = {
        **os.environ,
        "NIMA_EVIDENCE_BOUNDARY": boundary,
        "NIMA_EVIDENCE_READY": str(ready),
        "NIMA_EVIDENCE_ID": str(request_id),
        "NIMA_EVIDENCE_MANIFEST": str(metadata),
        "NIMA_EVIDENCE_INPUT": str(source),
        "NIMA_EVIDENCE_ARCHIVE": str(archive),
    }
    with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
        try:
            wait_until(ready.exists)
            worker.kill()
            worker.wait(timeout=5)
            assert len(list((archive / "bundles").glob("*.json"))) == int(boundary == "after")
            if boundary == "before":
                with pytest.raises(EvidenceError):
                    verify(request_id, archive)
            else:
                assert verify(request_id, archive)["records"] == 1
            result = intake(request_id, metadata, source, archive)
            assert result["reused"] is (boundary == "after")
            assert verify(request_id, archive)["records"] == 1
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)


def test_competing_payloads_cannot_replace_same_request(tmp_path: Path) -> None:
    metadata, source, archive = inputs(tmp_path)
    alternate = source / "alternate.json"
    alternate.write_bytes(manifest(capture(claimed_captured_at="2026-11-11T12:00:00Z")))
    request_id = uuid4()

    def attempt(path: Path) -> object:
        try:
            return intake(request_id, path, source, archive)["status"]
        except EvidenceError as exc:
            return exc.reason

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(attempt, [metadata, alternate]))
    assert set(outcomes) == {"staged", "conflict"}
    assert verify(request_id, archive)["records"] == 1


def test_input_mutation_during_descriptor_read_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata, source, archive = inputs(tmp_path)
    document = source / "αρχεία/capture.pdf"
    inode = document.stat().st_ino
    original = os.fstat
    reads = 0

    def mutate(fd: int) -> os.stat_result:
        nonlocal reads
        info = original(fd)
        if info.st_ino == inode:
            reads += 1
            if reads == 2:
                document.write_bytes(PDF + b"changed")
                return original(fd)
        return info

    monkeypatch.setattr(os, "fstat", mutate)
    with pytest.raises(EvidenceError, match="^input$"):
        intake(uuid4(), metadata, source, archive)
    assert not list(archive.glob("bundles/*.json"))


def test_actual_aggregate_limit_prevents_completion(tmp_path: Path) -> None:
    metadata, source, archive = inputs(tmp_path)
    rows = []
    for index in range(7):
        name = f"capture-{index}.pdf"
        size = 8 * 1024 * 1024 if index < 6 else 2 * 1024 * 1024 + 1
        (source / name).write_bytes(b"%PDF-" + b"x" * (size - 5))
        rows.append(capture(gemi_number=str(100 + index), file=name))
    metadata.write_bytes(manifest(*rows))
    with pytest.raises(EvidenceError, match="^input$"):
        intake(uuid4(), metadata, source, archive)
    assert not list(archive.glob("bundles/*.json"))


def test_archive_excludes_all_evidence_from_git(tmp_path: Path) -> None:
    metadata, source, archive = inputs(tmp_path)
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    request_id = uuid4()
    intake(request_id, metadata, source, archive)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "check-ignore",
            "--quiet",
            f"archive/bundles/{request_id.hex}.json",
        ],
        check=False,
    )
    assert result.returncode == 0
    assert (
        json.loads((archive / "bundles" / f"{request_id.hex}.json").read_bytes())["request_id"]
        == request_id.hex
    )
