"""HTTP client classifications/configuration; independent Docker counters prove delivery."""

import json
import os
import signal
import socket
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from nima.egress import probe_http
from nima.egress.bootstrap import ProxyCredentials, credentials, generate_certificates
from nima.egress.receipt import ClientResult


@pytest.fixture
def auth() -> ProxyCredentials:
    return credentials("fixture-user-" + "u" * 16, "p" * 43)


@pytest.fixture
def ca(tmp_path: Path) -> Path:
    file = tmp_path / "ca.pem"
    file.write_bytes(generate_certificates().ca.certificate)
    return file


def test_http_stage_is_exact_and_cannot_select_live_targets() -> None:
    assert len(probe_http.HTTP_CASES) == 18
    assert {row.name for row in probe_http.HTTP_CASES if not row.name.startswith("http_")} == {
        "ipv6_disabled",
        "gateway_restart",
    }
    with pytest.raises(probe_http.HttpProbeError):
        probe_http.execute(
            "https://private-secret.test/",
            credentials("fixture-user-" + "u" * 16, "p" * 43),
            Path("unused"),
        )


@pytest.mark.parametrize(
    "case",
    [
        "http_allowed",
        "gateway_restart",
        "http_direct_ipv4",
        "http_proxy_removed",
        "http_no_proxy",
        "http_trust_env_false",
        "http_host_bridge",
        "http_metadata",
        "http_missing_auth",
        "http_invalid_auth",
        "http_invalid_tls",
        "http_gateway_outage",
        "http_redirect_host",
        "http_redirect_ip",
        "http_redirect_port",
    ],
)
def test_http_cases_keep_tls_verification_and_return_only_typed_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    auth: ProxyCredentials,
    ca: Path,
    case: str,
) -> None:
    import ssl

    original = httpx.Client
    options: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        if case in {"http_allowed", "gateway_restart"}:
            return httpx.Response(200, content=b"Nima fixture")
        if case in {
            "http_missing_auth",
            "http_invalid_auth",
            "http_redirect_host",
            "http_redirect_ip",
            "http_redirect_port",
        }:
            raise httpx.ProxyError("407 Proxy Authentication Required")
        if case == "http_invalid_tls":
            raise httpx.ConnectError("CERTIFICATE_VERIFY_FAILED")
        raise httpx.ConnectTimeout("blocked")

    def client(**kwargs: object) -> httpx.Client:
        options.update(kwargs)
        if case == "http_proxy_removed":
            assert all(name not in os.environ for name in probe_http.PROXY_VARIABLES)
        if case == "http_no_proxy":
            assert os.environ["NO_PROXY"] == "172.30.240.4"
        return original(transport=httpx.MockTransport(respond), trust_env=False)

    monkeypatch.setattr(httpx, "Client", client)
    monkeypatch.setattr(probe_http, "require_metadata_alias", Mock())
    before = dict(os.environ)
    result = probe_http.execute(case, auth, ca)
    assert dict(os.environ) == before
    context = options["verify"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert options["max_redirects"] == 1
    if case in {"http_allowed", "gateway_restart"}:
        assert result == ClientResult.FIXTURE_BODY
    elif case in {
        "http_missing_auth",
        "http_invalid_auth",
        "http_redirect_host",
        "http_redirect_ip",
        "http_redirect_port",
    }:
        assert result == ClientResult.PROXY_REJECTED
    elif case == "http_invalid_tls":
        assert result == ClientResult.CERTIFICATE_REJECTED
    else:
        assert result == ClientResult.NETWORK_FAILURE
    if case in {"http_proxy_removed", "http_no_proxy"}:
        assert options["trust_env"] is True
    elif case == "http_trust_env_false":
        assert options["trust_env"] is False


@pytest.mark.parametrize("fault", ["body", "status", "limit", "wrong_proxy_code", "unexpected"])
def test_unsupported_errors_and_responses_cannot_count_as_blocked(
    monkeypatch: pytest.MonkeyPatch,
    auth: ProxyCredentials,
    ca: Path,
    fault: str,
) -> None:
    original = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        if fault == "wrong_proxy_code":
            raise httpx.ProxyError("403 Forbidden")
        if fault == "unexpected":
            raise httpx.RemoteProtocolError("private-secret")
        return httpx.Response(
            503 if fault == "status" else 200,
            content=b"x" * (1024**2 + 1) if fault == "limit" else b"wrong",
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), trust_env=False),
    )
    with pytest.raises(probe_http.HttpProbeError):
        probe_http.execute("http_allowed", auth, ca)


@pytest.mark.parametrize("mode", ["disabled", "enabled"])
def test_ipv6_mode_checks_every_interface(
    monkeypatch: pytest.MonkeyPatch, auth: ProxyCredentials, ca: Path, mode: str
) -> None:
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path: "0" if mode == "enabled" and path.parent.name == "eth0" else "1",
    )
    if mode == "enabled":
        with pytest.raises(probe_http.HttpProbeError, match="ipv6_mode"):
            probe_http.execute("ipv6_disabled", auth, ca)
    else:
        assert probe_http.execute("ipv6_disabled", auth, ca) == ClientResult.IPV6_UNAVAILABLE


@pytest.mark.parametrize("mode", ["blocked", "delivered", "wrong_resolver"])
def test_dns_requires_static_fixture_resolver_and_cannot_accept_delivery(
    monkeypatch: pytest.MonkeyPatch, auth: ProxyCredentials, ca: Path, mode: str
) -> None:
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: (
            b"wrong"
            if mode == "wrong_resolver"
            else b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n"
        ),
    )
    resolver = (
        Mock(side_effect=socket.gaierror("private-secret"))
        if mode == "blocked"
        else Mock(return_value=[])
    )
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    if mode == "blocked":
        assert probe_http.execute("http_dns", auth, ca) == ClientResult.NETWORK_FAILURE
    else:
        with pytest.raises(probe_http.HttpProbeError):
            probe_http.execute("http_dns", auth, ca)
        if mode == "wrong_resolver":
            resolver.assert_not_called()


@pytest.mark.parametrize("mode", ["blocked", "permission", "delivered", "refused"])
def test_udp_requires_blocking_and_rejects_refused_listener(
    monkeypatch: pytest.MonkeyPatch, auth: ProxyCredentials, ca: Path, mode: str
) -> None:
    channel = Mock()
    errors = {
        "blocked": TimeoutError,
        "permission": PermissionError,
        "refused": ConnectionRefusedError,
    }
    channel.recvfrom.side_effect = errors.get(mode)
    manager = Mock()
    manager.__enter__ = Mock(return_value=channel)
    manager.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(socket, "socket", Mock(return_value=manager))
    if mode in {"blocked", "permission"}:
        assert probe_http.execute("http_udp", auth, ca) == ClientResult.ATTEMPTED
    else:
        with pytest.raises(
            ConnectionRefusedError if mode == "refused" else probe_http.HttpProbeError
        ):
            probe_http.execute("http_udp", auth, ca)


@pytest.mark.parametrize("mode", ["local", "absent", "nonlocal"])
def test_metadata_must_be_locally_bound_before_http(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setattr(Path, "read_text", lambda path: "1" if mode == "nonlocal" else "0")
    channel = Mock()
    if mode == "absent":
        channel.bind.side_effect = OSError("private-secret")
    manager = Mock()
    manager.__enter__ = Mock(return_value=channel)
    manager.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(socket, "socket", Mock(return_value=manager))
    if mode == "local":
        probe_http.require_metadata_alias()
        channel.bind.assert_called_once_with(("169.254.169.254", 0))
    else:
        with pytest.raises(probe_http.HttpProbeError, match="metadata_alias"):
            probe_http.require_metadata_alias()
        if mode == "nonlocal":
            channel.bind.assert_not_called()


@pytest.mark.parametrize(
    "fault", ["case", "extra", "duplicate", "version", "whitespace", "nested", "oversize", "result"]
)
def test_probe_wire_result_rejects_tampering(fault: str) -> None:
    raw = probe_http.encode_result("http_allowed", ClientResult.FIXTURE_BODY)
    value = json.loads(raw)
    if fault == "case":
        value["case_name"] = "http_direct_ipv4"
    elif fault == "extra":
        value["secret"] = "private-secret"
    elif fault == "version":
        value["version"] = "other"
    elif fault == "result":
        value["client_result"] = "passed"
    changed = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if fault == "duplicate":
        changed = raw.replace(b"{", b'{"case_name":"http_allowed",', 1)
    elif fault == "whitespace":
        changed = raw + b" "
    elif fault == "nested":
        changed = b"[" * 1500 + b"]" * 1500
    elif fault == "oversize":
        changed = b"x" * 4097
    with pytest.raises(probe_http.HttpProbeError, match="result"):
        probe_http.read_result(changed, "http_allowed")
    assert probe_http.read_result(raw, "http_allowed") == ClientResult.FIXTURE_BODY


def test_deeply_nested_probe_result_is_a_fixed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(json, "loads", Mock(side_effect=RecursionError("private-secret")))
    with pytest.raises(probe_http.HttpProbeError, match="^result$"):
        probe_http.read_result(b"[]", "http_allowed")


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "preflight",
        "controls",
        "credentials",
        "probe",
        "interrupt",
        "deadline",
        "configuration",
    ],
)
def test_cli_redacts_failures_and_clears_total_attempt_timer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    auth: ProxyCredentials,
    fault: str,
) -> None:
    timers: list[float] = []
    monkeypatch.setattr(signal, "signal", Mock(return_value=signal.SIG_DFL))
    monkeypatch.setattr(signal, "setitimer", lambda which, seconds: timers.append(seconds))
    monkeypatch.setattr(Path, "read_text", lambda path: "status")
    checks = {
        name: Mock() for name in ("check_process", "private_controls", "credentials", "execute")
    }
    checks["credentials"].return_value = auth
    checks["execute"].return_value = ClientResult.FIXTURE_BODY
    fail_at = {
        "preflight": "check_process",
        "controls": "private_controls",
        "credentials": "credentials",
        "probe": "execute",
        "interrupt": "execute",
        "deadline": "execute",
    }
    if fault in fail_at:
        checks[fail_at[fault]].side_effect = (
            KeyboardInterrupt()
            if fault == "interrupt"
            else (lambda *args: probe_http._expired(signal.SIGALRM, None))
            if fault == "deadline"
            else ValueError("private-secret")
        )
    for name, check in checks.items():
        monkeypatch.setattr(probe_http, name, check)
    status = probe_http.main(["private-secret"] if fault == "configuration" else ["http_allowed"])
    raw = capsys.readouterr().out
    assert "private-secret" not in raw and auth.password not in raw
    if fault == "none":
        assert status == 0
        assert probe_http.read_result(raw.encode(), "http_allowed") == ClientResult.FIXTURE_BODY
    else:
        assert status == (2 if fault == "configuration" else 130 if fault == "interrupt" else 1)
        assert json.loads(raw)["status"] == "failed"
    assert timers == ([] if fault == "configuration" else [15, 0])


def test_total_attempt_alarm_actually_interrupts_a_stalled_probe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], auth: ProxyCredentials
) -> None:
    import time
    from types import SimpleNamespace

    previous = signal.getsignal(signal.SIGALRM)
    monkeypatch.setattr(probe_http, "FixturePolicy", lambda: SimpleNamespace(attempt_seconds=0.02))
    monkeypatch.setattr(Path, "read_text", lambda path: "status")
    monkeypatch.setattr(probe_http, "check_process", Mock())
    monkeypatch.setattr(probe_http, "private_controls", Mock())
    monkeypatch.setattr(probe_http, "credentials", Mock(return_value=auth))

    def stalled(*args: object) -> ClientResult:
        time.sleep(0.2)
        return ClientResult.FIXTURE_BODY

    monkeypatch.setattr(probe_http, "execute", stalled)
    assert probe_http.main(["http_allowed"]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "http_probe"
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)
