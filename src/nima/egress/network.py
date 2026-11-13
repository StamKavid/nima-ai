"""Scoped fixture setup/readback. Never flush rules or select an operator namespace.

Only the fixed absolute nft/ip tools are invoked, without a shell, with bounded
output/time and a clean locale environment. The narrow B404/B603 suppressions cover
only this closed operation map; no caller-supplied executable, arguments or stdin exist.
https://manpages.debian.org/bookworm/nftables/nft.8.en.html
https://manpages.debian.org/bookworm/iproute2/ip-address.8.en.html
"""

import json

# Required for the closed nft/ip operation map; no caller-supplied commands.
import subprocess  # nosec B404
import sys
from pathlib import Path

from nima.egress.preflight import check_process, report
from nima.egress.rules import (
    NetworkError,
    NetworkSnapshot,
    decode_ruleset,
    nft_objects,
    policy_payload,
)

NETWORK_FAILURES = frozenset(
    "network_" + name
    for name in (
        "readback",
        "policy",
        "counter",
        "tool",
        "existing",
        "namespace",
        "ipv6",
        "helper",
        "probe",
        "privileges",
    )
)


def _run(operation: str) -> bytes:
    commands = {
        "addresses": ("ip", "-j", "-4", "address", "show"),
        "alias": ("ip", "address", "add", "169.254.169.254/32", "dev", "lo"),
        "tables": ("nft", "--json", "--numeric", "list", "tables"),
        "read": ("nft", "--json", "--numeric", "list", "table", "inet", "nima_worker"),
        "check": ("nft", "--check", "--json", "--file", "-"),
        "install": ("nft", "--json", "--file", "-"),
        "forbidden": ("nft", "add", "table", "inet", "nima_unauthorized"),
    }
    if operation not in commands:
        raise NetworkError("network_tool")
    tool, *arguments = commands[operation]
    executable = next(
        (
            str(path)
            for base in ("/usr/sbin", "/usr/bin", "/sbin", "/bin")
            if (path := Path(base) / tool).is_file()
        ),
        None,
    )
    if executable is None:
        raise NetworkError("network_tool")
    try:
        # Fixed absolute executable/argv, no shell or external stdin (see docstring).
        result = subprocess.run(  # nosec B603
            [executable, *arguments],
            shell=False,
            check=False,
            capture_output=True,
            input=policy_payload() if operation in {"check", "install"} else None,
            timeout=10,
            env={"LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        raise NetworkError("network_tool") from None
    if len(result.stdout) > 65536 or len(result.stderr) > 65536:
        raise NetworkError("network_tool")
    if operation == "forbidden":
        if result.returncode == 0 or b"Operation not permitted" not in result.stderr:
            raise NetworkError("network_privileges")
    elif result.returncode:
        raise NetworkError("network_tool")
    return result.stdout


def namespace_state(*, installed: bool) -> int:
    try:
        rows = json.loads(_run("addresses"))
        if type(rows) is not list or {row["ifname"] for row in rows} != {"lo", "eth0"}:
            raise NetworkError("network_namespace")
        actual = {
            (row["ifname"], address["local"], address["prefixlen"])
            for row in rows
            for address in row["addr_info"]
            if address["family"] == "inet"
        }
        required = {("lo", "127.0.0.1", 8), ("eth0", "172.30.240.3", 24)}
        if installed:
            required.add(("lo", "169.254.169.254", 32))
        if actual != required:
            raise NetworkError("network_namespace")
        for name in ("all", "default", "lo", "eth0"):
            if Path("/proc/sys/net/ipv6/conf/" + name + "/disable_ipv6").read_text().strip() != "1":
                raise NetworkError("network_ipv6")
        for name in ("ip_forward", "ip_nonlocal_bind"):
            if Path("/proc/sys/net/ipv4/" + name).read_text().strip() != "0":
                raise NetworkError("network_namespace")
        return Path("/proc/self/ns/net").stat().st_ino
    except NetworkError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise NetworkError("network_namespace") from None


def inspect() -> tuple[NetworkSnapshot, int]:
    check_process(Path("/proc/self/status").read_text(), helper=True)
    inode = namespace_state(installed=True)
    return decode_ruleset(_run("read")), inode


def install() -> tuple[NetworkSnapshot, int]:
    check_process(Path("/proc/self/status").read_text(), helper=True)
    namespace_state(installed=False)
    tables = nft_objects(_run("tables"))
    if any(type(row.get("table")) is not dict for row in tables):
        raise NetworkError("network_readback")
    if any(
        row["table"].get("family") == "inet" and row["table"].get("name") == "nima_worker"
        for row in tables
    ):
        raise NetworkError("network_existing")
    _run("check")
    _run("install")
    _run("alias")
    return inspect()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in (["install"], ["inspect"]):
        report("failed", "configuration")
        return 2
    try:
        snapshot, inode = install() if arguments == ["install"] else inspect()
        print(
            json.dumps(
                {
                    "version": "source-worker-network-v1",
                    "scope": "fixtures",
                    "status": "passed",
                    "policy_sha256": snapshot.fingerprint,
                    "network_inode": inode,
                    "counters": {
                        name: {"packets": packets, "bytes": size}
                        for name, packets, size in snapshot.counters
                    },
                    "metadata_alias": True,
                    "ipv6_disabled": True,
                    "investigator_ip_protection_verified": False,
                    "internet_egress_verified": False,
                    "production_ready": False,
                }
            )
        )
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception as exc:
        report("failed", str(exc) if str(exc) in NETWORK_FAILURES else "network_helper")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
