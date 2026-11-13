"""Synthetic PKI and independent delivery counters contain no company records."""

import json
import signal
import socket
import ssl
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from nima.egress import fixtures as fixture_module
from nima.egress.bootstrap import (
    credentials,
    generate_certificates,
    initialize_fixture_state,
    write_certificates,
)
from nima.egress.fixtures import Counters, control_server, http_server, read_counters, udp_server


def test_private_observer_counters_are_independent_and_resettable(tmp_path: Path) -> None:
    counters = Counters()
    counters.add("tcp_accepts")
    counters.request("html", clean=False)
    snapshot = counters.snapshot()
    snapshot["tcp_accepts"] = 999
    assert counters.snapshot()["tcp_accepts"] == 1
    path = tmp_path / "canary.sock"
    with control_server(path, counters, role="canary"):
        assert path.stat().st_mode & 0o777 == 0o600
        observed = read_counters(path, role="canary")
        assert observed["tcp_accepts"] == 1
        assert observed["application_requests"] == 1
        assert observed["headers_clean"] is False
        reset = read_counters(path, role="canary", reset=True)
        assert reset["tcp_accepts"] == 0
        assert reset["headers_clean"] is True
    assert not path.exists()


def test_real_https_verifies_ca_and_records_only_safe_header_observations(tmp_path: Path) -> None:
    material = generate_certificates()
    private, public = tmp_path / "private", tmp_path / "public"
    public.mkdir()
    public.chmod(0o750)
    write_certificates(private, public, material)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(private / "origin.pem", private / "origin.key")
    client_context = ssl.create_default_context(cadata=material.ca.certificate.decode())
    counters = Counters()
    with http_server(
        ("127.0.0.1", 0),
        counters,
        role="origin",
        context=server_context,
        credentials=("fixture-user-sentinel", "fixture-password-sentinel"),
    ) as address:
        for extra in (b"", b"Proxy-Authorization: fixture-password-sentinel\r\n"):
            with (
                socket.create_connection(address, timeout=2) as raw,
                client_context.wrap_socket(raw, server_hostname="allowed.nima.test") as client,
            ):
                client.sendall(
                    b"GET / HTTP/1.1\r\nHost: allowed.nima.test\r\n"
                    + extra
                    + b"Connection: close\r\n\r\n"
                )
                with client.makefile("rb") as stream:
                    response = stream.read(65537)
                assert response.startswith(b"HTTP/1.1 200")
                assert b"Nima fixture" in response
        with (
            socket.create_connection(address, timeout=2) as raw,
            pytest.raises(ssl.SSLCertVerificationError),
        ):
            ssl.create_default_context().wrap_socket(raw, server_hostname="allowed.nima.test")
        observed = counters.snapshot()
        assert observed["application_requests"] == 2
        assert observed["headers_clean"] is False
        assert observed["server_errors"] == 0


def test_real_udp_and_dns_canaries_deliver_positive_controls() -> None:
    for dns in (False, True):
        counters = Counters()
        with udp_server(("127.0.0.1", 0), counters, dns=dns) as address:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(2)
                query = (
                    struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
                    + b"\x08unmapped\x04nima\x04test\x00"
                    + struct.pack("!HH", 1, 1)
                )
                client.sendto(query if dns else b"nima-control", address)
                response, _ = client.recvfrom(1232)
                if dns:
                    assert response[:2] == b"\x12\x34"
                    assert struct.unpack("!H", response[6:8]) == (1,)
                    assert response[-4:] == socket.inet_aton("172.30.240.4")
                else:
                    assert response == b"nima-control-ok"
            observed = counters.snapshot()
            assert observed["dns_queries" if dns else "udp_datagrams"] == 1


def test_reset_cannot_hide_an_unexpected_fixture_error() -> None:
    counters = Counters()
    counters.add("server_errors")
    counters.reset()
    assert counters.snapshot()["server_errors"] == 1


def test_service_startup_and_stop_close_listeners_and_restore_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private, public = tmp_path / "private", tmp_path / "public"
    public.mkdir()
    public.chmod(0o750)
    initialize_fixture_state(private, public, credentials("fixture-user-" + "u" * 16, "p" * 43))
    events: list[str] = []

    @contextmanager
    def listener(
        address: tuple[str, int], *args: object, **kwargs: object
    ) -> Iterator[tuple[str, int]]:
        assert address[0] in {
            "172.30.241.3",
            "172.30.241.4",
            "172.30.240.4",
            "169.254.169.254",
        }
        events.append("listener_open")
        try:
            yield address
        finally:
            events.append("listener_close")

    @contextmanager
    def control(*args: object, **kwargs: object) -> Iterator[None]:
        assert "listener_open" in events
        events.append("control_open")
        try:
            yield
        finally:
            events.append("control_close")

    monkeypatch.setattr(
        fixture_module, "Path", lambda value: private if value == "/fixture-private" else tmp_path
    )
    monkeypatch.setattr(fixture_module, "http_server", listener)
    monkeypatch.setattr(fixture_module, "udp_server", listener)
    monkeypatch.setattr(fixture_module, "control_server", control)
    previous = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    stopped = threading.Event()
    stopped.set()
    for role in ("origin", "bad", "canary", "metadata"):
        events.clear()
        fixture_module.serve_fixture(role, stop_event=stopped)
        assert events.count("listener_open") == events.count("listener_close")
        assert events.index("control_close") < events.index("listener_close")
        assert {number: signal.getsignal(number) for number in previous} == previous


def test_health_command_reads_real_private_control_and_redacts_invalid_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def require(status: str, *, uid: int) -> None:
        assert uid == 10002

    monkeypatch.setattr(fixture_module, "check_process", require)
    monkeypatch.setattr(
        fixture_module, "Path", lambda value: tmp_path if value == "/control" else Path(value)
    )
    with control_server(tmp_path / "canary.sock", Counters(), role="canary"):
        assert fixture_module.main(["health", "--role", "canary"]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "passed"
    assert fixture_module.main(["health", "--role", "private-secret"]) == 1
    output = capsys.readouterr().out
    assert "private-secret" not in output
    assert json.loads(output)["status"] == "failed"
