"""Kill a real publisher before/after its atomic, no-clobber link operation."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from nima.identity import AssessmentError
from nima.identity.artifacts import publish
from tests.test_postgres_crash import wait_until

WORKER = """
import os, signal
from pathlib import Path
from nima.identity.artifacts import publish
original = os.link
def boundary(*args, **kwargs):
    if not args[1].endswith('.json'):
        return original(*args, **kwargs)
    if os.environ['NIMA_REPORT_BOUNDARY'] == 'after':
        original(*args, **kwargs)
    Path(os.environ['NIMA_REPORT_READY']).write_text('ready')
    signal.pause()
os.link = boundary
publish(Path(os.environ['NIMA_REPORT_OUTPUT']), b'{"synthetic":true}')
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_killed_publisher_replays_without_partial_final_file(tmp_path: Path, boundary: str) -> None:
    directory, ready = tmp_path / "out", tmp_path / "ready"
    environment = {
        **os.environ,
        "NIMA_REPORT_BOUNDARY": boundary,
        "NIMA_REPORT_OUTPUT": str(directory),
        "NIMA_REPORT_READY": str(ready),
    }
    with subprocess.Popen([sys.executable, "-c", WORKER], env=environment) as worker:
        try:
            wait_until(ready.exists)
            worker.kill()
            worker.wait(timeout=5)
            assert len(list(directory.glob("*.json"))) == int(boundary == "after")
            digest = publish(directory, b'{"synthetic":true}')
            assert (directory / f"{digest}.json").read_bytes() == b'{"synthetic":true}'
            assert len(list(directory.glob("*.json"))) == 1
        finally:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)


def test_concurrent_identical_publication_is_idempotent(tmp_path: Path) -> None:
    directory = tmp_path / "out"
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: publish(directory, b'{"synthetic":true}'), range(2)))
    assert len(set(results)) == len(list(directory.glob("*.json"))) == 1


def test_reports_are_ignored_even_when_output_is_inside_a_git_checkout(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    digest = publish(tmp_path / "out", b'{"synthetic":true}')
    result = subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "--quiet", f"out/{digest}.json"], check=False
    )
    assert result.returncode == 0


def test_relative_output_cannot_write_inside_git_internals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    internal = tmp_path / ".git"
    internal.mkdir(mode=0o700)
    monkeypatch.chdir(internal)
    with pytest.raises(AssessmentError, match="output_path"):
        publish(Path("reports"), b'{"synthetic":true}')
    assert not (internal / "reports").exists()
