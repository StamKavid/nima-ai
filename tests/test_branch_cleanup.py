"""Only unchanged, merged, unused feature heads qualify for deletion."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.branch_cleanup import plan_cleanup

REPO: dict[str, object] = {"full_name": "StamKavid/nima-ai", "default_branch": "main"}
SHA = "a" * 40


def snapshot(
    name: str = "feature/finished",
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    head = {"ref": name, "sha": SHA, "repo": {"full_name": REPO["full_name"]}}
    prs: list[dict[str, object]] = [
        {"number": 1, "merged_at": "2026-11-12T00:00:00Z", "head": head}
    ]
    branches: list[dict[str, object]] = [{"name": name, "protected": False, "commit": {"sha": SHA}}]
    return prs, branches


def test_only_completed_unchanged_branch_is_selected() -> None:
    prs, branches = snapshot()
    result = plan_cleanup(REPO, prs, branches, [])
    assert result["delete"] == [{"branch": "feature/finished", "sha": SHA, "pr_number": 1}]


@pytest.mark.parametrize("name", ["main", "dev", "develop", "master"])
def test_long_lived_branches_are_retained_even_when_pr_merged(name: str) -> None:
    prs, branches = snapshot(name)
    assert not plan_cleanup(REPO, prs, branches, [])["delete"]


@pytest.mark.parametrize(
    "change", ["unmerged", "fork", "advanced", "protected", "missing_protection", "bad_sha"]
)
def test_incomplete_or_reused_heads_are_retained(change: str) -> None:
    prs, branches = snapshot()
    if change == "unmerged":
        prs[0]["merged_at"] = None
    elif change == "fork":
        prs[0]["head"] = {
            "ref": "feature/finished",
            "sha": SHA,
            "repo": {"full_name": "someone/fork"},
        }
    elif change == "advanced":
        branches[0]["commit"] = {"sha": "b" * 40}
    elif change == "protected":
        branches[0]["protected"] = True
    elif change == "missing_protection":
        branches[0].pop("protected")
    else:
        branches[0]["commit"] = {"sha": "invalid"}
    assert not plan_cleanup(REPO, prs, branches, [])["delete"]


@pytest.mark.parametrize("usage", ["head", "base"])
def test_open_pr_head_or_stack_base_is_retained(usage: str) -> None:
    prs, branches = snapshot()
    opened: list[dict[str, object]] = [
        {usage: {"ref": "feature/finished", "repo": {"full_name": REPO["full_name"]}}}
    ]
    assert not plan_cleanup(REPO, prs, branches, opened)["delete"]


def test_deferred_stack_base_is_cleaned_on_later_sweep() -> None:
    prs, branches = snapshot()
    candidate = deepcopy(branches)
    assert plan_cleanup(REPO, prs, candidate, [])["delete"]
    assert not plan_cleanup(REPO, prs, [], [])["delete"]
    with pytest.raises(ValueError):
        plan_cleanup({"full_name": "StamKavid/nima-ai"}, prs, branches, [])


def test_metadata_cli_blocks_bad_input_and_emits_reviewable_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from scripts.branch_cleanup import main

    prs, branches = snapshot()
    paths = {}
    for key, value in {"repository": REPO, "closed": prs, "branches": branches, "open": []}.items():
        path = tmp_path / (key + ".json")
        path.write_text(json.dumps(value))
        paths[key] = path
    args = [arg for key, value in paths.items() for arg in ("--" + key, str(value))]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["delete"][0]["sha"] == SHA
    paths["closed"].write_text(json.dumps(prs) + "\n" + json.dumps(prs))
    assert main(args) == 0
    assert len(json.loads(capsys.readouterr().out)["delete"]) == 1
    paths["open"].write_text("")
    assert main(args) == 1 and "metadata_invalid" in capsys.readouterr().out
    paths["open"].write_text("{}")
    assert main(args) == 1 and "metadata_invalid" in capsys.readouterr().out
    paths["open"].write_bytes(b" " * (4 * 1024 * 1024 + 1))
    assert main(args) == 1 and "metadata_invalid" in capsys.readouterr().out


@pytest.mark.parametrize("advanced", [False, True])
def test_atomic_git_deletion_keeps_commits_added_since_snapshot(
    tmp_path: Path, advanced: bool
) -> None:
    import subprocess

    remote, client = tmp_path / "remote.git", tmp_path / "client"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(client)], check=True, capture_output=True)

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=client, text=True).strip()

    git("config", "user.name", "Nima Test")
    git("config", "user.email", "nima-test@example.invalid")
    git("commit", "--allow-empty", "-m", "synthetic initial")
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "HEAD:refs/heads/main", "HEAD:refs/heads/feature/finished")
    expected = git("rev-parse", "HEAD")
    if advanced:
        git("commit", "--allow-empty", "-m", "synthetic unreviewed work")
        git("push", "origin", "HEAD:refs/heads/feature/finished")
    script = Path(__file__).resolve().parents[1] / "scripts/delete-merged-ref.sh"
    result = subprocess.run(
        ["sh", str(script), "feature/finished", expected, "main"],
        cwd=client,
        capture_output=True,
        text=True,
    )
    remaining = git("ls-remote", "--heads", "origin")
    assert "refs/heads/main" in remaining
    assert ("refs/heads/feature/finished" in remaining) is advanced
    assert result.returncode == (1 if advanced else 0)
    blocked = subprocess.run(
        ["sh", str(script), "main", expected, "main"], cwd=client, capture_output=True, text=True
    )
    assert blocked.returncode == 2 and "refs/heads/main" in git("ls-remote", "--heads", "origin")
