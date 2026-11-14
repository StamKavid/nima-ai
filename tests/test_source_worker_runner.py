"""Host orchestration failure tests; real Docker remains the enforcement gate."""

import json
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from nima.egress import runner
from nima.egress.fixtures import Counters
from nima.egress.policy import CaseKind
from nima.egress.probe_http import HTTP_CASES, encode_result
from nima.egress.receipt import ClientResult
from nima.egress.rules import COUNTERS
from nima.egress.stage import read_stage


class FixtureDriver:
    fault = ""
    host = Counters()
    instances: list["FixtureDriver"] = []

    def __init__(self, state: Path) -> None:
        self.run_id = str(uuid4())
        self.images = tuple(
            (role, "sha256:" + "a" * 64) for role in ("worker", "helper", "gateway")
        )
        self.network_identity = ("a" * 64, 123)
        self.auth = ("user-sentinel", "password-sentinel")
        self.started = time.monotonic()
        self.cleaned = False
        self.running = True
        self.case = HTTP_CASES[0]
        self.after = False
        self.instances.append(self)

    def remaining(self) -> float:
        return 500

    def prepare(self) -> None:
        if self.fault == "prepare":
            raise ValueError("private-sentinel")

    def start(self) -> None:
        if self.fault == "start":
            raise ValueError("private-sentinel")

    def cleanup(self) -> None:
        if self.fault == "cleanup":
            raise ValueError("private-sentinel")
        self.cleaned = True

    def command(self, *args: str, **kwargs: Any) -> str:
        if args[0] == "start":
            self.running = True
        if args[0] == "stop":
            self.running = False
        return (
            json.dumps({"running": self.running, "run": self.run_id, "role": "gateway"})
            if args[0] == "inspect"
            else ""
        )

    def compose(self, *args: str, **kwargs: Any) -> str:
        if args[0] == "stop":
            self.running = False
            return ""
        if args[0] == "ps":
            return "a" * 64
        if args[-1] == "metadata":
            return ""
        if "worker" in args:
            if self.fault == "interrupt":
                raise KeyboardInterrupt
            self.case = next(case for case in HTTP_CASES if case.name == args[-1])
            self.after = True
            result = {
                CaseKind.ALLOWED: ClientResult.FIXTURE_BODY,
                CaseKind.RESTARTED: ClientResult.FIXTURE_BODY,
                CaseKind.PACKET_BLOCKED: ClientResult.NETWORK_FAILURE,
                CaseKind.GATEWAY_REJECTED: ClientResult.PROXY_REJECTED,
                CaseKind.TLS_REJECTED: ClientResult.CERTIFICATE_REJECTED,
                CaseKind.GATEWAY_OUTAGE: ClientResult.NETWORK_FAILURE,
                CaseKind.IPV6_DISABLED: ClientResult.IPV6_UNAVAILABLE,
            }[self.case.kind]
            return encode_result(self.case.name, result).decode()
        if args[-1] == "network-inspect":
            drop = {
                "http_direct_ipv4": "direct_tcp",
                "http_proxy_removed": "direct_tcp",
                "http_no_proxy": "direct_tcp",
                "http_trust_env_false": "direct_tcp",
                "http_host_bridge": "host_tcp",
                "http_metadata": "metadata_tcp",
                "http_dns": "dns_udp",
                "http_udp": "direct_udp",
            }.get(self.case.name)
            return json.dumps(
                {
                    "version": "source-worker-network-v1",
                    "scope": "fixtures",
                    "status": "passed",
                    "policy_sha256": ("b" if self.fault == "policy" and self.after else "a") * 64,
                    "network_inode": 123,
                    "metadata_alias": True,
                    "ipv6_disabled": True,
                    "counters": {
                        name: {
                            "packets": int(self.after and name == drop and self.fault != "drops"),
                            "bytes": 0,
                        }
                        for name in COUNTERS
                    },
                    "production_ready": False,
                    "internet_egress_verified": False,
                    "investigator_ip_protection_verified": False,
                }
            )
        command = args[-1]
        if command == "packet-control":
            self.host.request(None, clean=True)
        if command in {"packet-control", "packet-reset", "packet-observe"}:
            canary, metadata = Counters(), Counters()
            if command == "packet-control":
                metadata.request(None, clean=True)
                for _ in range(4):
                    canary.request(None, clean=True)
                canary.add("dns_queries")
                for _ in range(3):
                    canary.add("udp_datagrams")
            if self.fault == "delivery" and self.after:
                canary.add("tcp_accepts")
            return json.dumps(
                {
                    "version": "source-worker-packet-observation-v1",
                    "canary": canary.snapshot(),
                    "metadata": metadata.snapshot(),
                }
            )
        origin, bad = Counters(), Counters()
        if command == "gateway-control":
            self.after = False
            origin.request("html", clean=True)
            bad.request("html", clean=True)
        if command == "gateway-reset":
            self.after = False
        if self.after and self.case.kind in {CaseKind.ALLOWED, CaseKind.RESTARTED}:
            origin.request("html", clean=True)
        if self.after and self.case.name.startswith("http_redirect_"):
            origin.request(None, clean=True)
        if command == "origins-observe":
            return json.dumps({"origin": origin.snapshot(), "bad": bad.snapshot()})
        return json.dumps(
            {
                "version": "source-worker-gateway-observation-v1",
                "allowed": 10 + int(self.after),
                "denied": int(self.after and self.case.kind == CaseKind.GATEWAY_REJECTED),
                "origin": origin.snapshot(),
                "bad": bad.snapshot(),
            }
        )


@pytest.fixture
def fixture_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    FixtureDriver.fault = ""
    FixtureDriver.instances = []
    FixtureDriver.host = Counters()
    monkeypatch.setattr(runner, "FixtureStack", FixtureDriver)
    monkeypatch.setattr(runner, "Counters", lambda: FixtureDriver.host)
    monkeypatch.setattr(runner, "http_server", lambda *args, **kwargs: nullcontext())


def test_runner_publishes_all_http_cases_only_after_cleanup(
    tmp_path: Path, fixture_driver: None
) -> None:
    output = tmp_path / "reports"
    report = runner.run_http(output)
    stage = read_stage(report.read_bytes())
    assert len(stage.cases) == 18
    assert FixtureDriver.instances[-1].cleaned and stage.cleanup_verified
    assert stage.images == FixtureDriver.instances[-1].images


@pytest.mark.parametrize(
    "fault", ["prepare", "start", "cleanup", "policy", "delivery", "drops", "interrupt"]
)
def test_failures_or_interruptions_never_publish_success(
    tmp_path: Path, fixture_driver: None, fault: str
) -> None:
    FixtureDriver.fault = fault
    output = tmp_path / "reports"
    with pytest.raises(KeyboardInterrupt if fault == "interrupt" else (ValueError, RuntimeError)):
        runner.run_http(output)
    assert not list(output.glob("*.json"))
    if fault != "cleanup":
        assert FixtureDriver.instances[-1].cleaned


def test_cli_is_fixture_only_and_redacts_failures(
    tmp_path: Path, fixture_driver: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        runner.main(
            [
                "--profile",
                "live-private-sentinel",
                "--stage",
                "http",
                "--output-dir",
                str(tmp_path / "reports"),
            ]
        )
        == 2
    )
    assert FixtureDriver.instances == []
    assert "private-sentinel" not in capsys.readouterr().out

    FixtureDriver.fault = "prepare"
    assert (
        runner.main(
            ["--profile", "fixtures", "--stage", "http", "--output-dir", str(tmp_path / "reports")]
        )
        == 1
    )
    assert "private-sentinel" not in capsys.readouterr().out


@pytest.mark.parametrize("fault", ["", "interrupt"])
def test_cli_reports_only_the_http_stage(
    tmp_path: Path,
    fixture_driver: None,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    FixtureDriver.fault = fault
    result = runner.main(
        ["--profile", "fixtures", "--stage", "http", "--output-dir", str(tmp_path / "reports")]
    )
    value = json.loads(capsys.readouterr().out)
    assert result == (130 if fault else 0)
    assert value["status"] == ("failed" if fault else "passed")
    if not fault:
        assert value["complete_matrix"] is value["production_ready"] is False


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', "[]", "invalid", "x" * 65537])
def test_invalid_observer_documents_fail_closed(raw: str) -> None:
    with pytest.raises(runner.RunnerError):
        runner._object(raw)


@pytest.mark.parametrize("value", [True, -1, 0.5, 1000001])
def test_counter_types_and_limits_cannot_be_coerced(value: object) -> None:
    with pytest.raises(runner.RunnerError):
        runner._count(value)
