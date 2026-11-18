"""Read committed ODCS interfaces without executing historical code or source data."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Never

from nima.contracts.schema import ContractError, check_compatibility, validate_contract

DIRECTORY = "src/nima/contracts"
MAX_CONTRACTS = 64
MAX_BLOB_BYTES = 256 * 1024
MAX_TREE_BYTES = 64 * 1024
_SHA = re.compile(r"[0-9a-f]{40}")
_NAME = re.compile(rb"[a-z0-9][a-z0-9-]*\.odcs\.json")


class BaselineError(ValueError):
    """Fixed reason only; Git stderr, descriptor contents and paths stay out."""


def _git(
    root: Path, *args: str, limit: int = MAX_TREE_BYTES, codes: tuple[int, ...] = (0,)
) -> bytes:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(root), *args],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise BaselineError("contracts_history") from None
    if result.returncode not in codes:
        raise BaselineError("contracts_history")
    if len(result.stdout) > limit:
        raise BaselineError("contracts_limit")
    return result.stdout


def _commit(root: Path, value: str) -> None:
    if _SHA.fullmatch(value) is None:
        raise BaselineError("contracts_configuration")
    if _git(root, "cat-file", "-t", value).strip() != b"commit":
        raise BaselineError("contracts_history")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for name, item in pairs:
        if name in value:
            raise BaselineError("contracts_invalid")
        value[name] = item
    return value


def _constant(value: str) -> Never:
    raise BaselineError("contracts_invalid")


def _entries(raw: bytes) -> list[tuple[bytes, bytes, bytes, bytes]]:
    entries = []
    for row in raw.split(b"\0"):
        if row:
            header, name = row.split(b"\t", 1)
            mode, kind, oid = header.split(b" ")
            entries.append((mode, kind, oid, name))
    return entries


def _catalogue(root: Path, commit: str) -> dict[str, dict[str, Any]]:
    directories = _entries(_git(root, "ls-tree", "-z", commit, "--", DIRECTORY))
    if not directories:
        return {}
    if len(directories) != 1 or directories[0][0:2] != (b"040000", b"tree"):
        raise BaselineError("contracts_mode")
    entries = _entries(_git(root, "ls-tree", "-z", directories[0][2].decode("ascii")))
    descriptors = [entry for entry in entries if entry[3].endswith(b".odcs.json")]
    if len(descriptors) > MAX_CONTRACTS:
        raise BaselineError("contracts_limit")
    catalogue: dict[str, dict[str, Any]] = {}
    for mode, kind, oid, name in descriptors:
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            raise BaselineError("contracts_mode")
        if _NAME.fullmatch(name) is None:
            raise BaselineError("contracts_invalid")
        object_id = oid.decode("ascii")
        size = int(_git(root, "cat-file", "-s", object_id))
        if size > MAX_BLOB_BYTES:
            raise BaselineError("contracts_limit")
        raw = _git(root, "cat-file", "blob", object_id, limit=MAX_BLOB_BYTES)
        value = validate_contract(
            json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        )
        identity = value["id"]
        if identity in catalogue:
            raise BaselineError("contracts_duplicate")
        catalogue[identity] = value
    return catalogue


def check_repository(root: Path, *, base: str, head: str) -> dict[str, int]:
    """Compare one current descriptor per ID using the current supported profile."""
    try:
        # Promisor clones can fetch missing objects implicitly. Refuse them first.
        if _git(
            root,
            "config",
            "--get-regexp",
            r"^(remote\..*\.promisor|extensions\.partial[Cc]lone)$",
            codes=(0, 1),
        ):
            raise BaselineError("contracts_history")
        _commit(root, base)
        _commit(root, head)
        _git(root, "merge-base", "--is-ancestor", base, head)
        previous, current = _catalogue(root, base), _catalogue(root, head)
        if previous.keys() - current.keys():
            raise BaselineError("contracts_removed")
        if not current:
            raise BaselineError("contracts_empty")
        result = {
            "total": len(current),
            "compared": len(previous),
            "added": len(current.keys() - previous.keys()),
            "unchanged": 0,
            "patch": 0,
            "minor": 0,
            "major": 0,
        }
        for identity, old in previous.items():
            result[check_compatibility(old, current[identity])] += 1
        return result
    except BaselineError:
        raise
    except ContractError as error:
        reason = str(error)
        if reason not in {"contract_version", "contract_breaking_change", "contract_identity"}:
            reason = "contracts_invalid"
        raise BaselineError(reason) from None
    except (ValueError, KeyError, TypeError, RecursionError):
        raise BaselineError("contracts_invalid") from None
