"""Fixed HTTP-stage probes; client outcomes require independent host reconciliation.

https://www.python-httpx.org/advanced/proxies/
https://www.python-httpx.org/environment_variables/
https://www.python-httpx.org/advanced/timeouts/
"""

import json
import os
import signal
import socket
import ssl
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Never

import httpx

from nima.egress.bootstrap import ProxyCredentials, credentials
from nima.egress.policy import CASES, FixturePolicy
from nima.egress.preflight import check_process, private_controls, report
from nima.egress.receipt import ClientResult

HTTP_CASES = tuple(
    row
    for row in CASES
    if row.name.startswith("http_") or row.name in {"ipv6_disabled", "gateway_restart"}
)
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)
PROXY = "http://172.30.240.2:3128"
ALLOWED = "https://allowed.nima.test:8443/"
DIRECT = "https://172.30.240.4:8443/"


class HttpProbeError(ValueError):
    """Fixed codes; raw HTTP errors, credentials and response bodies stay private."""


@contextmanager
def _environment(case: str, auth: ProxyCredentials) -> Iterator[None]:
    old = {name: os.environ.get(name) for name in PROXY_VARIABLES}
    try:
        for name in PROXY_VARIABLES:
            os.environ.pop(name, None)
        if case in {"http_no_proxy", "http_trust_env_false"}:
            proxy = "http://" + auth.username + ":" + auth.password + "@172.30.240.2:3128"
            for name in PROXY_VARIABLES[:6]:
                os.environ[name] = proxy
            for name in ("NO_PROXY", "no_proxy"):
                os.environ[name] = "172.30.240.4" if case == "http_no_proxy" else ""
        yield
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def require_metadata_alias() -> None:
    if Path("/proc/sys/net/ipv4/ip_nonlocal_bind").read_text().strip() != "0":
        raise HttpProbeError("metadata_alias")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as local:
        try:
            local.bind(("169.254.169.254", 0))
        except OSError:
            raise HttpProbeError("metadata_alias") from None


def _body(client: httpx.Client, url: str) -> bytes:
    body = bytearray()
    with client.stream("GET", url) as response:
        if response.status_code != 200:
            raise HttpProbeError("response")
        for chunk in response.iter_bytes(chunk_size=4096):
            body.extend(chunk)
            if len(body) > FixturePolicy().max_response_bytes:
                raise HttpProbeError("response")
    return bytes(body)


def execute(case: str, auth: ProxyCredentials, ca: Path) -> ClientResult:
    if case not in {row.name for row in HTTP_CASES}:
        raise HttpProbeError("configuration")
    if case == "ipv6_disabled":
        if any(
            Path("/proc/sys/net/ipv6/conf/" + name + "/disable_ipv6").read_text().strip() != "1"
            for name in ("all", "default", "lo", "eth0")
        ):
            raise HttpProbeError("ipv6_mode")
        return ClientResult.IPV6_UNAVAILABLE
    if case == "http_dns":
        if (
            Path("/etc/resolv.conf").read_bytes()
            != b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n"
        ):
            raise HttpProbeError("resolver")
        try:
            socket.getaddrinfo("unmapped.nima.test", 8443, socket.AF_INET)
        except socket.gaierror:
            return ClientResult.NETWORK_FAILURE
        raise HttpProbeError("unexpected_delivery")
    if case == "http_udp":
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as channel:
            channel.settimeout(2)
            try:
                channel.sendto(b"nima-control", ("172.30.240.4", 9001))
                channel.recvfrom(1232)
            except (TimeoutError, PermissionError):
                return ClientResult.ATTEMPTED
        raise HttpProbeError("unexpected_delivery")
    direct = case in {
        "http_direct_ipv4",
        "http_proxy_removed",
        "http_no_proxy",
        "http_trust_env_false",
        "http_host_bridge",
        "http_metadata",
    }
    target = DIRECT if direct else ALLOWED
    if case == "http_host_bridge":
        target = "http://172.30.240.1:18080/"
    elif case == "http_metadata":
        require_metadata_alias()
        target = "http://169.254.169.254/"
    elif case == "http_invalid_tls":
        target = "https://badcert.nima.test:8443/"
    elif case.startswith("http_redirect_"):
        target = (
            ALLOWED
            + {
                "http_redirect_host": "redirect-host",
                "http_redirect_ip": "redirect-ip",
                "http_redirect_port": "redirect-port",
            }[case]
        )
    proxy_auth = (
        None
        if case == "http_missing_auth"
        else (
            auth.username,
            "invalid-fixture-password-" + "0" * 32
            if case == "http_invalid_auth"
            else auth.password,
        )
    )
    context = ssl.create_default_context(cafile=ca)
    try:
        with (
            _environment(case, auth),
            httpx.Client(
                proxy=None if direct else httpx.Proxy(PROXY, auth=proxy_auth),
                trust_env=case in {"http_proxy_removed", "http_no_proxy"},
                verify=context,
                timeout=httpx.Timeout(2),
                max_redirects=1,
                follow_redirects=case.startswith("http_redirect_"),
            ) as client,
        ):
            body = _body(client, target)
            if b"Nima fixture" not in body and body != b"Nima synthetic canary\n":
                raise HttpProbeError("response")
            return ClientResult.FIXTURE_BODY
    except httpx.ProxyError as exc:
        if str(exc).startswith("407 "):
            return ClientResult.PROXY_REJECTED
        raise HttpProbeError("proxy_response") from None
    except httpx.ConnectError as exc:
        return (
            ClientResult.CERTIFICATE_REJECTED
            if "CERTIFICATE_VERIFY_FAILED" in str(exc)
            else ClientResult.NETWORK_FAILURE
        )
    except (httpx.ConnectTimeout, httpx.ReadTimeout):
        return ClientResult.NETWORK_FAILURE
    except httpx.HTTPError:
        raise HttpProbeError("http_error") from None


def encode_result(case: str, result: ClientResult) -> bytes:
    if case not in {row.name for row in HTTP_CASES} or not isinstance(result, ClientResult):
        raise HttpProbeError("result")
    return (
        json.dumps(
            {
                "version": "source-worker-http-probe-v1",
                "case_name": case,
                "client_result": result.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )


def read_result(raw: bytes, case: str) -> ClientResult:
    if len(raw) > 4096:
        raise HttpProbeError("result")
    try:
        value = json.loads(raw)
        result = ClientResult(value["client_result"])
        if value["case_name"] != case or encode_result(case, result) != raw:
            raise HttpProbeError("result")
        return result
    except (ValueError, KeyError, TypeError, RecursionError):
        raise HttpProbeError("result") from None


def _expired(signum: int, frame: FrameType | None) -> Never:
    raise HttpProbeError("attempt_deadline")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {row.name for row in HTTP_CASES}:
        report("failed", "configuration")
        return 2
    previous = signal.signal(signal.SIGALRM, _expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, FixturePolicy().attempt_seconds)
        check_process(Path("/proc/self/status").read_text())
        private_controls()
        auth = credentials(
            os.environ.get("NIMA_FIXTURE_USERNAME"), os.environ.get("NIMA_FIXTURE_PASSWORD")
        )
        raw = encode_result(args[0], execute(args[0], auth, Path("/fixture-public/ca.pem")))
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception:
        report("failed", "http_probe")
        return 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    print(raw.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
