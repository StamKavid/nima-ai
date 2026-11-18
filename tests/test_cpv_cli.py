"""Actual CLI and SQL paths; inputs and output artifacts remain private."""

import hashlib
import json
from pathlib import Path

import pytest

from nima.__main__ import main
from nima.metadata.cpv import prepare_reference
from nima.metadata.cpv_match import match_metadata
from nima.metadata.export import prepare_metadata
from nima.metadata.store import promote_metadata
from tests.test_cpv_reference import CAPTURED_AT, genericode
from tests.test_metadata_export import kimdis_run
from tests.test_metadata_store import principal


def arguments(tmp_path: Path, operation: str = "cpv-reference") -> tuple[list[str], Path, Path]:
    capture = tmp_path / "capture"
    capture.mkdir(mode=0o700)
    source = capture / "source.gc"
    source.write_bytes(genericode())
    source.chmod(0o600)
    output = tmp_path / "out"
    return (
        [
            "metadata",
            operation,
            "--reference-file",
            str(source),
            "--reference-raw-sha256",
            hashlib.sha256(source.read_bytes()).hexdigest(),
            "--language",
            "ell",
            "--retrieved-at",
            CAPTURED_AT,
            "--output-dir",
            str(output),
        ],
        source,
        output,
    )


def test_offline_reference_publication_is_private_canonical_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args, source, out = arguments(tmp_path)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    raw = source.read_bytes()
    expected = prepare_reference(
        raw, raw_sha256=hashlib.sha256(raw).hexdigest(), language="ell", retrieved_at=CAPTURED_AT
    ).body()
    digest = hashlib.sha256(expected).hexdigest()
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "complete", "entry_count": 2}
    artifact = out / (digest + ".json")
    assert artifact.read_bytes() == expected
    assert artifact.stat().st_mode & 0o777 == 0o600 and out.stat().st_mode & 0o777 == 0o700
    before = artifact.stat().st_mtime_ns
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "complete", "entry_count": 2}
    assert artifact.stat().st_mtime_ns == before and source.read_bytes() == raw


def test_match_uses_selected_stored_snapshot_readonly_with_originals_unchanged(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args, source, out = arguments(tmp_path, "cpv-match")
    run = kimdis_run(pg_dsn, tmp_path / "archive")
    raw, snapshot = prepare_metadata("kimdis", run, tmp_path / "archive", dsn=pg_dsn)
    with principal(pg_dsn, write=True) as dsn:
        promote_metadata(dsn, "kimdis", run, tmp_path / "archive", snapshot.artifact_sha256)
    with principal(pg_dsn) as dsn:
        monkeypatch.setenv("NIMA_DATABASE_URL", dsn)
        args += ["--snapshot-sha256", snapshot.artifact_sha256]
        assert main(args) == 0
        terminal = capsys.readouterr().out
        assert json.loads(terminal) == {
            "status": "complete",
            "entry_count": 2,
            "cpv_assertion_count": 1,
        }
        assert all(
            value not in terminal
            for value in (str(run), str(source), snapshot.artifact_sha256, "Άμυνα")
        )
        reference = prepare_reference(
            source.read_bytes(),
            raw_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            language="ell",
            retrieved_at=CAPTURED_AT,
        )
        expected = match_metadata(raw, snapshot.artifact_sha256, reference)
        assert (out / (hashlib.sha256(expected).hexdigest() + ".json")).read_bytes() == expected
        assert json.loads(expected)["metadata"] == json.loads(raw)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("wrong_hash", "reference_selection"),
        ("malformed", "reference_selection"),
        ("file_symlink", "reference_evidence"),
        ("directory_symlink", "reference_evidence"),
        ("public_file", "reference_evidence"),
        ("public_directory", "reference_evidence"),
        ("missing", "reference_evidence"),
        ("output_conflict", "reference_output"),
        ("relative_output", "reference_input"),
        ("relative_input", "reference_input"),
    ],
)
def test_invalid_inputs_and_output_boundaries_fail_with_fixed_private_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: str, reason: str
) -> None:
    args, source, out = arguments(tmp_path)
    if change == "wrong_hash":
        args[args.index("--reference-raw-sha256") + 1] = "0" * 64
    elif change == "malformed":
        source.write_bytes(b"<html/>")
    elif change == "file_symlink":
        target = source.with_suffix(".target")
        source.rename(target)
        source.symlink_to(target)
    elif change == "directory_symlink":
        target = source.parent.with_name("target")
        source.parent.rename(target)
        source.parent.symlink_to(target, target_is_directory=True)
    elif change == "public_file":
        source.chmod(0o644)
    elif change == "public_directory":
        source.parent.chmod(0o755)
    elif change == "missing":
        source.unlink()
    elif change == "output_conflict":
        out.mkdir(mode=0o755)
        out.chmod(0o755)
    elif change == "relative_output":
        args[args.index("--output-dir") + 1] = "relative-private"
    elif change == "relative_input":
        args[args.index("--reference-file") + 1] = "relative-private"
    assert main(args) == (2 if reason == "reference_input" else 1)
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "failure": reason}
    if change != "output_conflict":
        assert not out.exists()


def test_missing_database_snapshot_and_invalid_language_do_not_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args, _, out = arguments(tmp_path, "cpv-match")
    args += ["--snapshot-sha256", "0" * 64]
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "reference_input"
    args[args.index("--language") + 1] = "fallback"
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "reference_input"
    assert not out.exists()


def test_actual_parser_and_missing_sql_snapshot_fail_before_publication(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.storage.postgres import migrate

    args, source, out = arguments(tmp_path)
    source.write_bytes(b"<html/>")
    args[args.index("--reference-raw-sha256") + 1] = hashlib.sha256(source.read_bytes()).hexdigest()
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "reference_evidence"
    source.write_bytes(genericode())
    args[args.index("--reference-raw-sha256") + 1] = hashlib.sha256(source.read_bytes()).hexdigest()
    assert main([*args, "--snapshot-sha256", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "reference_input"
    migrate(pg_dsn)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    args[1] = "cpv-match"
    assert main([*args, "--snapshot-sha256", "0" * 64]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "metadata_unavailable"
    assert not out.exists()
