"""Independent fixture controls. Fixed CLI targets, never a live egress check."""

import json
import socket
import ssl
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import httpx

from nima.egress.fixtures import FixtureError, read_counters
from nima.egress.preflight import check_process, report

OBSERVER_FAILURES = frozenset(
    "observer_" + phase
    for phase in (
        "reset",
        "tls_context",
        "canary_http",
        "canary_tls",
        "host_bridge",
        "udp",
        "dns",
        "counters",
        "gateway",
    )
)


@dataclass(frozen=True, slots=True)
class FixtureTargets:
    canary_ip: str = "172.30.240.4"
    host_ip: str = "172.30.240.1"
    http_port: int = 9000
    tls_ports: tuple[int, ...] = (8443, 8444, 443)
    udp_ports: tuple[int, ...] = (3478, 443, 9001)
    dns_port: int = 53
    host_port: int = 18080

    def __post_init__(self) -> None:
        # Loopback is for real socket unit tests, not a configurable CLI profile.
        if (
            self.canary_ip not in {"172.30.240.4", "127.0.0.1"}
            or self.host_ip not in {"172.30.240.1", "127.0.0.1"}
            or not 1 <= len(self.tls_ports) <= 3
            or not 1 <= len(self.udp_ports) <= 3
            or any(
                type(port) is not int or not 1 <= port <= 65535
                for port in (
                    self.http_port,
                    *self.tls_ports,
                    *self.udp_ports,
                    self.dns_port,
                    self.host_port,
                )
            )
        ):
            raise ValueError("fixture_targets")


def _http_control(client: httpx.Client, url: str) -> None:
    body = bytearray()
    with client.stream("GET", url) as response:
        for chunk in response.iter_bytes(chunk_size=1024):
            body.extend(chunk)
            if len(body) > 4096:
                raise FixtureError("observer_response")
        if response.status_code != 200 or body != b"Nima synthetic canary\n":
            raise FixtureError("observer_http")


def fixture_smoke(targets: FixtureTargets, ca_path: Path, control_dir: Path) -> None:
    phase = "reset"
    try:
        read_counters(control_dir / "canary.sock", role="canary", reset=True)
        phase = "tls_context"
        context = ssl.create_default_context(cafile=ca_path)
        with httpx.Client(
            verify=context, trust_env=False, timeout=2, follow_redirects=False
        ) as client:
            phase = "canary_http"
            _http_control(client, f"http://{targets.canary_ip}:{targets.http_port}/")
            phase = "canary_tls"
            for port in targets.tls_ports:
                _http_control(client, f"https://{targets.canary_ip}:{port}/")
            phase = "host_bridge"
            _http_control(client, f"http://{targets.host_ip}:{targets.host_port}/")
        phase = "udp"
        for port in targets.udp_ports:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
                client_socket.settimeout(2)
                client_socket.sendto(b"nima-control", (targets.canary_ip, port))
                reply, peer = client_socket.recvfrom(1232)
                if reply != b"nima-control-ok" or peer != (targets.canary_ip, port):
                    raise FixtureError("observer_udp")
        phase = "dns"
        query = (
            struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
            + b"\x08unmapped\x04nima\x04test\x00"
            + struct.pack("!HH", 1, 1)
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
            client_socket.settimeout(2)
            client_socket.sendto(query, (targets.canary_ip, targets.dns_port))
            reply, peer = client_socket.recvfrom(1232)
            if (
                peer != (targets.canary_ip, targets.dns_port)
                or len(reply) < 16
                or reply[:2] != b"\x12\x34"
                or reply[6:8] != b"\x00\x01"
                or reply[-4:] != socket.inet_aton("172.30.240.4")
            ):
                raise FixtureError("observer_dns")
        phase = "counters"
        canary = read_counters(control_dir / "canary.sock", role="canary")
        if (
            canary["tcp_accepts"] != len(targets.tls_ports) + 1
            or canary["application_requests"] != len(targets.tls_ports) + 1
            or canary["udp_datagrams"] != len(targets.udp_ports)
            or canary["dns_queries"] != 1
            or canary["headers_clean"] is not True
        ):
            raise FixtureError("observer_counters")
    except Exception:
        raise FixtureError("observer_" + phase) from None


class GatewayObservation(TypedDict):
    version: str
    allowed: int
    denied: int
    origin: dict[str, int | bool]
    bad: dict[str, int | bool]


def gateway_observation(*, reset: bool = False) -> GatewayObservation:
    try:
        transport = httpx.HTTPTransport(uds="/gateway-admin/envoy.sock")
        with httpx.Client(transport=transport, timeout=2, trust_env=False) as client:
            body = bytearray()
            with client.stream(
                "GET",
                "http://fixture/stats",
                params={
                    "format": "json",
                    "filter": r"^http\.nima\.rbac\.(allowed|denied)$",
                },
            ) as response:
                if response.status_code != 200:
                    raise FixtureError("observer_gateway")
                for chunk in response.iter_bytes(chunk_size=4096):
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise FixtureError("observer_gateway")
        parsed = json.loads(body)
        if (
            type(parsed) is not dict
            or set(parsed) != {"stats"}
            or type(parsed["stats"]) is not list
        ):
            raise FixtureError("observer_gateway")
        counts: dict[str, int] = {}
        for row in parsed["stats"]:
            if (
                type(row) is not dict
                or set(row) != {"name", "value"}
                or row["name"] not in {"http.nima.rbac.allowed", "http.nima.rbac.denied"}
                or row["name"] in counts
                or type(row["value"]) is not int
                or not 0 <= row["value"] <= 1000000
            ):
                raise FixtureError("observer_gateway")
            counts[row["name"]] = row["value"]
        if len(counts) != 2:
            raise FixtureError("observer_gateway")
        return {
            "version": "source-worker-gateway-observation-v1",
            "allowed": counts["http.nima.rbac.allowed"],
            "denied": counts["http.nima.rbac.denied"],
            "origin": read_counters(Path("/control/origin.sock"), role="origin", reset=reset),
            "bad": read_counters(Path("/control/bad.sock"), role="bad", reset=reset),
        }
    except Exception:
        raise FixtureError("observer_gateway") from None


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in (["fixture-smoke"], ["gateway-observe"], ["gateway-reset"]):
        report("failed", "configuration")
        return 2
    try:
        check_process(Path("/proc/self/status").read_text(), uid=10002)
        if arguments == ["fixture-smoke"]:
            fixture_smoke(FixtureTargets(), Path("/fixture-public/ca.pem"), Path("/control"))
        else:
            print(json.dumps(gateway_observation(reset=arguments == ["gateway-reset"])))
            return 0
    except Exception as exc:
        code = str(exc)
        report("failed", code if code in OBSERVER_FAILURES else "observer_control")
        return 1
    report("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
