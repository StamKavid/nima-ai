"""Explicit Linux/Docker tests, never skipped or included in ordinary discovery.

The shared host controller creates only UUID-labelled closed fixtures; cleanup
verifies and removes exact IDs. Application execution remains fixture-only.
"""

import json
from pathlib import Path
from typing import Any

from nima.egress.fixtures import Counters, http_server
from nima.egress.policy import CaseKind
from nima.egress.probe_http import HTTP_CASES, read_result
from nima.egress.receipt import CaseEvidence, validate_case
from nima.egress.stack import FixtureStack


def test_closed_fixture_services_and_private_controls(tmp_path: Path) -> None:
    stack = FixtureStack(tmp_path)
    stack.prepare()
    try:
        stack.start()
        host = Counters()
        # Native host listener: Docker-published ports on an internal bridge do
        # not provide a reachable host-boundary positive control. Bind only the
        # disposable bridge address; counters stay in this trusted controller.
        with http_server(
            ("172.30.240.1", 18080), host, role="host", context=None, credentials=stack.auth
        ) as address:
            assert address == ("172.30.240.1", 18080)
            observer = json.loads(stack.compose("run", "--rm", "--no-deps", "observer"))
            assert observer["status"] == "passed"
            assert observer["investigator_ip_protection_verified"] is False
            worker = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "worker",
                    "python",
                    "-m",
                    "nima.egress.preflight",
                    "controls",
                )
            )
            assert worker["status"] == "passed"
            assert worker["production_ready"] is False
            snapshot = host.snapshot()
            assert snapshot["application_requests"] == 1
            assert snapshot["headers_clean"] is True
            assert snapshot["server_errors"] == 0
    finally:
        stack.cleanup()


def test_real_gateway_auth_tls_and_browser_resources(tmp_path: Path) -> None:
    stack = FixtureStack(tmp_path)
    stack.prepare()
    try:
        stack.start()
        for mode, applications in (("http", 1), ("browser", 5)):
            before = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "observer",
                    "python",
                    "-m",
                    "nima.egress.observer",
                    "gateway-reset",
                )
            )
            result = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "worker",
                    "python",
                    "-m",
                    "nima.egress.protocol",
                    mode,
                )
            )
            assert result["status"] == "passed"
            assert result["investigator_ip_protection_verified"] is False
            after = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "observer",
                    "python",
                    "-m",
                    "nima.egress.observer",
                    "gateway-observe",
                )
            )
            assert after["allowed"] - before["allowed"] >= 2
            assert after["denied"] > before["denied"]
            if mode == "http":
                assert after["denied"] - before["denied"] == 5
            assert after["origin"]["application_requests"] == applications
            assert after["origin"]["headers_clean"] is True
            assert after["bad"]["tcp_accepts"] >= 1
            assert after["bad"]["application_requests"] == 0
            assert after["bad"]["headers_clean"] is True
            if mode == "browser":
                assert all(
                    after["origin"][resource] == 1
                    for resource in ("html", "script", "image", "xhr", "fetch")
                )
    finally:
        stack.cleanup()


def test_packet_policy_blocks_real_delivery_and_user_namespace_bypass(tmp_path: Path) -> None:
    stack = FixtureStack(tmp_path)
    stack.prepare()
    try:
        stack.start()
        stack.compose("up", "-d", "--wait", "--no-deps", "metadata")
        host = Counters()
        with http_server(
            ("172.30.240.1", 18080), host, role="host", context=None, credentials=stack.auth
        ):
            controls = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "observer",
                    "python",
                    "-m",
                    "nima.egress.observer",
                    "packet-control",
                )
            )
            assert controls["metadata"]["application_requests"] == 1
            assert host.snapshot()["application_requests"] == 1
            host.reset()
            reset = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "observer",
                    "python",
                    "-m",
                    "nima.egress.observer",
                    "packet-reset",
                )
            )
            assert reset["canary"]["tcp_accepts"] == 0
            assert reset["metadata"]["application_requests"] == 0
            before = json.loads(stack.compose("run", "--rm", "--no-deps", "network-inspect"))
            result = json.loads(stack.compose("run", "--rm", "--no-deps", "network-probe"))
            assert result["status"] == "passed"
            after = json.loads(stack.compose("run", "--rm", "--no-deps", "network-inspect"))
            targets = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "observer",
                    "python",
                    "-m",
                    "nima.egress.observer",
                    "packet-observe",
                )
            )
            assert before["policy_sha256"] == after["policy_sha256"]
            assert before["network_inode"] == after["network_inode"]
            assert after["ipv6_disabled"] is True
            assert after["metadata_alias"] is True
            for name in (
                "direct_tcp",
                "host_tcp",
                "metadata_tcp",
                "dns_udp",
                "direct_udp",
                "quic_udp",
                "stun_udp",
            ):
                assert after["counters"][name]["packets"] > before["counters"][name]["packets"]
            for name in ("canary", "metadata"):
                assert all(
                    targets[name][metric] == 0
                    for metric in (
                        "tcp_accepts",
                        "application_requests",
                        "dns_queries",
                        "udp_datagrams",
                        "server_errors",
                    )
                )
            assert host.snapshot()["application_requests"] == 0
            assert host.snapshot()["tcp_accepts"] == 0
            assert host.snapshot()["server_errors"] == 0
    finally:
        stack.cleanup()


def test_all_http_cases_reconcile_real_controls_delivery_and_gateway_outage(tmp_path: Path) -> None:
    stack = FixtureStack(tmp_path)
    stack.prepare()

    def observe(command: str) -> dict[str, Any]:
        value: dict[str, Any] = json.loads(
            stack.compose(
                "run",
                "--rm",
                "--no-deps",
                "observer",
                "python",
                "-m",
                "nima.egress.observer",
                command,
            )
        )
        assert type(value) is dict
        return value

    def network() -> dict[str, Any]:
        value: dict[str, Any] = json.loads(
            stack.compose("run", "--rm", "--no-deps", "network-inspect")
        )
        assert type(value) is dict
        return value

    drops = {
        "http_direct_ipv4": "direct_tcp",
        "http_proxy_removed": "direct_tcp",
        "http_no_proxy": "direct_tcp",
        "http_trust_env_false": "direct_tcp",
        "http_host_bridge": "host_tcp",
        "http_metadata": "metadata_tcp",
        "http_dns": "dns_udp",
        "http_udp": "direct_udp",
    }
    completed = []
    stopped_gateway_id = None
    try:
        stack.start()
        stack.compose("up", "-d", "--wait", "--no-deps", "metadata")
        host = Counters()
        with http_server(
            ("172.30.240.1", 18080), host, role="host", context=None, credentials=stack.auth
        ):
            for case in HTTP_CASES:
                if case.name == "gateway_restart":
                    # Compose start also restarts the one-shot initializer.
                    # Keep its refuse-overwrite guard and restart only the
                    # exact gateway container observed stopped in the outage.
                    assert stopped_gateway_id is not None
                    stack.command("start", stopped_gateway_id)
                gateway_id = stack.compose("ps", "--all", "--quiet", "gateway")
                if case.name == "gateway_restart":
                    assert stopped_gateway_id == gateway_id
                assert (
                    stack.command("inspect", gateway_id, "--format", "{{.State.Running}}") == "true"
                )
                # Healthy controls precede every attempt, including the outage.
                controls = observe("gateway-control")
                assert controls["allowed"] >= 2
                observe("packet-control")
                assert host.snapshot()["application_requests"] == 1
                host.reset()
                observe("packet-reset")
                before_gateway = observe("gateway-reset")
                before = network()
                stopped = case.kind == CaseKind.GATEWAY_OUTAGE
                if stopped:
                    stack.compose("stop", "--timeout", "3", "gateway")
                    assert (
                        stack.command("inspect", gateway_id, "--format", "{{.State.Running}}")
                        == "false"
                    )
                    stopped_gateway_id = gateway_id
                raw = stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "worker",
                    "python",
                    "-m",
                    "nima.egress.probe_http",
                    case.name,
                )
                result = read_result((raw + "\n").encode(), case.name)
                after = network()
                packets = observe("packet-observe")
                gateway = observe("origins-observe" if stopped else "gateway-observe")
                assert before["policy_sha256"] == after["policy_sha256"]
                assert before["network_inode"] == after["network_inode"]
                assert after["ipv6_disabled"] is True and after["metadata_alias"] is True
                for role in ("canary", "metadata"):
                    assert all(
                        packets[role][metric] == 0
                        for metric in (
                            "tcp_accepts",
                            "application_requests",
                            "dns_queries",
                            "udp_datagrams",
                            "server_errors",
                        )
                    )
                    assert packets[role]["headers_clean"] is True
                assert host.snapshot()["tcp_accepts"] == 0
                assert host.snapshot()["application_requests"] == 0
                assert host.snapshot()["server_errors"] == 0
                for role in ("origin", "bad"):
                    assert gateway[role]["headers_clean"] is True
                    assert gateway[role]["server_errors"] == 0
                target = "bad" if case.kind == CaseKind.TLS_REJECTED else "origin"
                deliveries: int | None
                if case.kind == CaseKind.PACKET_BLOCKED:
                    sink = (
                        host.snapshot()
                        if case.name == "http_host_bridge"
                        else packets["metadata" if case.name == "http_metadata" else "canary"]
                    )
                    deliveries = int(sink[case.target_counter])
                elif case.name.startswith("http_redirect_"):
                    deliveries = packets["canary"][case.target_counter]
                else:
                    deliveries = (
                        gateway[target][case.target_counter]
                        if case.kind != CaseKind.IPV6_DISABLED
                        else None
                    )
                policy_drops = (
                    after["counters"][drops[case.name]]["packets"]
                    - before["counters"][drops[case.name]]["packets"]
                    if case.name in drops
                    else None
                )
                evidence = CaseEvidence(
                    case.name,
                    case.target_counter,
                    result,
                    control_success=None if case.kind == CaseKind.IPV6_DISABLED else True,
                    target_deliveries=deliveries,
                    gateway_tunnels=None
                    if stopped
                    else gateway["allowed"] - before_gateway["allowed"],
                    gateway_rejections=None
                    if stopped
                    else gateway["denied"] - before_gateway["denied"],
                    policy_drops=policy_drops,
                    observed_routes=frozenset({"html"})
                    if gateway["origin"]["html"] == 1
                    else frozenset(),
                    headers_clean=gateway["origin"]["headers_clean"],
                    gateway_stopped=True if stopped else None,
                    gateway_restarted=True if case.name == "gateway_restart" else None,
                )
                validate_case(evidence)
                completed.append(case.name)
            assert completed == [case.name for case in HTTP_CASES]
    finally:
        stack.cleanup()
