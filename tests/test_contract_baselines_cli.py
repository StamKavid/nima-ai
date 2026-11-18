"""Actual command/event entry points choose immutable provider baselines."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_contracts
from scripts.check_contracts import main
from tests.test_contract_baselines import commit, document, git, write
from tests.test_contract_baselines import history as history


@pytest.mark.parametrize("event", ["pull_request", "push", "new_branch", "workflow_dispatch"])
def test_ci_selects_the_event_baseline_not_just_current_head(
    history: tuple[Path, str],
    event: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, base = history
    value = document()
    value.update(name="A patch", version="1.0.1")
    write(root, value)
    head = commit(root)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push" if event == "new_branch" else event)
    monkeypatch.setenv("NIMA_CONTRACT_PR_BASE", base if event == "pull_request" else "unused")
    monkeypatch.setenv("NIMA_CONTRACT_PUSH_BEFORE", base if event == "push" else "0" * 40)
    assert main(["--ci", "--repo", str(root)]) == 0
    terminal = capsys.readouterr()
    result = json.loads(terminal.out)
    assert not terminal.err and result["base"] == base and result["head"] == head
    assert result["patch"] == result["compared"] == 1 and result["unchanged"] == 0


def test_real_cli_rejects_unversioned_commit_despite_repaired_dirty_file(
    history: tuple[Path, str],
) -> None:
    root, base = history
    value = document()
    value["name"] = "private-sentinel"
    write(root, value)
    head = commit(root)
    write(root, document())
    before = git(root, "status", "--porcelain")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_contracts.py",
            "--repo",
            str(root),
            "--base",
            base,
            "--head",
            head,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"status": "failed", "failure": "contract_version"}
    assert not result.stderr and "private-sentinel" not in result.stdout
    assert git(root, "status", "--porcelain") == before
    assert git(root, "rev-parse", "HEAD") == head


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--base", "private-sentinel"],
        ["--unknown", "private-sentinel"],
        ["--ci", "--base", "a" * 40, "--head", "b" * 40],
    ],
)
def test_bad_configuration_has_fixed_diagnostics(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(arguments) == 2
    terminal = capsys.readouterr()
    assert json.loads(terminal.out) == {"status": "failed", "failure": "contracts_configuration"}
    assert not terminal.err and "private-sentinel" not in terminal.out


@pytest.mark.parametrize("event", ["pull_request", "push", "unsupported"])
def test_missing_or_unknown_ci_context_fails_closed(
    history: tuple[Path, str],
    event: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, _ = history
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.delenv("NIMA_CONTRACT_PR_BASE", raising=False)
    monkeypatch.delenv("NIMA_CONTRACT_PUSH_BEFORE", raising=False)
    assert main(["--ci", "--repo", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "contracts_configuration"


def test_partial_history_does_not_skip_comparison(
    history: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, base = history
    value = document()
    value.update(name="Patch", version="1.0.1")
    write(root, value)
    head = commit(root)
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth=1", root.as_uri(), str(shallow)], check=True)
    assert main(["--repo", str(shallow), "--base", base, "--head", head]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "contracts_history"


@pytest.mark.parametrize("event", ["workflow_dispatch", "pull_request"])
def test_promisor_configuration_is_refused_before_any_history_read(
    history: tuple[Path, str],
    event: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, base = history
    git(root, "config", "remote.origin.promisor", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("NIMA_CONTRACT_PR_BASE", base)
    original = check_contracts._git

    def local_config_only(root: Path, *args: str, **kwargs: object) -> bytes:
        assert args[0] == "config", "Promisor history could implicitly fetch objects"
        return original(root, *args, codes=(0, 1))

    monkeypatch.setattr(check_contracts, "_git", local_config_only)
    monkeypatch.setenv("GIT_TRACE", "private-sentinel")
    assert main(["--ci", "--repo", str(root)]) == 1
    terminal = capsys.readouterr()
    assert json.loads(terminal.out)["failure"] == "contracts_history"
    assert not terminal.err and not (root / "private-sentinel").exists()
