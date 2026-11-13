"""Linux-only bounded host command capture; no shell or operator-selected CLI.

Called by the fixture controller with fixed absolute Docker/ip executables and
structured arguments. The private capture primitive also accepts test children.
Output stays private even on failure. Retain the leader as a zombie until its
process group is killed, so its PID cannot be recycled before cleanup.
https://docs.python.org/3.12/library/subprocess.html#subprocess.Popen
https://docs.python.org/3.12/library/os.html#os.waitid
https://docs.python.org/3.12/library/selectors.html
"""

import math
import os
import selectors
import signal

# Host fixture controller only: structured argv, never shell=True or remote input.
import subprocess  # nosec B404
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

OUTPUT_LIMIT = 1024**2


class CommandError(RuntimeError):
    """Fixed codes without argv, environment, stderr or response contents."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = field(repr=False)
    stderr: str = field(repr=False)


def capture(
    argv: tuple[str, ...], *, cwd: Path, env: Mapping[str, str], timeout: float
) -> CommandResult:
    if (
        isinstance(timeout, bool)
        or not math.isfinite(timeout)
        or not 0 < timeout <= 600
        or not argv
        or not Path(argv[0]).is_absolute()
    ):
        raise CommandError("command_configuration")
    deadline = time.monotonic() + timeout

    def remaining() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise CommandError("command_deadline")
        return left

    try:
        # Closed controller callers select executable/argv; no shell expansion.
        child = subprocess.Popen(  # nosec B603
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, ValueError):
        raise CommandError("command_unavailable") from None
    out, err = bytearray(), bytearray()
    try:
        if child.stdout is None or child.stderr is None:
            raise CommandError("command_unavailable")
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ, out)
            selector.register(child.stderr, selectors.EVENT_READ, err)
            while selector.get_map():
                for key, _ in selector.select(min(0.1, remaining())):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif len(out) + len(err) + len(chunk) > OUTPUT_LIMIT:
                        raise CommandError("command_output_limit")
                    else:
                        key.data.extend(chunk)
        # Closed pipes do not mean the process exited. WNOWAIT observes exit
        # without reaping, including a leader whose descendants closed their FDs.
        while os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            time.sleep(min(0.01, remaining()))
        remaining()
    except OSError:
        raise CommandError("command_unavailable") from None
    finally:
        # start_new_session pins this command's PGID to its unreaped leader.
        # Never signal a caller-selected PID, Docker daemon or host service.
        try:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            raise CommandError("command_cleanup") from None
        finally:
            if child.stdout is not None:
                child.stdout.close()
            if child.stderr is not None:
                child.stderr.close()
    try:
        return CommandResult(child.returncode, out.decode("utf-8"), err.decode("utf-8"))
    except UnicodeError:
        raise CommandError("command_encoding") from None
