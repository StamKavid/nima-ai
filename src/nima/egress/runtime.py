"""Observed process/kernel state, independent of declared container settings."""

import os
from dataclasses import dataclass
from pathlib import Path

from nima.egress.preflight import check_process


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
