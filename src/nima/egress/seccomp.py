"""One reviewed compatibility rule; the upstream profile remains immutable.

Chromium requires chroot inside its own user namespace. The parent has no
SYS_CHROOT and must remain unable to call it. See the real prerequisite probe.
https://chromium.googlesource.com/chromium/src/+/158.0.8127.18/sandbox/linux/services/credentials.cc#56
"""

import hashlib
import json

UPSTREAM_SHA256 = "cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849"


def build_profile(upstream: bytes) -> bytes:
    if hashlib.sha256(upstream).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("profile_identity")
    profile = json.loads(upstream)
    profile["syscalls"].append(
        {
            "names": ["chroot"],
            "action": "SCMP_ACT_ALLOW",
            "args": [],
            "includes": {},
            "excludes": {},
            "comment": "Chromium user-namespace sandbox; parent SYS_CHROOT remains absent",
        }
    )
    return json.dumps(profile, sort_keys=True, separators=(",", ":")).encode() + b"\n"
