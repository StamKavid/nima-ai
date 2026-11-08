"""The integrity check must detect missing, changed, and unregistered skills."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_skills import main, verify_skills


@pytest.fixture
def installation(tmp_path: Path) -> Path:
    root = tmp_path / ".agents"
    skill = root / "skills/example/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: example\n---\nVerified skill.\n", encoding="utf-8")
    manifest = {
        "repository": "https://github.com/addyosmani/agent-skills",
        "revision": "a" * 40,
        "skill_names": ["example"],
        "files": {"skills/example/SKILL.md": hashlib.sha256(skill.read_bytes()).hexdigest()},
    }
    (root / "skills.lock.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_accepts_an_unchanged_installation(installation: Path) -> None:
    assert verify_skills(installation) == []


def test_detects_changed_skill_contents(installation: Path) -> None:
    (installation / "skills/example/SKILL.md").write_text("Changed", encoding="utf-8")
    assert verify_skills(installation) == ["Changed file: skills/example/SKILL.md"]


def test_detects_a_deleted_file(installation: Path) -> None:
    (installation / "skills/example/SKILL.md").unlink()
    errors = verify_skills(installation)
    assert "Missing file: skills/example/SKILL.md" in errors
    assert "Installed skill names differ from the lockfile" in errors


def test_detects_an_unregistered_skill(installation: Path) -> None:
    skill = installation / "skills/unregistered/SKILL.md"
    skill.parent.mkdir()
    skill.write_text("Unexpected skill", encoding="utf-8")
    assert "Installed skill names differ from the lockfile" in verify_skills(installation)


def test_rejects_a_manifest_path_outside_the_installation(installation: Path) -> None:
    manifest_path = installation / "skills.lock.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["../outside"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "Unsafe manifest path: ../outside" in verify_skills(installation)


def test_rejects_a_symlink_outside_the_installation(installation: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("Verified skill.", encoding="utf-8")
    skill = installation / "skills/example/SKILL.md"
    skill.unlink()
    skill.symlink_to(outside)
    assert "Unsafe manifest path: skills/example/SKILL.md" in verify_skills(installation)


@pytest.mark.parametrize("contents", ["{invalid", "[]", '{"files": []}'])
def test_rejects_an_invalid_manifest(installation: Path, contents: str) -> None:
    (installation / "skills.lock.json").write_text(contents, encoding="utf-8")
    assert verify_skills(installation) == ["Invalid skill lockfile"]


def test_reports_a_missing_lockfile(installation: Path) -> None:
    (installation / "skills.lock.json").unlink()
    assert verify_skills(installation) == ["Invalid skill lockfile"]


def test_command_reports_success(installation: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(installation) == 0
    assert "matches its lockfile" in capsys.readouterr().out


def test_command_fails_on_drift(installation: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (installation / "skills/example/SKILL.md").unlink()
    assert main(installation) == 1
    assert "Missing file" in capsys.readouterr().out


def test_checks_the_actual_project_installation() -> None:
    assert main() == 0
