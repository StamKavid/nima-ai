"""Every relative Markdown link in tracked documents must resolve to a file."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)\s]+)\)")
SKIPPED = (".agents/",)


def _documents() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [ROOT / name for name in listed if not name.startswith(SKIPPED) and (ROOT / name).exists()]


def _broken(document: Path) -> list[str]:
    broken = []
    for target in LINK.findall(document.read_text(encoding="utf-8")):
        path = target.split("#", 1)[0]
        if not path or re.match(r"^[a-z][a-z0-9+.-]*:", path) or path.startswith("/"):
            continue
        if not (document.parent / path).exists():
            broken.append(target)
    return broken


def test_relative_markdown_links_resolve() -> None:
    failures = {
        str(document.relative_to(ROOT)): broken
        for document in _documents()
        if (broken := _broken(document))
    }
    assert failures == {}
