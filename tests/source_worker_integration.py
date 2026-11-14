"""Explicit Linux/Docker tests, never skipped or included in ordinary discovery.

The shared host controller creates only UUID-labelled closed fixtures; cleanup
verifies and removes exact IDs. Application execution remains fixture-only.
"""

import json
from pathlib import Path

import pytest

from nima.egress.fixtures import Counters, http_server
from nima.egress.stack import FixtureStack, ProbeCommandError


def test_closed_fixture_services_and_private_controls(tmp_path: Path) -> None:
    stack = FixtureStack(tmp_path)
    stack.prepare()
    try:
        stack.start()
        assert stack.network_identity is not None
        stack.verify_topology()
        observed_runtime = json.loads(
            stack.compose(
                "run",
                "--rm",
                "--no-deps",
                "observer",
                "python",
                "-m",
                "nima.egress.runtime",
                "observer",
            )
        )
        gateway_runtime = json.loads(stack.compose("run", "--rm", "--no-deps", "gateway-inspect"))
        assert observed_runtime["process"]["uid"] == gateway_runtime["process"]["uid"] == 10002
        assert observed_runtime["process"]["network_inode"] == stack.network_identity[1]
        assert gateway_runtime["process"]["network_inode"] != stack.network_identity[1]
        assert gateway_runtime["gateway_forwarding_disabled"] is True
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
            result = json.loads(
                stack.compose(
                    "run",
                    "--rm",
                    "--no-deps",
                    "network-probe",
                    "python",
                    "-m",
                    "nima.egress.probe_network",
                    "evidence",
                )
            )
            assert result["version"] == "source-worker-privileges-v1"
            assert result["process"]["uid"] == 10001
            assert result["process"]["network_inode"] == before["network_inode"]
            assert result["observer_uid_denied"] is result["parent_net_admin_denied"] is True
            assert result["controls_unreachable"] is True
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
    from nima.egress.runner import run_http
    from nima.egress.stage import read_stage

    file = run_http(tmp_path / "http-reports")
    stage = read_stage(file.read_bytes())
    assert len(stage.cases) == 18
    assert stage.cleanup_verified
    assert stage.elapsed_seconds <= 600
    assert all(
        row.control_success is True for row in stage.cases if row.case_name != "ipv6_disabled"
    )
    value = json.loads(file.read_bytes())
    assert len(value["pending_cases"]) == 10
    assert value["complete_matrix"] is value["isolation_checks_passed"] is False
    assert value["investigator_ip_protection_verified"] is value["production_ready"] is False


def test_real_browser_cases_require_sandbox_and_kernel_delivery_evidence(tmp_path: Path) -> None:
    from nima.egress.probe_browser import BROWSER_CASES
    from nima.egress.runner import execute_cases

    stack = FixtureStack(tmp_path)
    try:
        stack.prepare()
        rows = execute_cases(stack, BROWSER_CASES).cases
        assert tuple(row.case_name for row in rows) == tuple(case.name for case in BROWSER_CASES)
        for row in rows:
            assert row.control_success is True
        assert rows[0].observed_routes == frozenset({"html", "script", "image", "xhr", "fetch"})
    finally:
        stack.cleanup()
    assert stack.cleaned


def test_full_matrix_receipt_requires_runtime_observations_and_cleanup(tmp_path: Path) -> None:
    from nima.egress.policy import CASES
    from nima.egress.receipt import read_receipt
    from nima.egress.runner import run_all

    file = run_all(tmp_path / "matrix-reports")
    receipt = read_receipt(file.read_bytes())
    assert tuple(row.case_name for row in receipt.cases) == tuple(case.name for case in CASES)
    assert receipt.runtime.observer_uid_denied is True
    assert receipt.runtime.parent_net_admin_denied is True
    assert receipt.runtime.gateway_forwarding_disabled is True
    assert receipt.runtime.external_networks is False
    value = json.loads(file.read_bytes())
    assert value["isolation_checks_passed"] is True
    assert value["investigator_ip_protection_verified"] is value["production_ready"] is False


def test_real_packet_guard_mutation_is_detected_restored_and_full_matrix_replayed(
    tmp_path: Path,
) -> None:
    """Trusted test helper only; never expose mutation through the application CLI.

    https://manpages.debian.org/bookworm/nftables/nft.8.en.html#RULES
    Insert one narrow rule at the head; delete only its observed kernel handle.
    No host namespace, table flush, persistent policy edit or external target.
    """
    from nima.egress.probe_browser import read_result
    from nima.egress.receipt import ClientResult, read_receipt
    from nima.egress.rules import nft_objects, policy_payload
    from nima.egress.runner import _network, _observe, _packet_control, _zero_delivery, run_all

    state = tmp_path / "mutation-state"
    state.mkdir(mode=0o700)
    stack = FixtureStack(state)

    def nft(*args: str) -> str:
        return stack.compose("run", "--rm", "--no-deps", "network-setup", "/usr/sbin/nft", *args)

    def handles() -> set[int]:
        rows = nft_objects(
            nft("--json", "--numeric", "--handle", "list", "table", "inet", "nima_worker").encode()
        )
        rules = [row["rule"] for row in rows if "rule" in row]
        assert rules and all(
            row["family"] == "inet" and row["table"] == "nima_worker" and row["chain"] == "output"
            for row in rules
        )
        values = [row["handle"] for row in rules]
        assert all(type(value) is int and 0 < value < 2**64 for value in values)
        assert len(set(values)) == len(values)
        return set(values)

    try:
        stack.prepare()
        stack.start()
        stack.compose("up", "-d", "--wait", "--no-deps", "metadata")
        original_bytes = policy_payload()
        _network(stack)  # Require the original full policy before any mutation.
        original_handles = handles()
        host = Counters()
        with http_server(
            ("172.30.240.1", 18080), host, role="host", context=None, credentials=stack.auth
        ):
            _packet_control(stack, host)
            added_handle = None
            try:
                nft(
                    "insert",
                    "rule",
                    "inet",
                    "nima_worker",
                    "output",
                    "meta",
                    "skuid",
                    "10001",
                    "ip",
                    "daddr",
                    "172.30.240.4",
                    "tcp",
                    "dport",
                    "8443",
                    "accept",
                )
                changed = handles()
                assert original_handles < changed and len(changed) == len(original_handles) + 1
                added_handle = (changed - original_handles).pop()
                # The unchanged host validator must reject the actual mutated policy.
                with pytest.raises(ProbeCommandError) as rejected_policy:
                    stack.compose("run", "--rm", "--no-deps", "network-inspect", exact=True)
                policy_outcome = json.loads(rejected_policy.value.result.stdout)
                assert policy_outcome["status"] == "failed"
                assert policy_outcome["failure"] == "network_policy"
                # Run the real negative probe directly to demonstrate its regression:
                # it must FAIL after a forbidden canary response, rather than call it isolation.
                with pytest.raises(ProbeCommandError) as failed_probe:
                    stack.compose(
                        "run",
                        "--rm",
                        "--no-deps",
                        "worker",
                        "python",
                        "-m",
                        "nima.egress.probe_browser",
                        "browser_proxy_bypass",
                        exact=True,
                    )
                outcome = json.loads(failed_probe.value.result.stdout)
                assert outcome["status"] == "failed" and outcome["failure"] == "unexpected_delivery"
                delivered = _observe(stack, "packet-observe")["canary"]
                assert delivered["application_requests"] > 0 and delivered["tcp_accepts"] > 0
                assert delivered["headers_clean"] is True
            finally:
                if added_handle is not None:
                    nft(
                        "delete",
                        "rule",
                        "inet",
                        "nima_worker",
                        "output",
                        "handle",
                        str(added_handle),
                    )
                assert handles() == original_handles
                assert policy_payload() == original_bytes
                _network(stack)  # Exact original policy digest and namespace must be restored.

            _packet_control(stack, host)
            before = _network(stack)
            raw = stack.compose(
                "run",
                "--rm",
                "--no-deps",
                "worker",
                "python",
                "-m",
                "nima.egress.probe_browser",
                "browser_proxy_bypass",
                exact=True,
            )
            assert (
                read_result(raw.encode(), "browser_proxy_bypass").client_result
                == ClientResult.NETWORK_FAILURE
            )
            assert _network(stack)["direct_tcp"] > before["direct_tcp"]
            _zero_delivery(stack, host)
    finally:
        stack.cleanup()
    assert stack.cleaned

    # Use fresh, independently owned fixtures after mutation cleanup. The ordinary
    # strict full runner and publisher must still accept every normal case.
    file = run_all(tmp_path / "restored-matrix")
    receipt = read_receipt(file.read_bytes())
    assert len(receipt.cases) == 28
    value = json.loads(file.read_bytes())
    assert value["isolation_checks_passed"] is True
    assert value["investigator_ip_protection_verified"] is value["production_ready"] is False
