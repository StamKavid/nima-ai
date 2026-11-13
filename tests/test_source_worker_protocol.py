"""Client boundaries and redaction; real proxy/browser delivery is checked in Docker."""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from nima.egress import protocol
from nima.egress.bootstrap import credentials
from nima.egress.preflight import CHROMIUM


@pytest.mark.parametrize(
    "fault", ["none", "tls_missing", "tls_wrong", "bad_body", "proxy_403", "proxy_allowed"]
)
def test_http_probe_requires_real_auth_denial_and_certificate_failure(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    identities = []

    def client(identity: object, ca: Path) -> httpx.Client:
        identities.append(identity)

        def respond(request: httpx.Request) -> httpx.Response:
            if str(request.url) == protocol.BAD_TLS:
                if fault == "tls_missing":
                    return httpx.Response(200, content=b"Nima fixture")
                raise httpx.ConnectError(
                    "other failure" if fault == "tls_wrong" else "CERTIFICATE_VERIFY_FAILED"
                )
            if identity != auth or str(request.url) in protocol.DENIED:
                if fault == "proxy_allowed":
                    return httpx.Response(200)
                raise httpx.ProxyError(
                    "403 Forbidden" if fault == "proxy_403" else "407 Proxy Authentication Required"
                )
            return httpx.Response(200, content=b"wrong" if fault == "bad_body" else b"Nima fixture")

        return httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)

    monkeypatch.setattr(protocol, "_client", client)
    if fault == "none":
        protocol.probe_http(auth, Path("unused"))
        assert identities[0] == auth
        assert identities[1] is None
        assert identities[2] != auth
    else:
        with pytest.raises(protocol.ProtocolError, match="^protocol_(tls|body|proxy)$"):
            protocol.probe_http(auth, Path("unused"))


@pytest.mark.parametrize("status,body", [(503, b""), (200, b"x" * (1024**2 + 1))])
def test_response_bounds_fail_closed(status: int, body: bytes) -> None:
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body))
        ) as client,
        pytest.raises(protocol.ProtocolError, match="^protocol_response$"),
    ):
        protocol._get(client, protocol.ALLOWED)


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "bad_version",
        "bad_sandbox",
        "bad_body",
        "auth_wrong_error",
        "tls_allowed",
        "bad_status",
    ],
)
def test_browser_preserves_sandbox_trust_and_validates_failure_reasons(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace
    from unittest.mock import MagicMock, Mock

    from playwright.sync_api import Error as PlaywrightError

    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    browser, page, context = Mock(), Mock(), MagicMock()
    context.__enter__.return_value = context
    browser.version = "wrong" if fault == "bad_version" else CHROMIUM
    browser.new_context.return_value = context
    context.new_page.return_value = page
    page.goto.side_effect = [
        None,
        SimpleNamespace(status=503 if fault == "bad_status" else 200),
        PlaywrightError(
            "net::ERR_CONNECTION_REFUSED"
            if fault == "auth_wrong_error"
            else "net::ERR_INVALID_AUTH_CREDENTIALS"
        ),
        None if fault == "tls_allowed" else PlaywrightError("net::ERR_CERT_AUTHORITY_INVALID"),
    ]
    sandbox = "PID namespaces Yes Network namespaces Yes Seccomp-BPF sandbox Yes"
    page.locator.return_value.inner_text.side_effect = [
        "" if fault == "bad_sandbox" else sandbox,
        "other" if fault == "bad_body" else "Nima fixture",
    ]
    launch = Mock(return_value=browser)

    @contextmanager
    def factory() -> Iterator[SimpleNamespace]:
        yield SimpleNamespace(chromium=SimpleNamespace(launch=launch))

    monkeypatch.setattr(protocol, "sync_playwright", factory)
    if fault == "none":
        protocol.probe_browser(auth)
        options = launch.call_args.kwargs
        assert options["chromium_sandbox"] is True
        assert options["channel"] == "chromium"
        assert "--no-sandbox" not in options["args"]
        assert options["proxy"] == {"server": protocol.PROXY}
        assert all(
            "ignore_https_errors" not in call.kwargs for call in browser.new_context.call_args_list
        )
        assert browser.new_context.call_args_list[0].kwargs["proxy"]["password"] == auth.password
        page.wait_for_function.assert_called_once_with(
            "() => window.nimaComplete === true", timeout=15000
        )
    else:
        with pytest.raises(ValueError):
            protocol.probe_browser(auth)
    browser.close.assert_called_once()


def test_http_client_requires_fixture_ca_and_explicit_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ssl
    from unittest.mock import Mock

    from nima.egress.bootstrap import generate_certificates

    ca = tmp_path / "ca.pem"
    ca.write_bytes(generate_certificates().ca.certificate)
    constructor = Mock()
    monkeypatch.setattr(httpx, "Client", constructor)
    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    protocol._client(auth, ca)
    options = constructor.call_args.kwargs
    assert isinstance(options["verify"], ssl.SSLContext)
    assert options["verify"].verify_mode == ssl.CERT_REQUIRED
    assert options["verify"].check_hostname is True
    assert str(options["proxy"].url) == protocol.PROXY
    assert options["trust_env"] is False
    assert options["follow_redirects"] is False
    assert options["timeout"] == 15


@pytest.mark.parametrize("mode", ["http", "browser"])
@pytest.mark.parametrize(
    "failure",
    [
        None,
        protocol.ProtocolError("protocol_tls"),
        protocol.ProtocolError("sensitive-secret"),
        OSError("sensitive-secret"),
        KeyboardInterrupt(),
    ],
)
def test_protocol_cli_redacts_failures_and_never_attests_production(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    failure: BaseException | None,
) -> None:
    import json
    from unittest.mock import Mock

    process, controls = Mock(), Mock()
    monkeypatch.setattr(protocol, "check_process", process)
    monkeypatch.setattr(protocol, "private_controls", controls)
    monkeypatch.setenv("NIMA_FIXTURE_USERNAME", "fixture-user-" + "u" * 16)
    monkeypatch.setenv("NIMA_FIXTURE_PASSWORD", "p" * 43)
    probe = Mock(side_effect=failure)
    monkeypatch.setattr(protocol, "probe_" + mode, probe)
    result = protocol.main([mode])
    assert result == (
        0 if failure is None else 130 if isinstance(failure, KeyboardInterrupt) else 1
    )
    output = capsys.readouterr().out
    assert "sensitive-secret" not in output
    assert "p" * 43 not in output
    body = json.loads(output)
    assert body["investigator_ip_protection_verified"] is False
    assert body["production_ready"] is False
    process.assert_called_once()
    controls.assert_called_once()
    probe.assert_called_once()
    assert protocol.main(["--sensitive-secret"]) == 2
    assert "sensitive-secret" not in capsys.readouterr().out
