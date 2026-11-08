"""Verify the project-local skill snapshot against its recorded file hashes."""

import hashlib
import json
from pathlib import Path


def verify_skills(root: Path) -> list[str]:
    """Return integrity failures without reading paths outside the installation."""
    try:
        manifest = json.loads((root / "skills.lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["Invalid skill lockfile"]

    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("files"), dict)
        or not isinstance(manifest.get("skill_names"), list)
        or not all(isinstance(name, str) for name in manifest["skill_names"])
        or not all(
            isinstance(path, str) and isinstance(digest, str)
            for path, digest in manifest["files"].items()
        )
    ):
        return ["Invalid skill lockfile"]

    errors: list[str] = []
    resolved_root = root.resolve()
    for relative, expected_hash in manifest["files"].items():
        path = root / relative
        if not path.resolve().is_relative_to(resolved_root):
            errors.append(f"Unsafe manifest path: {relative}")
        elif not path.is_file():
            errors.append(f"Missing file: {relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            errors.append(f"Changed file: {relative}")

    installed_names = sorted(path.parent.name for path in (root / "skills").glob("*/SKILL.md"))
    if installed_names != sorted(manifest["skill_names"]):
        errors.append("Installed skill names differ from the lockfile")
    return errors


def main(root: Path | None = None) -> int:
    """Check this checkout and use a nonzero exit status for any detected drift."""
    if root is None:
        root = Path(__file__).resolve().parents[1] / ".agents"
    errors = verify_skills(root)
    for error in errors:
        print(error)
    if errors:
        return 1
    print("Installed skill snapshot matches its lockfile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
