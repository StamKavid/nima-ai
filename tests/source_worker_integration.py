"""Explicit Linux/Docker tests, never skipped or included in ordinary discovery.

The shared host controller creates only UUID-labelled closed fixtures; cleanup
verifies and removes exact IDs. Application execution remains fixture-only.
"""

import json
import multiprocessing
import os
import re
import signal
import tempfile
import time
from contextlib import ExitStack, redirect_stderr, redirect_stdout, suppress
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


def test_real_browser_deadline_removes_live_driver_and_controller_refuses_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.egress import runner
    from nima.egress.preflight import CHROMIUM

    # Trusted fixture fault injection: replace one worker attempt, preserving the
    # real CLI alarm, real sandboxed Chromium, Docker and controller cleanup path.
    stalled_browser = """
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from nima.egress import probe_browser
from nima.egress.preflight import check_sandbox, private_controls
from nima.egress.runtime import observe_process

def stalled(case, auth):
    observe_process()
    private_controls()
    with sync_playwright() as api:
        browser = api.chromium.launch(
            channel='chromium', headless=True, chromium_sandbox=True,
            args=['--disable-background-networking', '--no-first-run'], timeout=5000)
        page = browser.new_page()
        page.goto('chrome://sandbox', wait_until='domcontentloaded', timeout=3000)
        check_sandbox(page.locator('body').inner_text(timeout=1000))
        children = Path(f'/proc/self/task/{os.getpid()}/children').read_text().split()
        pids = [int(value) for value in children]
        states = [next(line.split()[1] for line in
            Path(f'/proc/{pid}/status').read_text().splitlines()
            if line.startswith('State:')) for pid in pids]
        print(json.dumps({'version':'source-worker-live-driver-v1',
            'chromium':browser.version,'pids':pids,'states':states}), flush=True)
        time.sleep(120)
        raise RuntimeError('worker_deadline_not_enforced')

probe_browser.execute = stalled
raise SystemExit(probe_browser.main(['browser_resources']))
"""
    compile(stalled_browser, "<fixture-browser-deadline>", "exec")
    instances: list[FixtureStack] = []
    deadline_seen = False

    class DeadlineStack(FixtureStack):
        def compose(self, *arguments: str, exact: bool = False) -> str:
            nonlocal deadline_seen
            if self not in instances:
                instances.append(self)
            if "worker" in arguments and arguments[-1] == "browser_resources":
                try:
                    return super().compose(
                        "run",
                        "--rm",
                        "--no-deps",
                        "worker",
                        "python",
                        "-c",
                        stalled_browser,
                        exact=True,
                    )
                except ProbeCommandError as error:
                    # Never put a sentinel or secret-bearing captured stream in
                    # an assert expression that pytest might expand on failure.
                    if any(
                        secret in error.result.stdout + error.result.stderr for secret in self.auth
                    ):
                        raise AssertionError("fixture_secret_in_diagnostics") from None
                    events = [json.loads(line) for line in error.result.stdout.splitlines()]
                    assert error.result.returncode == 1 and len(events) == 2
                    live, expired = events
                    assert live["version"] == "source-worker-live-driver-v1"
                    assert live["chromium"] == CHROMIUM
                    assert live["pids"] and all(
                        type(pid) is int and pid > 1 for pid in live["pids"]
                    )
                    assert len(live["pids"]) == len(live["states"])
                    assert all(state in {"R", "S", "D", "I"} for state in live["states"])
                    assert expired["status"] == "failed"
                    assert expired["failure"] == "browser_attempt_deadline"
                    # Check actual removal BEFORE the controller's finally cleanup.
                    removal_deadline = time.monotonic() + 5
                    while self.command(
                        "ps",
                        "-aq",
                        "--filter",
                        "label=com.docker.compose.project=" + self.project,
                        "--filter",
                        "label=com.docker.compose.service=worker",
                        timeout=2,
                    ):
                        if time.monotonic() >= removal_deadline:
                            raise AssertionError("expired_worker_not_removed") from None
                        time.sleep(0.05)
                    deadline_seen = True
                    raise
            return super().compose(*arguments, exact=exact)

    monkeypatch.setattr(runner, "FixtureStack", DeadlineStack)
    output = tmp_path / "deadline-reports"
    assert (
        runner.main(["--profile", "fixtures", "--stage", "all", "--output-dir", str(output)]) == 1
    )
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "failure": "matrix_stage"}
    assert deadline_seen and len(instances) == 1 and instances[0].cleaned
    assert not list(output.glob("*.json"))


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


def test_missing_network_admin_is_observed_and_controller_cleans_without_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.egress import runner

    # Test-only setup replacement: preserve the selected image, network namespace,
    # read-only root and seccomp, but deliberately omit the NET_ADMIN capability.
    missing_capability = """
import json
import os
from pathlib import Path
from nima.egress.network import main
lines = Path('/proc/self/status').read_text().splitlines()
fields = dict(line.split(':',1) for line in lines if ':' in line)
print(json.dumps({'version':'source-worker-missing-capability-v1',
    'uid':int(fields['Uid'].split()[0]),
    'caps':[int(fields[name],16) for name in ('CapEff','CapPrm','CapBnd')],
    'no_new_privs':int(fields['NoNewPrivs']), 'seccomp':int(fields['Seccomp']),
    'root_readonly':bool(os.statvfs('/').f_flag & os.ST_RDONLY)}), flush=True)
raise SystemExit(main(['install']))
"""
    compile(missing_capability, "<fixture-missing-capability>", "exec")
    instances: list[FixtureStack] = []
    rejected = False

    class MissingCapabilityStack(FixtureStack):
        def compose(self, *arguments: str, exact: bool = False) -> str:
            nonlocal rejected
            if self not in instances:
                instances.append(self)
            if arguments[-1] == "network-setup":
                anchor = super().compose("ps", "--quiet", "anchor")
                assert re.fullmatch(r"[0-9a-f]{64}", anchor)
                try:
                    return self.command(
                        "run",
                        "--rm",
                        "--read-only",
                        "--user",
                        "0:0",
                        "--cap-drop",
                        "ALL",
                        "--security-opt",
                        "no-new-privileges",
                        "--security-opt",
                        "seccomp=" + str(self.state / "seccomp.json"),
                        "--network",
                        "container:" + anchor,
                        "--pids-limit",
                        "64",
                        "--memory",
                        "128m",
                        "--cpus",
                        "1",
                        "--label",
                        "io.nima.fixture.run_id=" + self.run_id,
                        "--label",
                        "com.docker.compose.project=" + self.project,
                        "--label",
                        "com.docker.compose.service=network-setup",
                        dict(self.images)["helper"],
                        "python",
                        "-c",
                        missing_capability,
                        exact=True,
                    )
                except ProbeCommandError as error:
                    if any(
                        secret in error.result.stdout + error.result.stderr for secret in self.auth
                    ):
                        raise AssertionError("fixture_secret_in_diagnostics") from None
                    rows = [json.loads(line) for line in error.result.stdout.splitlines()]
                    assert error.result.returncode == 1 and len(rows) == 2
                    observed, failure = rows
                    assert observed == {
                        "version": "source-worker-missing-capability-v1",
                        "uid": 0,
                        "caps": [0, 0, 0],
                        "no_new_privs": 1,
                        "seccomp": 2,
                        "root_readonly": True,
                    }
                    assert failure["status"] == "failed" and failure["failure"] == "network_helper"
                    rejected = True
                    raise
            return super().compose(*arguments, exact=exact)

    monkeypatch.setattr(runner, "FixtureStack", MissingCapabilityStack)
    output = tmp_path / "missing-capability-reports"
    assert (
        runner.main(["--profile", "fixtures", "--stage", "all", "--output-dir", str(output)]) == 1
    )
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "failure": "matrix_stage"}
    assert rejected and len(instances) == 1 and instances[0].cleaned
    assert not list(output.glob("*.json"))


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM, signal.SIGKILL])
def test_real_controller_signals_refuse_success_and_preserve_unrelated_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signum: signal.Signals
) -> None:
    """Signal a pinned child after real positive controls, between Docker commands.

    SIGINT exercises the controller's own finally cleanup; hard termination needs
    the independently owning test supervisor. This is not deployed recovery logic.
    https://docs.python.org/3.12/library/signal.html#signal.pidfd_send_signal
    """
    from nima.egress import runner

    context = multiprocessing.get_context("fork")
    ready = context.Event()

    class PausedStack(FixtureStack):
        def compose(self, *arguments: str, exact: bool = False) -> str:
            if "worker" in arguments:
                # The normal runner has verified gateway/packet controls and the
                # original policy here. No host Docker subprocess is in flight.
                ready.set()
                while True:
                    signal.pause()
            return super().compose(*arguments, exact=exact)

    state, foreign_state = tmp_path / "controller-state", tmp_path / "foreign-state"
    state.mkdir(mode=0o700)
    foreign_state.mkdir(mode=0o700)
    controller, foreign = PausedStack(state), FixtureStack(foreign_state)
    # Ownership is generated by this supervisor before forking, not recovered
    # from untrusted stdout. Mark potential creation before the child can start.
    controller.created = True
    output, trace = tmp_path / "signal-reports", state / "controller.log"
    temporary_root = state / "runtime-temporary"
    temporary_root.mkdir(mode=0o700)

    def run_controller() -> None:
        try:
            signal.signal(signal.SIGINT, signal.default_int_handler)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
            signal.alarm(180)  # Harness fails boundedly if synchronization breaks.
            monkeypatch.setattr(tempfile, "tempdir", str(temporary_root))
            descriptor = os.open(trace, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with (
                os.fdopen(descriptor, "w") as stream,
                redirect_stdout(stream),
                redirect_stderr(stream),
            ):
                monkeypatch.setattr(runner, "FixtureStack", lambda path: controller)
                result = runner.main(
                    ["--profile", "fixtures", "--stage", "all", "--output-dir", str(output)]
                )
            os._exit(result)
        except BaseException:
            os._exit(70)  # Fixed harness failure, never a child traceback or secret.

    process = context.Process(target=run_controller)
    controller_pidfd: int | None = None

    def stop_controller() -> None:
        try:
            if process.pid is not None:
                if process.is_alive():
                    if controller_pidfd is None:
                        # Fallback for pidfd_open failure: this immediate parent
                        # has not reaped the child, so the child's PID is pinned.
                        process.kill()
                    else:
                        with suppress(ProcessLookupError):
                            signal.pidfd_send_signal(controller_pidfd, signal.SIGKILL)
                process.join(15)
                assert not process.is_alive()
        finally:
            if controller_pidfd is not None:
                os.close(controller_pidfd)
            if process.pid is not None and not process.is_alive():
                process.close()

    with ExitStack() as cleanup:
        cleanup.callback(foreign.cleanup)
        cleanup.callback(controller.cleanup)
        cleanup.callback(stop_controller)
        process.start()
        assert process.pid is not None
        controller_pidfd = os.pidfd_open(process.pid)
        readiness_deadline = time.monotonic() + 90
        while not ready.wait(0.1):
            if not process.is_alive() or time.monotonic() >= readiness_deadline:
                raise AssertionError("controller_did_not_reach_signal_boundary")
        assert controller.command(
            "ps", "-q", "--filter", "label=com.docker.compose.project=" + controller.project
        )

        image = foreign.command(
            "image", "inspect", "nima-egress-helper:local", "--format", "{{.Id}}"
        )
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", image)
        foreign.created = True
        sentinel = foreign.command(
            "run",
            "-d",
            "--network",
            "none",
            "--read-only",
            "--user",
            "10002:10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "16",
            "--memory",
            "64m",
            "--cpus",
            "0.25",
            "--label",
            "io.nima.fixture.run_id=" + foreign.run_id,
            "--label",
            "com.docker.compose.project=" + foreign.project,
            "--label",
            "com.docker.compose.service=anchor",
            image,
            "python",
            "-c",
            "import signal; signal.pause()",
        )
        assert re.fullmatch(r"[0-9a-f]{64}", sentinel)
        signal.pidfd_send_signal(controller_pidfd, signum)
        process.join(15)
        assert not process.is_alive()
        assert process.exitcode == (130 if signum == signal.SIGINT else -int(signum))
        assert not list(output.glob("*.json"))

        remaining = controller.command(
            "ps", "-aq", "--filter", "label=com.docker.compose.project=" + controller.project
        )
        assert bool(remaining) is (signum != signal.SIGINT)
        raw = trace.read_bytes()
        if len(raw) > 4096 or any(secret.encode() in raw for secret in controller.auth):
            raise AssertionError("controller_diagnostics_not_private_and_bounded")
        if signum == signal.SIGINT:
            assert json.loads(raw) == {"status": "failed", "failure": "interrupted"}
        else:
            assert raw == b""

        controller.cleanup()
        assert controller.cleaned
        assert foreign.command("inspect", sentinel, "--format", "{{.State.Running}}") == "true"
    assert controller.cleaned and foreign.cleaned
    # Hard-killed Python cannot close its empty TemporaryDirectory context.
    # Reclaim only the known test root's expected empty child; rmdir refuses data.
    pending = list(temporary_root.iterdir())
    assert len(pending) <= 1
    for entry in pending:
        assert entry.name.startswith("nima-egress-") and not entry.is_symlink()
        entry.rmdir()
    temporary_root.rmdir()
