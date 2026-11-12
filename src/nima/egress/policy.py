"""Immutable synthetic destinations and budgets; there is no live profile."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum


class PolicyError(ValueError):
    """A fixed reason without configuration values."""


class CaseKind(StrEnum):
    ALLOWED = "allowed"
    BROWSER_RESOURCES = "browser_resources"
    PACKET_BLOCKED = "packet_blocked"
    GATEWAY_REJECTED = "gateway_rejected"
    TLS_REJECTED = "tls_rejected"
    IPV6_DISABLED = "ipv6_disabled"
    GATEWAY_OUTAGE = "gateway_outage"
    RESTARTED = "restarted"


@dataclass(frozen=True, slots=True)
class CaseSpec:
    name: str
    kind: CaseKind

    @property
    def target_counter(self) -> str:
        if self.kind == CaseKind.IPV6_DISABLED:
            return "disabled_mode"
        if self.name in {"http_dns", "browser_dns"}:
            return "dns_queries"
        if self.name in {"http_udp", "browser_quic", "browser_stun"}:
            return "udp_datagrams"
        if self.kind == CaseKind.PACKET_BLOCKED:
            return "tcp_accepts"
        return "application_requests"


CASES = tuple(
    CaseSpec(name, kind)
    for kind, names in (
        (CaseKind.ALLOWED, ("http_allowed",)),
        (CaseKind.BROWSER_RESOURCES, ("browser_resources",)),
        (
            CaseKind.PACKET_BLOCKED,
            (
                "http_direct_ipv4",
                "http_proxy_removed",
                "http_no_proxy",
                "http_trust_env_false",
                "browser_proxy_bypass",
                "http_host_bridge",
                "http_metadata",
                "browser_metadata",
                "http_dns",
                "browser_dns",
                "http_udp",
                "browser_quic",
                "browser_stun",
            ),
        ),
        (CaseKind.IPV6_DISABLED, ("ipv6_disabled",)),
        (
            CaseKind.GATEWAY_REJECTED,
            (
                "http_redirect_host",
                "http_redirect_ip",
                "http_redirect_port",
                "browser_redirect_host",
                "http_missing_auth",
                "http_invalid_auth",
                "browser_invalid_auth",
            ),
        ),
        (CaseKind.TLS_REJECTED, ("http_invalid_tls", "browser_invalid_tls")),
        (CaseKind.GATEWAY_OUTAGE, ("http_gateway_outage", "browser_gateway_outage")),
        (CaseKind.RESTARTED, ("gateway_restart",)),
    )
    for name in names
)


@dataclass(frozen=True, slots=True)
class FixturePolicy:
    version: str = field(default="source-worker-policy-v1", init=False)
    profile: str = field(default="fixtures", init=False)
    front_subnet: str = field(default="172.30.240.0/24", init=False)
    back_subnet: str = field(default="172.30.241.0/24", init=False)
    gateway_ip: str = field(default="172.30.240.2", init=False)
    gateway_port: int = field(default=3128, init=False)
    allowed_authorities: tuple[str, ...] = field(
        default=("allowed.nima.test:8443", "badcert.nima.test:8443"), init=False
    )
    max_cases: int = field(default=30, init=False)
    max_seconds: int = field(default=600, init=False)
    attempt_seconds: int = field(default=15, init=False)
    max_response_bytes: int = field(default=1024**2, init=False)
    max_receipt_bytes: int = field(default=64 * 1024, init=False)
    seccomp_sha256: str = field(
        default="1ec225154906ce8e797e22d7fadaff5b592d273a08774f35c627f5c940faf4b4", init=False
    )
    cases: tuple[CaseSpec, ...] = field(default=CASES, init=False)

    @property
    def digest(self) -> str:
        manifest = asdict(self)
        manifest["cases"] = [
            {**asdict(case), "target_counter": case.target_counter} for case in self.cases
        ]
        return hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def fixture_policy(configuration: object) -> FixturePolicy:
    if type(configuration) is not dict or configuration != {
        "version": "source-worker-policy-v1",
        "profile": "fixtures",
    }:
        raise PolicyError("policy")
    return FixturePolicy()
