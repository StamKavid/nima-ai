"""Fixed helper operations and privilege gates; real kernel effects run in Docker."""

import json
from pathlib import Path
from typing import Any

import pytest

from nima.egress.rules import NetworkError, decode_ruleset, policy_objects


def kernel_dump() -> bytes:
    rows = policy_objects()
    for row in rows:
        if "counter" in row:
            row["counter"].update(packets=0, bytes=0)
    return json.dumps(
        {
            "nftables": [
                {
                    "metainfo": {
                        "version": "1.0.6",
                        "release_name": "test",
                        "json_schema_version": 1,
                    }
                },
                *rows,
            ]
        }
    ).encode()


def test_namespace_guard_requires_exact_closed_addresses_and_disabled_forwarding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.egress import network

    addresses: list[dict[str, Any]] = [
        {"ifname": "lo", "addr_info": [{"family": "inet", "local": "127.0.0.1", "prefixlen": 8}]},
        {
            "ifname": "eth0",
            "addr_info": [{"family": "inet", "local": "172.30.240.3", "prefixlen": 24}],
        },
    ]
    monkeypatch.setattr(network, "_run", lambda mode: json.dumps(addresses).encode())
    monkeypatch.setattr(Path, "read_text", lambda self: "1\n" if "ipv6" in str(self) else "0\n")
    network.namespace_state(installed=False)
    with pytest.raises(NetworkError):
        network.namespace_state(installed=True)
    addresses[0]["addr_info"].append(
        {"family": "inet", "local": "169.254.169.254", "prefixlen": 32}
    )
    network.namespace_state(installed=True)
    monkeypatch.setattr(Path, "read_text", lambda self: "1\n")
    with pytest.raises(NetworkError):
        network.namespace_state(installed=True)


def test_installer_preserves_other_tables_and_reads_back_after_atomic_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nima.egress import network

    operations: list[str] = []
    states: list[bool] = []

    def run(mode: str) -> bytes:
        operations.append(mode)
        if mode in {"read", "tables"}:
            return (
                kernel_dump()
                if "install" in operations
                else json.dumps(
                    {
                        "nftables": [
                            {
                                "metainfo": {
                                    "version": "1.0.6",
                                    "release_name": "test",
                                    "json_schema_version": 1,
                                }
                            },
                            {"table": {"family": "ip", "name": "nat"}},
                        ]
                    }
                ).encode()
            )
        return b""

    def state(*, installed: bool) -> int:
        states.append(installed)
        return 12345

    monkeypatch.setattr(network, "check_process", lambda *args, **kwargs: None)
    monkeypatch.setattr(network, "_run", run)
    monkeypatch.setattr(network, "namespace_state", state)
    snapshot, inode = network.install()
    assert inode == 12345
    assert snapshot.fingerprint == decode_ruleset(kernel_dump()).fingerprint
    assert operations == ["tables", "check", "install", "alias", "read"]
    assert states == [False, True]
    operations.clear()
    existing = json.loads(kernel_dump())
    existing["nftables"] = [
        row for row in existing["nftables"] if "metainfo" in row or "table" in row
    ]
    monkeypatch.setattr(network, "_run", lambda mode: json.dumps(existing).encode())
    with pytest.raises(NetworkError, match="^network_existing$"):
        network.install()


@pytest.mark.parametrize(
    "mode,result", [("read", 0), ("read", 1), ("forbidden", 1), ("forbidden", 0), ("invalid", 0)]
)
def test_fixed_tool_boundary_has_no_shell_and_requires_a_real_permission_denial(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    result: int,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    from nima.egress import network

    runner = Mock(
        return_value=SimpleNamespace(
            returncode=result, stdout=b"{}", stderr=b"Operation not permitted"
        )
    )
    import subprocess

    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    if mode == "invalid" or (mode == "forbidden") == (result == 0):
        with pytest.raises(NetworkError):
            network._run(mode)
    else:
        network._run(mode)
        call = runner.call_args
        assert call.args[0][0].startswith("/")
        assert call.kwargs["shell"] is False
        assert call.kwargs["timeout"] == 10
        assert call.kwargs["env"] == {"LC_ALL": "C"}


@pytest.mark.parametrize("operation", ["install", "inspect"])
@pytest.mark.parametrize("failure", [None, OSError("private-secret"), KeyboardInterrupt()])
def test_helper_cli_never_exposes_tool_errors_or_attests_production(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    operation: str,
    failure: BaseException | None,
) -> None:
    from unittest.mock import Mock

    from nima.egress import network

    function = Mock(side_effect=failure, return_value=(decode_ruleset(kernel_dump()), 123))
    monkeypatch.setattr(network, operation, function)
    assert network.main([operation]) == (
        0 if failure is None else 130 if isinstance(failure, KeyboardInterrupt) else 1
    )
    output = capsys.readouterr().out
    assert "private-secret" not in output
    value = json.loads(output)
    assert value["production_ready"] is False
    if failure is None:
        assert value["network_inode"] == 123
        assert value["metadata_alias"] is True
    assert network.main(["--private-secret"]) == 2
    assert "private-secret" not in capsys.readouterr().out


@pytest.mark.parametrize("fault", ["missing", "large", "wrong_denial", "os_error", "timeout"])
def test_tool_boundary_rejects_missing_tools_unbounded_output_and_false_denials(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    import subprocess
    from types import SimpleNamespace
    from unittest.mock import Mock

    from nima.egress import network

    runner = Mock(
        return_value=SimpleNamespace(
            returncode=1, stdout=b"x" * 65537 if fault == "large" else b"", stderr=b"wrong failure"
        )
    )
    if fault == "os_error":
        runner.side_effect = OSError("private-secret")
    elif fault == "timeout":
        runner.side_effect = subprocess.TimeoutExpired("private-secret", 10)
    monkeypatch.setattr(subprocess, "run", runner)
    monkeypatch.setattr(Path, "is_file", lambda self: fault != "missing")
    with pytest.raises(NetworkError):
        network._run("forbidden")
