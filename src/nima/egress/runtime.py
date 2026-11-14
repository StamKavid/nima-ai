"""Observed process/kernel state, independent of declared container settings."""

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nima.egress.preflight import check_process, report


@dataclass(frozen=True, slots=True)
class ProcessState:
    uid: int
    cap_effective: int
    cap_permitted: int
    cap_bounding: int
    no_new_privs: int
    seccomp: int
    root_readonly: bool
    network_inode: int


def validate_process(state: ProcessState, *, uid: int) -> None:
    expected = (uid, 0, 0, 0, 1, 2)
    observed = (
        state.uid,
        state.cap_effective,
        state.cap_permitted,
        state.cap_bounding,
        state.no_new_privs,
        state.seccomp,
    )
    if (
        uid not in {10001, 10002}
        or any(
            type(value) is not int or value != wanted
            for value, wanted in zip(observed, expected, strict=True)
        )
        or state.root_readonly is not True
        or type(state.network_inode) is not int
        or not 0 < state.network_inode < 2**64
    ):
        raise ValueError("runtime_process")


def observe_process(*, uid: int = 10001) -> ProcessState:
    raw = Path("/proc/self/status").read_text()
    check_process(raw, uid=uid)
    values = {line.partition(":")[0]: line.partition(":")[2].strip() for line in raw.splitlines()}
    state = ProcessState(
        int(values["Uid"].split()[0]),
        int(values["CapEff"], 16),
        int(values["CapPrm"], 16),
        int(values["CapBnd"], 16),
        int(values["NoNewPrivs"]),
        int(values["Seccomp"]),
        bool(os.statvfs("/").f_flag & os.ST_RDONLY),
        Path("/proc/self/ns/net").stat().st_ino,
    )
    validate_process(state, uid=uid)
    return state


def snapshot(role: str) -> dict[str, Any]:
    if role not in {"observer", "gateway"}:
        raise ValueError("configuration")
    process = observe_process(uid=10002)
    forwarding = None
    if role == "gateway":
        forwarding = Path("/proc/sys/net/ipv4/ip_forward").read_text() == "0\n"
        if not forwarding:
            raise ValueError("runtime_forwarding")
    return {
        "version": "source-worker-runtime-v1",
        "role": role,
        "process": asdict(process),
        "gateway_forwarding_disabled": forwarding,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {"observer", "gateway"}:
        report("failed", "configuration")
        return 2
    try:
        value = snapshot(args[0])
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception:
        report("failed", "runtime_observation")
        return 1
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
