"""Build a conservative deletion plan from GitHub metadata; never execute PR code."""

import argparse
import json
import re
from pathlib import Path
from typing import cast


def _object(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _used(branch: str, repository: str, opened: list[dict[str, object]]) -> bool:
    for pr in opened:
        for side in ("head", "base"):
            ref = _object(pr.get(side))
            if ref.get("ref") == branch and _object(ref.get("repo")).get("full_name") == repository:
                return True
    return False


def plan_cleanup(
    repository: dict[str, object],
    closed: list[dict[str, object]],
    branches: list[dict[str, object]],
    opened: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    name, default = repository.get("full_name"), repository.get("default_branch")
    if not isinstance(name, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", name):
        raise ValueError("repository_invalid")
    if not isinstance(default, str) or not default:
        raise ValueError("default_branch_unknown")
    reserved = {"main", "dev", "stg", "master", "develop", default}
    delete: list[dict[str, object]] = []
    retained: list[dict[str, object]] = []
    for branch in branches:
        ref = branch.get("name")
        sha = _object(branch.get("commit")).get("sha")
        if not isinstance(ref, str) or not ref or any(c.isspace() or ord(c) < 32 for c in ref):
            raise ValueError("branch_invalid")
        reason = "no_matching_merged_pr"
        if ref in reserved or branch.get("protected") is not False:
            reason = "protected"
        elif _used(ref, name, opened):
            reason = "open_pr"
        elif isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{40}", sha):
            for pr in closed:
                head = _object(pr.get("head"))
                if (
                    pr.get("merged_at")
                    and head.get("ref") == ref
                    and head.get("sha") == sha
                    and _object(head.get("repo")).get("full_name") == name
                    and type(pr.get("number")) is int
                ):
                    delete.append({"branch": ref, "sha": sha, "pr_number": pr["number"]})
                    break
            else:
                retained.append({"branch": ref, "reason": reason})
            continue
        retained.append({"branch": ref, "reason": reason})
    return {"delete": delete, "retained": retained}


def _text(path: Path) -> str:
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("metadata_limit")
    return path.read_text()


def _read(path: Path) -> object:
    return json.loads(_text(path))


def _list(path: Path) -> list[dict[str, object]]:
    # gh --paginate emits consecutive JSON pages; works with older CLIs too.
    text = _text(path).strip()
    if not text:
        raise ValueError("metadata_empty")
    result: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    while text:
        value, end = decoder.raw_decode(text)
        if not isinstance(value, list) or any(not isinstance(v, dict) for v in value):
            raise ValueError("metadata_invalid")
        result.extend(cast(list[dict[str, object]], value))
        text = text[end:].lstrip()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("repository", "closed", "branches", "open"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        repository = _object(_read(args.repository))
        result = plan_cleanup(
            repository, _list(args.closed), _list(args.branches), _list(args.open)
        )
    except (ValueError, OSError):
        print(json.dumps({"status": "blocked", "reason": "metadata_invalid"}))
        return 1
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
