"""Packet probe classification and user-namespace boundaries; Docker tests delivery."""

import errno
import socket
from unittest.mock import MagicMock

import pytest

from nima.egress import probe_network
from nima.egress.rules import NetworkError


@pytest.mark.parametrize(
    "failure",
    [
        None,
        TimeoutError(),
        PermissionError(errno.EPERM, "blocked"),
        ConnectionRefusedError(errno.ECONNREFUSED, "dead fixture"),
    ],
)
def test_dead_or_reachable_tcp_fixture_cannot_count_as_packet_blocked(
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException | None,
) -> None:
    channel = MagicMock()
    channel.__enter__.return_value = channel
    channel.connect.side_effect = failure
    monkeypatch.setattr(socket, "socket", lambda *args: channel)
    if isinstance(failure, (TimeoutError, PermissionError)):
        probe_network.blocked_tcp("172.30.240.4", 9000)
    else:
        with pytest.raises(NetworkError):
            probe_network.blocked_tcp("172.30.240.4", 9000)


@pytest.mark.parametrize("delivered", [True, False])
def test_udp_probe_requires_no_reply_and_never_treats_send_as_delivery_proof(
    monkeypatch: pytest.MonkeyPatch,
    delivered: bool,
) -> None:
    channel = MagicMock()
    channel.__enter__.return_value = channel
    channel.recvfrom.side_effect = None if delivered else TimeoutError()
    monkeypatch.setattr(socket, "socket", lambda *args: channel)
    if delivered:
        with pytest.raises(NetworkError):
            probe_network.blocked_udp(443)
    else:
        probe_network.blocked_udp(443)
    channel.sendto.assert_called_once_with(b"nima-control", ("172.30.240.4", 443))


@pytest.mark.parametrize(
    "fault", ["none", "outer_uid_allowed", "wrong_uid", "missing_capability", "network_changed"]
)
def test_child_cannot_map_outer_observer_uid_or_administer_parent_namespace(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import os
    from types import SimpleNamespace
    from unittest.mock import Mock

    calls: list[str] = []
    reads = 0

    class FakePath:
        def __init__(self, value: str) -> None:
            self.value = value

        def stat(self) -> SimpleNamespace:
            nonlocal reads
            reads += 1
            return SimpleNamespace(st_ino=999 if fault == "network_changed" and reads > 1 else 123)

        def write_text(self, value: str) -> int:
            calls.append(value)
            if "10002 10002" in value and fault != "outer_uid_allowed":
                raise PermissionError()
            return len(value)

        def read_text(self) -> str:
            return "CapEff:\t0\n" if fault == "missing_capability" else "CapEff:\t1000\n"

    monkeypatch.setattr(probe_network, "Path", FakePath)
    monkeypatch.setattr(os, "unshare", Mock())
    monkeypatch.setattr(os, "getuid", lambda: 0 if fault == "wrong_uid" else 10002)
    mark, blocked, forbidden = Mock(), Mock(), Mock()
    monkeypatch.setattr(probe_network, "check_socket_mark", mark)
    monkeypatch.setattr(probe_network, "blocked_tcp", blocked)
    monkeypatch.setattr(probe_network, "_run", forbidden)
    if fault == "none":
        probe_network.child_probe()
        assert calls == ["10002 10002 1\n", "10002 10001 1\n"]
        mark.assert_called_once_with(helper=False)
        blocked.assert_called_once_with("172.30.240.4", 9000)
        forbidden.assert_called_once_with("forbidden")
    else:
        with pytest.raises(NetworkError):
            probe_network.child_probe()


@pytest.mark.parametrize(
    "fault", ["none", "outer_uid_allowed", "child_failed", "child_success", "child_exception"]
)
def test_parent_and_child_privilege_failures_are_contained(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import os
    from unittest.mock import Mock

    monkeypatch.setattr(probe_network, "check_socket_mark", Mock())
    monkeypatch.setattr(probe_network, "_run", Mock())
    monkeypatch.setattr(
        os, "setuid", Mock(side_effect=None if fault == "outer_uid_allowed" else PermissionError())
    )
    monkeypatch.setattr(
        os, "fork", lambda: 0 if fault.startswith("child_") and fault != "child_failed" else 123
    )
    monkeypatch.setattr(os, "waitpid", lambda *args: (123, 256 if fault == "child_failed" else 0))
    monkeypatch.setattr(
        probe_network,
        "child_probe",
        Mock(side_effect=ValueError() if fault == "child_exception" else None),
    )

    def exit_child(value: int) -> None:
        raise SystemExit(value)

    monkeypatch.setattr(os, "_exit", exit_child)
    if fault in {"child_success", "child_exception"}:
        with pytest.raises(SystemExit) as outcome:
            probe_network.privilege_probe()
        assert outcome.value.code == (0 if fault == "child_success" else 1)
    elif fault == "none":
        probe_network.privilege_probe()
    else:
        with pytest.raises(NetworkError):
            probe_network.privilege_probe()


@pytest.mark.parametrize("fault", ["none", "bad_resolver", "dns_delivered", "missing_alias"])
def test_packet_probe_refuses_metadata_and_dns_until_local_setup_is_proven(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    monkeypatch.setattr(probe_network, "check_process", Mock())
    monkeypatch.setattr(
        probe_network,
        "namespace_state",
        Mock(side_effect=NetworkError("network_namespace") if fault == "missing_alias" else None),
    )
    monkeypatch.setattr(
        probe_network,
        "Path",
        lambda value: SimpleNamespace(
            read_bytes=lambda: (
                b"invalid"
                if fault == "bad_resolver"
                else b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n"
            ),
            read_text=lambda: "",
        ),
    )
    privilege, tcp, udp = Mock(), Mock(), Mock()
    monkeypatch.setattr(probe_network, "privilege_probe", privilege)
    monkeypatch.setattr(probe_network, "blocked_tcp", tcp)
    monkeypatch.setattr(probe_network, "blocked_udp", udp)
    dns = Mock(side_effect=None if fault == "dns_delivered" else socket.gaierror())
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    if fault == "none":
        probe_network.probe()
        assert tcp.call_count == 3 and udp.call_count == 3
        assert ("169.254.169.254", 80) in [call.args for call in tcp.call_args_list]
    else:
        with pytest.raises(NetworkError):
            probe_network.probe()
    if fault in {"bad_resolver", "missing_alias"}:
        tcp.assert_not_called()
        udp.assert_not_called()
        dns.assert_not_called()


@pytest.mark.parametrize("failure", [None, OSError("private-secret"), KeyboardInterrupt()])
def test_packet_cli_redacts_faults_and_never_attests_production(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException | None,
) -> None:
    import json
    from unittest.mock import Mock

    monkeypatch.setattr(probe_network, "probe", Mock(side_effect=failure))
    assert probe_network.main(["raw"]) == (
        0 if failure is None else 130 if isinstance(failure, KeyboardInterrupt) else 1
    )
    output = capsys.readouterr().out
    assert "private-secret" not in output
    assert json.loads(output)["production_ready"] is False
    assert probe_network.main(["--private-secret"]) == 2
    assert "private-secret" not in capsys.readouterr().out
