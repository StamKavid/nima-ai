"""Bounded fixture-only protocol probes; never a live collection client.

https://www.python-httpx.org/advanced/proxies/
https://playwright.dev/python/docs/api/class-browser#browser-new-context-option-proxy
"""

import os
import ssl
import sys
from pathlib import Path

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import ProxySettings, sync_playwright

from nima.egress.bootstrap import ProxyCredentials, credentials
from nima.egress.preflight import CHROMIUM, check_process, check_sandbox, private_controls, report

PROXY = "http://172.30.240.2:3128"
ALLOWED = "https://allowed.nima.test:8443/"
BAD_TLS = "https://badcert.nima.test:8443/"
DENIED = (
    "https://denied.nima.test:8443/",
    "https://172.30.240.4:8443/",
    "https://allowed.nima.test:8444/",
)


PROTOCOL_FAILURES = frozenset(
    {
        "protocol_response",
        "protocol_proxy",
        "protocol_body",
        "protocol_tls",
        "protocol_browser_version",
        "protocol_browser_auth",
        "protocol_browser_auth_http_response",
        "protocol_browser_auth_connection",
        "protocol_browser_auth_accepted",
        "protocol_browser_auth_returned_407",
        "protocol_browser_tls",
        "protocol_probe",
    }
)


class ProtocolError(ValueError):
    """Fixed diagnostic codes only, never raw client exceptions."""


def _client(auth: ProxyCredentials | None, ca: Path) -> httpx.Client:
    context = ssl.create_default_context(cafile=ca)
    return httpx.Client(
        proxy=httpx.Proxy(PROXY, auth=None if auth is None else (auth.username, auth.password)),
        verify=context,
        trust_env=False,
        timeout=15,
        follow_redirects=False,
    )


def _get(client: httpx.Client, url: str) -> bytes:
    body = bytearray()
    with client.stream("GET", url) as response:
        if response.status_code != 200:
            raise ProtocolError("protocol_response")
        for chunk in response.iter_bytes(chunk_size=4096):
            body.extend(chunk)
            if len(body) > 1024**2:
                raise ProtocolError("protocol_response")
    return bytes(body)


def _proxy_denied(client: httpx.Client, url: str) -> None:
    try:
        _get(client, url)
    except httpx.ProxyError as exc:
        if str(exc).startswith("407 "):
            return
    raise ProtocolError("protocol_proxy")


def probe_http(auth: ProxyCredentials, ca: Path) -> None:
    with _client(auth, ca) as client:
        if b"Nima fixture" not in _get(client, ALLOWED):
            raise ProtocolError("protocol_body")
        for target in DENIED:
            _proxy_denied(client, target)
        try:
            _get(client, BAD_TLS)
        except httpx.ConnectError as exc:
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                raise ProtocolError("protocol_tls") from None
        else:
            raise ProtocolError("protocol_tls")
    for identity in (None, credentials(auth.username, "invalid-fixture-password-" + "0" * 32)):
        with _client(identity, ca) as client:
            _proxy_denied(client, ALLOWED)


def probe_browser(auth: ProxyCredentials) -> None:
    with sync_playwright() as api:
        browser = api.chromium.launch(
            channel="chromium",
            headless=True,
            chromium_sandbox=True,
            proxy={"server": PROXY},
            timeout=15000,
            args=["--disable-background-networking", "--no-first-run"],
        )
        try:
            if browser.version != CHROMIUM:
                raise ProtocolError("protocol_browser_version")
            proxy: ProxySettings = {
                "server": PROXY,
                "username": auth.username,
                "password": auth.password,
            }
            with browser.new_context(proxy=proxy) as context:
                page = context.new_page()
                page.goto("chrome://sandbox", wait_until="domcontentloaded", timeout=15000)
                check_sandbox(page.locator("body").inner_text())
                response = page.goto(ALLOWED, wait_until="domcontentloaded", timeout=15000)
                if response is None or response.status != 200:
                    raise ProtocolError("protocol_response")
                page.wait_for_function("() => window.nimaComplete === true", timeout=15000)
                if "Nima fixture" not in page.locator("body").inner_text():
                    raise ProtocolError("protocol_body")
            for target, password, reason in (
                (ALLOWED, "invalid-fixture-password-" + "0" * 32, "auth"),
                (BAD_TLS, auth.password, "tls"),
            ):
                rejected_proxy: ProxySettings = {
                    "server": PROXY,
                    "username": auth.username,
                    "password": password,
                }
                with browser.new_context(proxy=rejected_proxy) as context:
                    try:
                        rejected_response = context.new_page().goto(
                            target, wait_until="domcontentloaded", timeout=15000
                        )
                    except PlaywrightError as exc:
                        expected = (
                            ("ERR_INVALID_AUTH_CREDENTIALS", "ERR_TUNNEL_CONNECTION_FAILED")
                            if reason == "auth"
                            else ("ERR_CERT_AUTHORITY_INVALID",)
                        )
                        if not any(marker in str(exc) for marker in expected):
                            if reason == "auth" and "ERR_HTTP_RESPONSE_CODE_FAILURE" in str(exc):
                                raise ProtocolError("protocol_browser_auth_http_response") from None
                            if reason == "auth" and "ERR_PROXY_CONNECTION_FAILED" in str(exc):
                                raise ProtocolError("protocol_browser_auth_connection") from None
                            raise ProtocolError("protocol_browser_" + reason) from None
                    else:
                        if reason == "auth":
                            code = (
                                "returned_407"
                                if rejected_response is not None and rejected_response.status == 407
                                else "accepted"
                            )
                            raise ProtocolError("protocol_browser_auth_" + code)
                        raise ProtocolError("protocol_browser_" + reason)
        finally:
            browser.close()


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments not in (["http"], ["browser"]):
        report("failed", "configuration")
        return 2
    try:
        check_process(Path("/proc/self/status").read_text())
        private_controls()
        auth = credentials(
            os.environ.get("NIMA_FIXTURE_USERNAME"), os.environ.get("NIMA_FIXTURE_PASSWORD")
        )
        if arguments == ["http"]:
            probe_http(auth, Path("/fixture-public/ca.pem"))
        else:
            probe_browser(auth)
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception as exc:
        report("failed", str(exc) if str(exc) in PROTOCOL_FAILURES else "protocol_probe")
        return 1
    report("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
