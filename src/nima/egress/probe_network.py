"""Fixed synthetic packet/privilege probes. No configurable targets or live mode."""

import errno
import os
import socket
import sys
from pathlib import Path

from nima.egress.network import NETWORK_FAILURES, _run, namespace_state
from nima.egress.preflight import check_process, check_socket_mark, report
from nima.egress.rules import NetworkError


def blocked_tcp(address: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as channel:
        channel.settimeout(1)
        try:
            channel.connect((address, port))
        except OSError as exc:
            if isinstance(exc, TimeoutError) or exc.errno in {errno.EPERM, errno.EACCES}:
                return
        raise NetworkError("network_probe")


def blocked_udp(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as channel:
        channel.settimeout(1)
        try:
            channel.sendto(b"nima-control", ("172.30.240.4", port))
            channel.recvfrom(1232)
        except OSError as exc:
            if isinstance(exc, TimeoutError) or exc.errno in {errno.EPERM, errno.EACCES}:
                return
        raise NetworkError("network_probe")


def child_probe() -> None:
    parent = Path("/proc/self/ns/net").stat().st_ino
    os.unshare(os.CLONE_NEWUSER)
    # An inner UID of 10002 must still map to the workload's OUTER UID 10001.
    # Mapping the actual observer identity is forbidden without parent privilege.
    try:
        Path("/proc/self/uid_map").write_text("10002 10002 1\n")
    except PermissionError:
        pass
    else:
        raise NetworkError("network_privileges")
    Path("/proc/self/uid_map").write_text("10002 10001 1\n")
    if os.getuid() != 10002 or Path("/proc/self/ns/net").stat().st_ino != parent:
        raise NetworkError("network_privileges")
    fields = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    if not int(fields.get("CapEff", "0"), 16) & 0x1000:
        raise NetworkError("network_privileges")
    check_socket_mark(helper=False)  # Own-userns NET_ADMIN cannot administer parent netns.
    blocked_tcp("172.30.240.4", 9000)  # Inner "observer" UID does not bypass the outer-UID rule.
    _run("forbidden")


def privilege_probe() -> None:
    check_socket_mark(helper=False)
    try:
        os.setuid(10002)
    except PermissionError:
        pass
    else:
        raise NetworkError("network_privileges")
    _run("forbidden")
    child = os.fork()
    if child == 0:
        try:
            child_probe()
        except BaseException:
            os._exit(1)
        os._exit(0)
    _, status = os.waitpid(child, 0)
    if status:
        raise NetworkError("network_privileges")


def probe() -> None:
    check_process(Path("/proc/self/status").read_text())
    namespace_state(installed=True)
    # These checks precede all metadata traffic and DNS calls.
    if (
        Path("/etc/resolv.conf").read_bytes()
        != b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n"
    ):
        raise NetworkError("network_namespace")
    privilege_probe()
    for address, port in (("172.30.240.4", 9000), ("172.30.240.1", 18080), ("169.254.169.254", 80)):
        blocked_tcp(address, port)
    for port in (9001, 443, 3478):
        blocked_udp(port)
    try:
        socket.getaddrinfo("unmapped.nima.test", 8443, socket.AF_INET)
    except socket.gaierror:
        pass  # The host also requires a positive DNS control and a kernel drop counter.
    else:
        raise NetworkError("network_probe")


def main(argv: list[str] | None = None) -> int:
    if (sys.argv[1:] if argv is None else argv) != ["raw"]:
        report("failed", "configuration")
        return 2
    try:
        probe()
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception as exc:
        report("failed", str(exc) if str(exc) in NETWORK_FAILURES else "network_probe")
        return 1
    report("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
