"""Real committed Git histories enforce consumer contracts, never dirty files."""

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.check_contracts import BaselineError, check_repository

DIRECTORY = "src/nima/contracts"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Synthetic Test",
            "-c",
            "user.email=synthetic@example.invalid",
            *args,
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def document() -> dict[str, Any]:
    return {
        "apiVersion": "v3.2.0",
        "kind": "DataContract",
        "id": "synthetic.example",
        "version": "1.0.0",
        "name": "Synthetic example",
        "schema": [
            {
                "name": "example",
                "logicalType": "object",
                "properties": [{"name": "value", "logicalType": "string", "required": True}],
            }
        ],
        "customProperties": [
            {"property": "nima.semanticDefinition", "value": {"grain": "example"}}
        ],
    }


def write(root: Path, value: object, name: str = "example-v1.odcs.json") -> Path:
    path = root / DIRECTORY / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def commit(root: Path) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Synthetic snapshot", "--allow-empty")
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q", "--initial-branch=main")
    write(root, document())
    base = commit(root)
    git(root, "update-ref", "refs/remotes/origin/main", base)
    return root, base


@pytest.mark.parametrize("change", ["unchanged", "patch", "minor", "major", "rename"])
def test_compatible_committed_histories(history: tuple[Path, str], change: str) -> None:
    root, base = history
    value = document()
    if change == "patch":
        value.update(version="1.0.1", name="Reviewed description")
    elif change == "minor":
        value["schema"][0]["properties"].append(
            {"name": "optional", "logicalType": "string", "required": False}
        )
        value["version"] = "1.1.0"
    elif change == "major":
        value["schema"][0]["properties"] = []
        value["version"] = "2.0.0"
    path = write(root, value)
    if change == "rename":
        path.rename(path.with_name("renamed-v1.odcs.json"))
    head = commit(root)
    result = check_repository(root, base=base, head=head)
    assert result["total"] == result["compared"] == 1 and result["added"] == 0
    assert result["unchanged" if change == "rename" else change] == 1


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("unversioned", "contract_version"),
        ("breaking", "contract_breaking_change"),
        ("removed", "contracts_removed"),
        ("replaced_id", "contracts_removed"),
        ("duplicate_id", "contracts_duplicate"),
        ("corrupt", "contracts_invalid"),
        ("symlink", "contracts_mode"),
        ("oversized", "contracts_limit"),
    ],
)
def test_bad_committed_history_cannot_be_hidden_by_valid_working_files(
    history: tuple[Path, str], fault: str, reason: str
) -> None:
    root, base = history
    value = document()
    path = root / DIRECTORY / "example-v1.odcs.json"
    if fault == "unversioned":
        value["name"] = "changed"
    elif fault == "breaking":
        value["schema"][0]["properties"] = []
        value["version"] = "1.1.0"
    elif fault == "replaced_id":
        value["id"] = "different.identity"
    elif fault == "duplicate_id":
        write(root, value, "duplicate-v1.odcs.json")
    write(root, value)
    if fault == "removed":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"private-sentinel")
    elif fault == "symlink":
        path.unlink()
        path.symlink_to("../../../../outside-private-sentinel")
    elif fault == "oversized":
        path.write_bytes(b"x" * (256 * 1024 + 1))
    head = commit(root)
    if path.is_symlink():
        path.unlink()
    write(root, document())  # An attractive dirty-tree replacement is not evidence.
    with pytest.raises(BaselineError, match=f"^{reason}$"):
        check_repository(root, base=base, head=head)


def test_new_identity_is_validated_and_counted(history: tuple[Path, str]) -> None:
    root, base = history
    value = copy.deepcopy(document())
    value["id"] = "second.identity"
    write(root, value, "second-v1.odcs.json")
    result = check_repository(root, base=base, head=commit(root))
    assert result["total"] == 2 and result["compared"] == result["added"] == 1


@pytest.mark.parametrize("reference", ["main", "f" * 40, "--private-sentinel", "A" * 40])
def test_baselines_require_available_full_commit_ids(
    history: tuple[Path, str], reference: str
) -> None:
    root, head = history
    with pytest.raises(BaselineError):
        check_repository(root, base=reference, head=head)


def test_divergent_baseline_is_not_an_interface_history(history: tuple[Path, str]) -> None:
    root, head = history
    tree = git(root, "rev-parse", "HEAD^{tree}")
    unrelated = git(root, "commit-tree", tree, "-m", "Independent root")
    with pytest.raises(BaselineError, match="^contracts_history$"):
        check_repository(root, base=unrelated, head=head)
