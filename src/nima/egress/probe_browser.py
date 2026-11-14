"""Fixed Chromium cases with observed sandbox/runtime and no live destinations.

https://playwright.dev/python/docs/api/class-browser#browser-new-context-option-proxy
https://chromium.googlesource.com/website/+/refs/heads/main/site/quic/playing-with-quic/index.md
https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/setLocalDescription
"""

import json
import os
import re
import signal
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from types import FrameType
from typing import Never

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import ProxySettings, sync_playwright
from playwright.sync_api import TimeoutError as BrowserTimeout

from nima.egress.bootstrap import ProxyCredentials, credentials
from nima.egress.policy import CASES, FixturePolicy
from nima.egress.preflight import CHROMIUM, PLAYWRIGHT, check_sandbox, private_controls, report
from nima.egress.probe_http import ALLOWED, PROXY, require_metadata_alias
from nima.egress.receipt import ClientResult
from nima.egress.runtime import ProcessState, observe_process, validate_process

BROWSER_CASES = tuple(case for case in CASES if case.name.startswith("browser_"))
DIRECT = {"browser_metadata", "browser_dns", "browser_quic", "browser_stun"}
STUN = """async () => {
  const pc = new RTCPeerConnection({iceServers:[{urls:'stun:172.30.240.4:3478'}]});
  window.nimaPeer = pc;
  pc.createDataChannel('nima');
  await pc.setLocalDescription(await pc.createOffer());
  return pc.iceGatheringState;
}"""
FAILURES = frozenset(
    {
        "browser_outcome",
        "browser_body",
        "unexpected_delivery",
        "stun_not_started",
        "browser_version",
        "package_version",
        "resolver",
        "browser_probe",
        "browser_quic_disabled",
    }
)


class BrowserProbeError(ValueError):
    """Fixed codes; raw driver errors and browser diagnostics remain private."""


@dataclass(frozen=True, slots=True)
class BrowserResult:
    client_result: ClientResult
    chromium: str
    process: ProcessState
    sandbox_pid: bool
    sandbox_network: bool
    sandbox_seccomp: bool
    controls_unreachable: bool


def _failure(case: str, error: BrowserError) -> ClientResult:
    if case == "browser_quic":
        if "ERR_QUIC_HANDSHAKE_FAILED" in str(error):
            # Pinned Chromium reports this when the fixture's QUIC packets drop.
            # The host independently requires a positive quic_udp drop delta.
            return ClientResult.NETWORK_FAILURE
        for marker, code in (("ERR_QUIC_GOAWAY_REQUEST_CAN_BE_RETRIED", "browser_quic_disabled"),):
            if marker in str(error):
                raise BrowserProbeError(code)
    if case in {"browser_invalid_auth", "browser_redirect_host"}:
        if any(
            marker in str(error)
            for marker in (
                "ERR_INVALID_AUTH_CREDENTIALS",
                "ERR_TUNNEL_CONNECTION_FAILED",
                "ERR_HTTP_RESPONSE_CODE_FAILURE",
            )
        ):
            return ClientResult.PROXY_REJECTED
    elif case == "browser_invalid_tls":
        if "ERR_CERT_AUTHORITY_INVALID" in str(error):
            return ClientResult.CERTIFICATE_REJECTED
    elif case == "browser_gateway_outage":
        if "ERR_PROXY_CONNECTION_FAILED" in str(error):
            return ClientResult.NETWORK_FAILURE
    elif case != "browser_resources" and (
        isinstance(error, BrowserTimeout)
        or any(
            marker in str(error)
            for marker in (
                "ERR_CONNECTION_TIMED_OUT",
                "ERR_TIMED_OUT",
                "ERR_NAME_NOT_RESOLVED",
                "ERR_DNS_TIMED_OUT",
                "ERR_QUIC_PROTOCOL_ERROR",
            )
        )
    ):
        return ClientResult.NETWORK_FAILURE
    raise BrowserProbeError("browser_outcome") from None


def execute(case: str, auth: ProxyCredentials) -> BrowserResult:
    if case not in {row.name for row in BROWSER_CASES}:
        raise BrowserProbeError("configuration")
    process = observe_process()
    private_controls()
    if version("playwright") != PLAYWRIGHT:
        raise BrowserProbeError("package_version")
    if case == "browser_metadata":
        require_metadata_alias()
    if (
        case == "browser_dns"
        and Path("/etc/resolv.conf").read_bytes()
        != b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n"
    ):
        raise BrowserProbeError("resolver")
    args = ["--disable-background-networking", "--no-first-run"]
    if case in DIRECT:
        args.append("--no-proxy-server")
    if case == "browser_quic":
        args.extend(["--enable-quic", "--origin-to-force-quic-on=172.30.240.4:443"])
    if case == "browser_stun":
        args.append("--force-webrtc-ip-handling-policy=default")
    proxy: ProxySettings = {"server": PROXY, "username": auth.username, "password": auth.password}
    if case == "browser_invalid_auth":
        proxy["password"] = "invalid-fixture-password-" + "0" * 32
    if case == "browser_proxy_bypass":
        proxy["bypass"] = "172.30.240.4"
    with sync_playwright() as api:
        browser = api.chromium.launch(
            channel="chromium",
            headless=True,
            chromium_sandbox=True,
            proxy=None if case in DIRECT else {"server": PROXY},
            args=args,
            timeout=5000,
        )
        try:
            if browser.version != CHROMIUM:
                raise BrowserProbeError("browser_version")
            with browser.new_context(
                proxy=None if case in DIRECT else proxy, ignore_https_errors=False
            ) as context:
                page = context.new_page()
                page.goto("chrome://sandbox", wait_until="domcontentloaded", timeout=3000)
                text = page.locator("body").inner_text(timeout=1000)
                check_sandbox(text)
                flags = [
                    bool(re.search(re.escape(label) + r"\s+Yes\b", text))
                    for label in ("PID namespaces", "Network namespaces", "Seccomp-BPF sandbox")
                ]
                if case == "browser_stun":
                    page.goto("data:text/html,<title>Nima fixture</title>", timeout=1000)
                    if page.evaluate(STUN) not in {"gathering", "complete"}:
                        raise BrowserProbeError("stun_not_started")
                    page.wait_for_timeout(1200)
                    result = ClientResult.ATTEMPTED
                else:
                    url = {
                        "browser_proxy_bypass": "https://172.30.240.4:8443/",
                        "browser_metadata": "http://169.254.169.254/",
                        "browser_dns": "http://unmapped.nima.test:9000/",
                        "browser_quic": "https://172.30.240.4:443/",
                        "browser_redirect_host": ALLOWED + "redirect-host",
                        "browser_invalid_tls": "https://badcert.nima.test:8443/",
                    }.get(case, ALLOWED)
                    try:
                        response = page.goto(url, wait_until="domcontentloaded", timeout=2500)
                    except BrowserError as error:
                        result = _failure(case, error)
                    else:
                        if (
                            case != "browser_resources"
                            or response is None
                            or response.status != 200
                        ):
                            raise BrowserProbeError("unexpected_delivery")
                        page.wait_for_function("() => window.nimaComplete === true", timeout=2000)
                        if (
                            "Nima fixture" not in page.locator("body").inner_text(timeout=1000)
                            or len(page.content().encode()) > FixturePolicy().max_response_bytes
                        ):
                            raise BrowserProbeError("browser_body")
                        result = ClientResult.FIXTURE_BODY
                return BrowserResult(
                    result, browser.version, process, flags[0], flags[1], flags[2], True
                )
        finally:
            browser.close()


def encode_result(case: str, result: BrowserResult) -> bytes:
    if (
        case not in {row.name for row in BROWSER_CASES}
        or not isinstance(result.client_result, ClientResult)
        or result.chromium != CHROMIUM
        or any(
            value is not True
            for value in (
                result.sandbox_pid,
                result.sandbox_network,
                result.sandbox_seccomp,
                result.controls_unreachable,
            )
        )
    ):
        raise BrowserProbeError("result")
    validate_process(result.process, uid=10001)
    raw = (
        json.dumps(
            {
                "version": "source-worker-browser-probe-v1",
                "case_name": case,
                "observation": asdict(result),
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        + b"\n"
    )
    if len(raw) > 4096:
        raise BrowserProbeError("result")
    return raw


def read_result(raw: bytes, case: str) -> BrowserResult:
    if not 0 < len(raw) <= 4096:
        raise BrowserProbeError("result")
    try:
        body = json.loads(raw)
        value = body["observation"]
        result = BrowserResult(
            **{
                **value,
                "client_result": ClientResult(value["client_result"]),
                "process": ProcessState(**value["process"]),
            }
        )
        if body["case_name"] != case or encode_result(case, result) != raw:
            raise BrowserProbeError("result")
        return result
    except (ValueError, TypeError, KeyError, RecursionError):
        raise BrowserProbeError("result") from None


def _expired(signum: int, frame: FrameType | None) -> Never:
    # PID 1 exits on deadline; Docker terminates its driver/browser descendants.
    report("failed", "browser_attempt_deadline")
    sys.stdout.flush()
    os._exit(1)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {row.name for row in BROWSER_CASES}:
        report("failed", "configuration")
        return 2
    previous = signal.signal(signal.SIGALRM, _expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, FixturePolicy().attempt_seconds)
        auth = credentials(
            os.environ.get("NIMA_FIXTURE_USERNAME"), os.environ.get("NIMA_FIXTURE_PASSWORD")
        )
        raw = encode_result(args[0], execute(args[0], auth))
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception as error:
        reason = str(error)
        report(
            "failed",
            reason
            if isinstance(error, BrowserProbeError) and reason in FAILURES
            else "browser_probe",
        )
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    print(raw.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
