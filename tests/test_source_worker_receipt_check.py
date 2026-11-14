"""Artifact export must reject incomplete, foreign or unsafe publications."""

import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from nima.egress import receipt_check
from nima.egress.receipt import ReceiptError, publish_receipt
from nima.evidence import artifacts
from tests.test_source_worker_receipts import complete


def test_prepare_requires_a_fresh_private_directory_and_verify_is_read_only(tmp_path: Path) -> None:
    root = tmp_path / "receipts"
    receipt_check.prepare(root)
    assert root.stat().st_mode & 0o777 == 0o700 and list(root.iterdir()) == []
    with pytest.raises(ReceiptError):
        receipt_check.verify(root)
    receipt = complete()
    publish_receipt(root, receipt)
    before = {file.name: file.read_bytes() for file in root.iterdir()}
    assert receipt_check.verify(root) == receipt
    assert {file.name: file.read_bytes() for file in root.iterdir()} == before
    with pytest.raises(ReceiptError):
        receipt_check.prepare(root)
    assert {file.name: file.read_bytes() for file in root.iterdir()} == before


@pytest.mark.parametrize(
    "fault",
    [
        "root_symlink",
        "root_mode",
        "extra",
        "marker",
        "gitignore",
        "two_reports",
        "filename",
        "symlink",
        "hardlink",
        "file_mode",
        "oversize",
        "tamper",
        "extra_field",
        "http_stage",
    ],
)
def test_unsafe_or_noncanonical_bundle_never_becomes_an_artifact(
    tmp_path: Path, fault: str
) -> None:
    root = tmp_path / "receipts"
    file = publish_receipt(root, complete())
    if fault == "root_symlink":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif fault == "root_mode":
        root.chmod(0o755)
    elif fault == "extra":
        (root / "private-sentinel").write_text("private-sentinel")
    elif fault == "marker":
        (root / ".nima-source-worker").write_bytes(b"foreign-archive\n")
    elif fault == "gitignore":
        (root / ".gitignore").write_bytes(b"wrong\n")
    elif fault == "two_reports":
        publish_receipt(root, replace(complete(), run_id=uuid4()))
    elif fault == "filename":
        file.rename(root / "private-sentinel.json")
    elif fault == "symlink":
        target = tmp_path / "target"
        file.rename(target)
        file.symlink_to(target)
    elif fault == "hardlink":
        os.link(file, tmp_path / "alias")
    elif fault == "file_mode":
        file.chmod(0o644)
    elif fault == "oversize":
        file.write_bytes(b"x" * 65537)
    elif fault in {"tamper", "extra_field"}:
        value = json.loads(file.read_bytes())
        value["production_ready" if fault == "tamper" else "private-sentinel"] = True
        file.write_text(json.dumps(value))
    elif fault == "http_stage":
        file.write_bytes(b'{"version":"source-worker-http-stage-v1"}\n')
    with pytest.raises(ReceiptError) as error:
        receipt_check.verify(root)
    assert "private-sentinel" not in str(error.value)


def test_atomic_replacement_after_read_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "receipts"
    file = publish_receipt(root, complete())
    replacement = tmp_path / "replacement"
    replacement.write_bytes(file.read_bytes())
    replacement.chmod(0o600)
    original = artifacts.read

    def replace_after_read(parent: int, name: str, *, limit: int, private: bool) -> bytes:
        raw = original(parent, name, limit=limit, private=private)
        if name == file.name:
            os.replace(replacement, file)
        return raw

    monkeypatch.setattr(artifacts, "read", replace_after_read)
    with pytest.raises(ReceiptError):
        receipt_check.verify(root)


@pytest.mark.parametrize("args", [[], ["verify"], ["private-sentinel", "private-sentinel"]])
def test_bad_cli_arguments_are_redacted(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert receipt_check.main(args) == 2
    assert "private-sentinel" not in capsys.readouterr().out


def test_cli_reports_counts_without_paths_or_deployment_claims(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "private-sentinel"
    assert receipt_check.main(["prepare", str(root)]) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["receipts"] == prepared["cases"] == 0
    assert prepared["isolation_checks_passed"] is False
    publish_receipt(root, complete())
    assert receipt_check.main(["verify", str(root)]) == 0
    raw = capsys.readouterr().out
    value = json.loads(raw)
    assert value["receipts"] == 1 and value["cases"] == 28
    assert value["isolation_checks_passed"] is True
    assert (
        value["internet_egress_verified"]
        is value["investigator_ip_protection_verified"]
        is value["production_ready"]
        is False
    )
    assert "private-sentinel" not in raw
    assert receipt_check.main(["prepare", str(root)]) == 1
    assert "private-sentinel" not in capsys.readouterr().out
