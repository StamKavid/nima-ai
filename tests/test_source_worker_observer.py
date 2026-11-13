"""Synthetic PKI and independent delivery counters contain no company records."""

import ssl
from contextlib import ExitStack
from pathlib import Path

import pytest

from nima.egress.bootstrap import (
    generate_certificates,
    write_certificates,
)
from nima.egress.fixtures import Counters, control_server, http_server, udp_server
from nima.egress.observer import FixtureTargets, fixture_smoke


def test_observer_runs_real_delivery_controls_and_rejects_nonfixture_targets(
    tmp_path: Path,
) -> None:
    material = generate_certificates()
    private, public = tmp_path / "private", tmp_path / "public"
    public.mkdir()
    public.chmod(0o750)
    write_certificates(private, public, material)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(private / "canary.pem", private / "canary.key")
    canary, host = Counters(), Counters()
    auth = ("fixture-user-sentinel", "fixture-password-sentinel")
    with ExitStack() as stack:
        plain = stack.enter_context(
            http_server(("127.0.0.1", 0), canary, role="canary", context=None, credentials=auth)
        )
        secure = stack.enter_context(
            http_server(("127.0.0.1", 0), canary, role="canary", context=context, credentials=auth)
        )
        host_address = stack.enter_context(
            http_server(("127.0.0.1", 0), host, role="host", context=None, credentials=auth)
        )
        udp = stack.enter_context(udp_server(("127.0.0.1", 0), canary, dns=False))
        dns = stack.enter_context(udp_server(("127.0.0.1", 0), canary, dns=True))
        stack.enter_context(control_server(tmp_path / "canary.sock", canary, role="canary"))
        targets = FixtureTargets(
            canary_ip="127.0.0.1",
            host_ip="127.0.0.1",
            http_port=plain[1],
            tls_ports=(secure[1],),
            udp_ports=(udp[1],),
            dns_port=dns[1],
            host_port=host_address[1],
        )
        fixture_smoke(targets, public / "ca.pem", tmp_path)
        assert canary.snapshot()["application_requests"] == 2
        assert canary.snapshot()["udp_datagrams"] == 1
        assert canary.snapshot()["dns_queries"] == 1
        assert host.snapshot()["application_requests"] == 1
    with pytest.raises(ValueError, match="^fixture_targets$"):
        FixtureTargets(canary_ip="192.0.2.1")


@pytest.mark.parametrize("fault", ["none", "negative", "unknown", "missing", "large"])
def test_gateway_observation_accepts_only_bounded_numeric_admin_counters(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import httpx

    from nima.egress import observer
    from nima.egress.fixtures import Counters, FixtureError

    rows = [
        {"name": "http.nima.rbac.allowed", "value": 2},
        {"name": "http.nima.rbac.denied", "value": 5},
    ]
    if fault == "negative":
        rows[0]["value"] = -1
    elif fault == "unknown":
        rows[0]["name"] = "unexpected.secret"
    elif fault == "missing":
        rows.pop()

    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/stats"
        assert request.url.params["format"] == "json"
        return (
            httpx.Response(200, content=b"x" * 65537)
            if fault == "large"
            else httpx.Response(200, json={"stats": rows})
        )

    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(response))
    monkeypatch.setattr(observer, "read_counters", lambda *args, **kwargs: Counters().snapshot())
    if fault == "none":
        result = observer.gateway_observation(reset=True)
        assert result["allowed"] == 2
        assert result["denied"] == 5
        assert result["origin"]["application_requests"] == 0
    else:
        with pytest.raises(FixtureError):
            observer.gateway_observation()


@pytest.mark.parametrize("fault", ["none", "nonlocal_bind", "missing_alias"])
def test_packet_controls_never_request_metadata_without_a_local_alias(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import socket
    from pathlib import Path
    from unittest.mock import MagicMock, Mock

    import httpx

    from nima.egress import observer
    from nima.egress.fixtures import Counters, FixtureError

    monkeypatch.setattr(
        Path, "read_text", lambda self: "1\n" if fault == "nonlocal_bind" else "0\n"
    )
    channel = MagicMock()
    channel.__enter__.return_value = channel
    if fault == "missing_alias":
        channel.bind.side_effect = OSError("not local")
    monkeypatch.setattr(socket, "socket", lambda *args: channel)
    client = MagicMock()
    client.__enter__.return_value = client
    monkeypatch.setattr(httpx, "Client", Mock(return_value=client))
    control = Mock()
    monkeypatch.setattr(observer, "fixture_smoke", Mock())
    monkeypatch.setattr(observer, "_http_control", control)
    counter = Counters()
    counter.request(None, clean=True)
    monkeypatch.setattr(observer, "read_counters", lambda *args, **kwargs: counter.snapshot())
    if fault == "none":
        value = observer.packet_control()
        assert value["metadata"]["application_requests"] == 1
        channel.bind.assert_called_once_with(("169.254.169.254", 0))
        control.assert_called_once_with(client, "http://169.254.169.254/")
    else:
        with pytest.raises(FixtureError):
            observer.packet_control()
        control.assert_not_called()


@pytest.mark.parametrize("fault", ["none", "client", "missing_delivery", "headers", "errors"])
def test_gateway_controls_require_verified_body_and_independent_delivery(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from unittest.mock import Mock

    from nima.egress import observer
    from nima.egress.bootstrap import credentials
    from nima.egress.fixtures import FixtureError
    from nima.egress.receipt import ClientResult

    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    monkeypatch.setattr(observer, "credentials", Mock(return_value=auth))
    outcomes = Mock(
        return_value=ClientResult.NETWORK_FAILURE
        if fault == "client"
        else ClientResult.FIXTURE_BODY
    )
    monkeypatch.setattr(observer, "execute", outcomes)
    counts = Counters()
    counts.request("html", clean=fault != "headers")
    if fault == "errors":
        counts.add("server_errors")
    before = {
        "version": "unused",
        "allowed": 2,
        "denied": 0,
        "origin": Counters().snapshot(),
        "bad": Counters().snapshot(),
    }
    after = {
        **before,
        "allowed": 4,
        "origin": counts.snapshot(),
        "bad": Counters().snapshot() if fault == "missing_delivery" else counts.snapshot(),
    }
    monkeypatch.setattr(observer, "gateway_observation", Mock(side_effect=[before, after]))
    if fault == "none":
        result = observer.gateway_control()
        assert result["origin"]["application_requests"] == 1
        assert result["bad"]["application_requests"] == 1
        assert outcomes.call_args_list[0].args[2] == Path("/fixture-public/ca.pem")
        assert outcomes.call_args_list[1].args[2] == Path("/fixture-private/bad-ca.pem")
    else:
        with pytest.raises(FixtureError, match="^observer_gateway$"):
            observer.gateway_control()
