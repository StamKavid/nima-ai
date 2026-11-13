"""Explicit Linux/Docker tests, never skipped or included in ordinary discovery.

This temporary test controller creates only UUID-labelled closed fixtures. The
application runner is a later increment; cleanup verifies and removes exact IDs.
"""

import json
import os
import re
import secrets
import stat
from ipaddress import ip_network
from pathlib import Path
from typing import Any
from uuid import uuid4

from nima.egress.commands import capture
from nima.egress.fixtures import Counters, http_server
from nima.egress.network import NETWORK_FAILURES
from nima.egress.observer import OBSERVER_FAILURES
from nima.egress.policy import CaseKind
from nima.egress.preflight import check_host
from nima.egress.probe_http import HTTP_CASES, read_result
from nima.egress.protocol import PROTOCOL_FAILURES
from nima.egress.receipt import CaseEvidence, validate_case
from nima.egress.seccomp import build_profile

ROOT = Path(__file__).resolve().parents[1]


class FixtureStack:
    def __init__(self, state: Path) -> None:
        self.state = state
        self.run_id = str(uuid4())
        self.project = "nima-egress-" + self.run_id.replace("-", "")
        self.docker = next(
            (path for path in ("/usr/bin/docker", "/usr/local/bin/docker") if Path(path).is_file()),
            "",
        )
        if not self.docker or stat.S_IMODE(state.stat().st_mode) != 0o700:
            raise RuntimeError("fixture_prerequisite")
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_TLS",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
            }
        }
        self.env_file = state / "fixture.env"
        self.auth = ("nima-fixture-" + secrets.token_urlsafe(12), secrets.token_urlsafe(32))

    def command(self, *arguments: str, timeout: int = 90) -> str:
        result = capture(
            (self.docker, "--host=unix:///var/run/docker.sock", *arguments),
            cwd=ROOT,
            env=self.environment,
            timeout=timeout,
        )
        if result.returncode:
            # No CalledProcessError, raw daemon output, configuration or secrets.
            for line in result.stdout.splitlines()[:16]:
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if (
                    type(value) is dict
                    and value.get("version") == "source-worker-preflight-v1"
                    and value.get("failure")
                    in OBSERVER_FAILURES | PROTOCOL_FAILURES | NETWORK_FAILURES
                ):
                    raise RuntimeError(value["failure"])
            diagnostic = (result.stdout + result.stderr).lower()
            tags = [
                name
                for name in (
                    "invalid",
                    "mount",
                    "seccomp",
                    "sysctl",
                    "apparmor",
                    "cgroup",
                    "permission",
                    "logging",
                    "failed to initialize logging driver",
                    "unknown log opt",
                    "max-file",
                    "max-size",
                    "driver",
                    "json",
                    "namespace",
                    "capability",
                    "executable",
                    "not found",
                    "not a directory",
                    "operation not permitted",
                    "address already in use",
                    "cannot join",
                    "read-only",
                    "dependency",
                    "initialize",
                    "default",
                    "volume",
                )
                if name in diagnostic
            ]
            print(json.dumps({"version": "source-worker-docker-error-v1", "fixed_tags": tags}))
            for marker, code in (
                ("seccomp", "seccomp"),
                ("sysctl", "sysctl"),
                ("permission denied", "permissions"),
                ("address already in use", "binding"),
                ("port is already allocated", "binding"),
                ("no such file", "missing_file"),
                ("unhealthy", "unhealthy"),
                ("exited", "service_exit"),
            ):
                if marker in diagnostic:
                    raise RuntimeError("fixture_docker_" + code)
            raise RuntimeError("fixture_docker_command")
        return result.stdout.strip()

    def compose(self, *arguments: str) -> str:
        return self.command(
            "compose",
            "--env-file",
            str(self.env_file),
            "-p",
            self.project,
            "-f",
            str(ROOT / "infra/compose.source-worker-test.yml"),
            *arguments,
        )

    def prepare(self) -> None:
        info = json.loads(
            self.command(
                "info",
                "--format",
                '{"OSType":"{{.OSType}}","Architecture":"{{.Architecture}}","Root":"{{.DockerRootDir}}"}',
            )
        )
        filesystem = os.statvfs(info["Root"])
        check_host(info, filesystem.f_bavail * filesystem.f_frsize)
        for identity in self.command("network", "ls", "-q").splitlines():
            for entry in (
                json.loads(
                    self.command(
                        "network", "inspect", identity, "--format", "{{json .IPAM.Config}}"
                    )
                )
                or []
            ):
                subnet = entry.get("Subnet")
                if subnet and any(
                    ip_network(subnet).overlaps(ip_network(candidate))
                    for candidate in ("172.30.240.0/24", "172.30.241.0/24")
                ):
                    raise RuntimeError("fixture_subnet_conflict")
        worker = self.command("image", "inspect", "nima-egress-worker:local", "--format", "{{.Id}}")
        helper = self.command("image", "inspect", "nima-egress-helper:local", "--format", "{{.Id}}")
        if any(re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None for value in (worker, helper)):
            raise RuntimeError("fixture_image_identity")
        profile = self.state / "seccomp.json"
        profile.write_bytes(build_profile((ROOT / "infra/source-worker/seccomp.json").read_bytes()))
        profile.chmod(0o600)
        resolver = self.state / "resolv.conf"
        resolver.write_bytes(b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n")
        resolver.chmod(0o644)  # Public fixed resolver config, inside a 0700 state directory.
        values = {
            "NIMA_RUN_ID": self.run_id,
            "NIMA_WORKER_IMAGE": worker,
            "NIMA_HELPER_IMAGE": helper,
            "NIMA_SECCOMP_PATH": str(profile),
            "NIMA_RESOLV_PATH": str(resolver),
            "NIMA_FIXTURE_USERNAME": self.auth[0],
            "NIMA_FIXTURE_PASSWORD": self.auth[1],
        }
        self.env_file.write_text("".join(key + "=" + value + "\n" for key, value in values.items()))
        self.env_file.chmod(0o600)
        self.compose("config", "--quiet")

    def start(self) -> None:
        self.compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "60",
            "anchor",
            "origin",
            "bad",
            "canary",
        )
        networks = self.command(
            "network", "ls", "-q", "--filter", "label=com.docker.compose.project=" + self.project
        ).splitlines()
        if len(networks) != 2 or any(
            self.command("network", "inspect", identity, "--format", "{{.Internal}}") != "true"
            for identity in networks
        ):
            raise RuntimeError("fixture_network_identity")
        self.compose("run", "--rm", "--no-deps", "nss")
        self.compose("run", "--rm", "--no-deps", "gateway-validate")
        self.compose("up", "-d", "--wait", "--no-deps", "gateway")
        installed = json.loads(self.compose("run", "--rm", "--no-deps", "network-setup"))
        assert installed["status"] == "passed"
        assert installed["metadata_alias"] is True
        assert installed["ipv6_disabled"] is True
        observed = json.loads(self.compose("run", "--rm", "--no-deps", "network-inspect"))
        assert observed["policy_sha256"] == installed["policy_sha256"]
        assert observed["network_inode"] == installed["network_inode"]

    def cleanup(self) -> None:
        selected: dict[str, list[str]] = {}
        for kind in ("container", "network", "volume"):
            arguments = ("ps", "-aq") if kind == "container" else (kind, "ls", "-q")
            ids = self.command(
                *arguments, "--filter", "label=com.docker.compose.project=" + self.project
            ).splitlines()
            for identity in ids:
                valid = (
                    bool(re.fullmatch(r"[0-9a-f]{12,64}", identity))
                    if kind != "volume"
                    else identity.startswith(self.project + "_")
                )
                if not valid:
                    raise RuntimeError("fixture_resource_identity")
                template = (
                    '{{index .Config.Labels "io.nima.fixture.run_id"}}'
                    if kind == "container"
                    else '{{index .Labels "io.nima.fixture.run_id"}}'
                )
                if self.command(kind, "inspect", identity, "--format", template) != self.run_id:
                    raise RuntimeError("fixture_resource_ownership")
            selected[kind] = ids
        observations = []
        for identity in selected["container"]:
            row = json.loads(
                self.command(
                    "container",
                    "inspect",
                    identity,
                    "--format",
                    '{"role":"{{index .Config.Labels "com.docker.compose.service"}}",'
                    '"exit_code":{{.State.ExitCode}},"running":{{.State.Running}}}',
                )
            )
            if row["role"] not in {
                "initialize",
                "anchor",
                "nss",
                "origin",
                "bad",
                "canary",
                "observer",
                "worker",
                "gateway",
                "gateway-validate",
                "network-setup",
                "network-inspect",
                "metadata",
                "network-probe",
            }:
                raise RuntimeError("fixture_service_identity")
            observations.append(row)
            print(json.dumps({"version": "source-worker-service-observation-v1", "service": row}))
            if row["exit_code"]:
                try:
                    logs = self.command("logs", identity)
                except RuntimeError:
                    row["logs_available"] = False
                    logs = ""
                for line in logs.splitlines()[:32]:
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if type(value) is not dict:
                        continue
                    if value.get("version") == "source-worker-preflight-v1" and value.get(
                        "failure"
                    ) in {
                        "process",
                        "fixture_initialization",
                        "fixture_storage",
                        "fixture_credentials",
                        "fixture_service",
                    }:
                        row["failure"] = value["failure"]
                    if value.get("version") == "source-worker-volume-observation-v1":
                        volumes = value.get("volumes")
                        if type(volumes) is dict and all(
                            key
                            in {
                                "private_uid",
                                "private_gid",
                                "private_mode",
                                "public_uid",
                                "public_gid",
                                "public_mode",
                            }
                            and type(item) is int
                            and 0 <= item <= 2**32 - 1
                            for key, item in volumes.items()
                        ):
                            row["volumes"] = volumes
        print(
            json.dumps(
                {"version": "source-worker-service-observation-v1", "services": observations}
            )
        )
        if selected["container"]:
            self.command("stop", "--time", "3", *selected["container"])
            self.command("rm", "--force", "--volumes", *selected["container"])
        for kind in ("network", "volume"):
            if selected[kind]:
                self.command(kind, "rm", *selected[kind])
        self.env_file.unlink(missing_ok=True)


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
