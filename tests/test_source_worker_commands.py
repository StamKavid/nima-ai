"""Real child processes prove bounds without Docker or source connections."""

import os
import sys
import time
from pathlib import Path

import pytest

from nima.egress.commands import CommandError, capture


def run(code: str, tmp_path: Path, *, timeout: float = 2) -> str:
    result = capture((sys.executable, "-c", code), cwd=tmp_path, env={}, timeout=timeout)
    assert result.returncode == 0
    return result.stdout


def test_bounded_capture_preserves_exact_streams_and_private_representation(tmp_path: Path) -> None:
    result = capture(
        (
            sys.executable,
            "-c",
            "import sys; print('private-sentinel'); sys.stderr.write('detail'); sys.exit(7)",
        ),
        cwd=tmp_path,
        env={},
        timeout=2,
    )
    assert result.returncode == 7
    assert result.stdout == "private-sentinel\n" and result.stderr == "detail"
    assert "private-sentinel" not in repr(result) and "detail" not in repr(result)


@pytest.mark.parametrize("stream", ["stdout", "stderr", "both"])
def test_output_is_limited_while_the_child_is_still_writing(tmp_path: Path, stream: str) -> None:
    code = "import os\n" + (
        "while True: os.write(1, b'x'*65536); os.write(2,b'x'*65536)"
        if stream == "both"
        else "while True: os.write(" + ("1" if stream == "stdout" else "2") + ",b'x'*65536)"
    )
    with pytest.raises(CommandError, match="^command_output_limit$"):
        run(code, tmp_path)


@pytest.mark.parametrize("mode", ["sleep", "closed_pipes", "child_holds_pipes"])
def test_timeout_kills_the_owned_process_group(tmp_path: Path, mode: str) -> None:
    code = "import os,time\n"
    if mode == "closed_pipes":
        code += "os.close(1); os.close(2)\n"
    elif mode == "child_holds_pipes":
        code += "if os.fork(): os._exit(0)\n"
    code += "time.sleep(10)"
    started = time.monotonic()
    with pytest.raises(CommandError, match="^command_deadline$"):
        run(code, tmp_path, timeout=0.1)
    assert time.monotonic() - started < 3


def test_success_cleans_background_children_before_reaping_leader(tmp_path: Path) -> None:
    code = (
        "import os,time\nif os.fork()==0:\n os.close(1); os.close(2); time.sleep(0.3);"
        " open('leak','w').write('bad'); os._exit(0)\nprint('done')"
    )
    assert run(code, tmp_path) == "done\n"
    time.sleep(0.4)
    assert not (tmp_path / "leak").exists()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_limits_are_rejected_before_spawning(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(CommandError, match="^command_configuration$"):
        run("raise Exception('never')", tmp_path, timeout=timeout)


def test_unavailable_and_non_utf8_commands_have_fixed_errors(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="^command_unavailable$"):
        capture(("/missing-private-sentinel",), cwd=tmp_path, env={}, timeout=1)
    with pytest.raises(CommandError, match="^command_encoding$"):
        run("import os; os.write(1,b'\\xff')", tmp_path)


def test_supplied_environment_does_not_inherit_host_secrets(tmp_path: Path) -> None:
    assert run("import os; print(os.getenv('HOME', 'absent'))", tmp_path) == "absent\n"
    assert os.getpid() > 0
