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
