"""Bounded fixture-only HTTP stage; publish evidence only after owned cleanup."""

import argparse
import json
import re
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Never
from uuid import UUID

from nima.egress.fixtures import METRICS, Counters, http_server
from nima.egress.policy import CaseKind
from nima.egress.probe_http import HTTP_CASES, read_result
from nima.egress.receipt import CaseEvidence, validate_case
from nima.egress.rules import COUNTERS
from nima.egress.stack import FixtureStack
from nima.egress.stage import HttpStage, publish_stage

DROPS = {
    "http_direct_ipv4": "direct_tcp",
    "http_proxy_removed": "direct_tcp",
    "http_no_proxy": "direct_tcp",
    "http_trust_env_false": "direct_tcp",
    "http_host_bridge": "host_tcp",
    "http_metadata": "metadata_tcp",
    "http_dns": "dns_udp",
    "http_udp": "direct_udp",
}


class RunnerError(ValueError):
    """Fixed codes, never raw Docker/client output or operator paths."""


def _require(condition: bool) -> None:
    if not condition:
        raise RunnerError("observation")


def _object(raw: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result

    _require(0 < len(raw) <= 65536)
    try:
        value: Any = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, RecursionError):
        raise RunnerError("observation") from None
    _require(type(value) is dict)
    return dict(value)


def _count(value: object, *, limit: int = 1000000) -> int:
    if type(value) is not int or not 0 <= value <= limit:
        raise RunnerError("observation")
    return value


def _delivery(value: Any) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == METRICS | {"headers_clean"})
    _require(value["headers_clean"] is True)
    for metric in METRICS:
        _count(value[metric])
    _require(value["server_errors"] == 0)
    return dict(value)


def _observe(stack: FixtureStack, command: str) -> dict[str, Any]:
    value = _object(
        stack.compose(
            "run", "--rm", "--no-deps", "observer", "python", "-m", "nima.egress.observer", command
        )
    )
    if command.startswith("packet-"):
        _require(
            set(value) == {"version", "canary", "metadata"}
            and value["version"] == "source-worker-packet-observation-v1"
        )
        roles = ("canary", "metadata")
    else:
        roles = ("origin", "bad")
        if command == "origins-observe":
            _require(set(value) == {"origin", "bad"})
        else:
            _require(
                set(value) == {"version", "allowed", "denied", "origin", "bad"}
                and value["version"] == "source-worker-gateway-observation-v1"
            )
            _count(value["allowed"])
            _count(value["denied"])
    for role in roles:
        value[role] = _delivery(value[role])
    return value


def _network(stack: FixtureStack) -> dict[str, int]:
    value = _object(stack.compose("run", "--rm", "--no-deps", "network-inspect"))
    _require(
        value.get("version") == "source-worker-network-v1"
        and value.get("status") == "passed"
        and value.get("scope") == "fixtures"
    )
    _require(
        type(value.get("network_inode")) is int
        and (value.get("policy_sha256"), value["network_inode"]) == stack.network_identity
    )
    _require(value.get("ipv6_disabled") is True and value.get("metadata_alias") is True)
    _require(type(value.get("counters")) is dict and set(value["counters"]) == set(COUNTERS))
    counters = {}
    for name, row in value["counters"].items():
        _require(type(row) is dict and set(row) == {"packets", "bytes"})
        counters[name] = _count(row["packets"], limit=2**64 - 1)
        _count(row["bytes"], limit=2**64 - 1)
    return counters


def _gateway_running(stack: FixtureStack, identity: str) -> bool:
    _require(re.fullmatch(r"[0-9a-f]{64}", identity) is not None)
    value = _object(
        stack.command(
            "inspect",
            identity,
            "--format",
            '{"running":{{.State.Running}},'
            '"run":"{{index .Config.Labels "io.nima.fixture.run_id"}}",'
            '"role":"{{index .Config.Labels "com.docker.compose.service"}}"}',
        )
    )
    _require(
        set(value) == {"running", "run", "role"}
        and type(value["running"]) is bool
        and value["run"] == stack.run_id
        and value["role"] == "gateway"
    )
    return bool(value["running"])


def execute_http(stack: FixtureStack) -> tuple[CaseEvidence, ...]:
    stack.start()
    stack.compose("up", "-d", "--wait", "--no-deps", "metadata")
    host = Counters()
    completed = []
    stopped_id = None
    with http_server(
        ("172.30.240.1", 18080), host, role="host", context=None, credentials=stack.auth
    ):
        for case in HTTP_CASES:
            stack.remaining()
            if case.kind == CaseKind.RESTARTED:
                _require(stopped_id is not None)
                stack.command("start", str(stopped_id))
            gateway_id = stack.compose("ps", "--all", "--quiet", "gateway")
            _require(_gateway_running(stack, gateway_id))
            if case.kind == CaseKind.RESTARTED:
                _require(gateway_id == stopped_id)
            controls = _observe(stack, "gateway-control")
            _require(
                controls["allowed"] >= 2
                and controls["origin"]["application_requests"]
                == controls["bad"]["application_requests"]
                == 1
            )
            controls = _observe(stack, "packet-control")
            _require(
                controls["metadata"]["application_requests"] == 1
                and host.snapshot()["application_requests"] == 1
            )
            _require(
                controls["canary"]["application_requests"] == 4
                and controls["canary"]["dns_queries"] == 1
                and controls["canary"]["udp_datagrams"] == 3
            )
            host.reset()
            _observe(stack, "packet-reset")
            before_gateway = _observe(stack, "gateway-reset")
            before = _network(stack)
            stopped = case.kind == CaseKind.GATEWAY_OUTAGE
            if stopped:
                stack.command("stop", "--time", "3", gateway_id)
                _require(not _gateway_running(stack, gateway_id))
                stopped_id = gateway_id
            raw = stack.compose(
                "run",
                "--rm",
                "--no-deps",
                "worker",
                "python",
                "-m",
                "nima.egress.probe_http",
                case.name,
                exact=True,
            )
            result = read_result(raw.encode(), case.name)
            after = _network(stack)
            packets = _observe(stack, "packet-observe")
            gateway = _observe(stack, "origins-observe" if stopped else "gateway-observe")
            for counts in (packets["canary"], packets["metadata"], _delivery(host.snapshot())):
                _require(
                    all(
                        counts[metric] == 0
                        for metric in (
                            "tcp_accepts",
                            "application_requests",
                            "dns_queries",
                            "udp_datagrams",
                        )
                    )
                )
            positive = case.kind in {CaseKind.ALLOWED, CaseKind.RESTARTED}
            redirect = case.name.startswith("http_redirect_")
            _require(
                gateway["origin"]["application_requests"] == int(positive or redirect)
                and gateway["bad"]["application_requests"] == 0
            )
            deliveries = None
            if case.kind != CaseKind.IPV6_DISABLED:
                target = "bad" if case.kind == CaseKind.TLS_REJECTED else "origin"
                if case.kind == CaseKind.PACKET_BLOCKED:
                    sink = (
                        host.snapshot()
                        if case.name == "http_host_bridge"
                        else packets["metadata" if case.name == "http_metadata" else "canary"]
                    )
                    deliveries = _count(sink[case.target_counter])
                elif redirect:
                    deliveries = _count(packets["canary"][case.target_counter])
                else:
                    deliveries = _count(gateway[target][case.target_counter])
            row = CaseEvidence(
                case.name,
                case.target_counter,
                result,
                control_success=None if case.kind == CaseKind.IPV6_DISABLED else True,
                target_deliveries=deliveries,
                gateway_tunnels=None if stopped else gateway["allowed"] - before_gateway["allowed"],
                gateway_rejections=None
                if stopped
                else gateway["denied"] - before_gateway["denied"],
                policy_drops=after[DROPS[case.name]] - before[DROPS[case.name]]
                if case.name in DROPS
                else None,
                observed_routes=frozenset({"html"})
                if gateway["origin"]["html"] == 1
                else frozenset(),
                headers_clean=gateway["origin"]["headers_clean"],
                gateway_stopped=True if stopped else None,
                gateway_restarted=True if case.kind == CaseKind.RESTARTED else None,
            )
            validate_case(row)
            completed.append(row)
    stack.remaining()
    return tuple(completed)


def run_http(output_dir: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="nima-egress-") as temporary:
        stack = FixtureStack(Path(temporary))
        started_at = datetime.now(UTC)
        try:
            stack.prepare()
            cases = execute_http(stack)
        finally:
            stack.cleanup()
        if not stack.cleaned or stack.network_identity is None:
            raise RunnerError("observation")
        fingerprint, inode = stack.network_identity
    # Include destruction of the private temporary configuration in runtime.
    stage = HttpStage(
        UUID(stack.run_id),
        stack.images,
        fingerprint,
        inode,
        started_at,
        datetime.now(UTC),
        time.monotonic() - stack.started,
        stack.cleaned,
        cases,
    )
    return publish_stage(output_dir, stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise RunnerError("configuration")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser()
        parser.add_argument("--profile", required=True, choices=("fixtures",))
        parser.add_argument("--stage", required=True, choices=("http",))
        parser.add_argument("--output-dir", required=True, type=Path)
        args = parser.parse_args(argv)
    except RunnerError:
        print(json.dumps({"status": "failed", "failure": "configuration"}))
        return 2
    try:
        file = run_http(args.output_dir)
    except KeyboardInterrupt:
        print(json.dumps({"status": "failed", "failure": "interrupted"}))
        return 130
    except Exception:
        print(json.dumps({"status": "failed", "failure": "http_stage"}))
        return 1
    print(
        json.dumps(
            {
                "version": "source-worker-http-stage-summary-v1",
                "status": "passed",
                "run_id": file.stem,
                "http_cases": len(HTTP_CASES),
                "complete_matrix": False,
                "investigator_ip_protection_verified": False,
                "production_ready": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
