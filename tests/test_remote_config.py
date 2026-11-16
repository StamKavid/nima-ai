"""Remote preparation validates intent offline, never runtime or source access."""

import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from nima.egress.remote_config import RemoteConfigError, decode_config, read_config


@pytest.fixture
def configuration(tmp_path: Path) -> dict[str, Any]:
    return {
        "version": "remote-worker-config-v1",
        "host": {"label": "worker-1", "expected_gateway_ipv4": "8.8.8.8"},
        "probes": [
            {"role": role, "hostname": f"{role.replace('_', '-')}.nima-probe.org"}
            for role in ("allowed", "invalid_tls", "denied")
        ],
        "observer": {
            "authority": "observer.nima-probe.org:443",
            "credential_file": str(tmp_path / "observer.secret"),
        },
        "paths": {
            "state_dir": str(tmp_path / "state"),
            "gateway_credentials_file": str(tmp_path / "gateway.secret"),
        },
        "network": {"front_subnet": "10.81.0.0/24", "back_subnet": "10.82.0.0/24"},
        "runtime": {
            "pins_sha256": "1" * 64,
            **{
                f"{role}_image_id": "sha256:" + digit * 64
                for role, digit in (("gateway", "2"), ("helper", "3"), ("worker", "4"))
            },
        },
        "limits": {
            "max_cases": 30,
            "run_seconds": 600,
            "cleanup_seconds": 60,
            "attempt_seconds": 15,
            "response_bytes": 1048576,
            "receipt_bytes": 65536,
        },
    }


def test_typed_intent_preserves_exact_values_and_never_attests_runtime(
    configuration: dict[str, Any],
) -> None:
    result = decode_config(json.dumps(configuration).encode())
    assert result.host.label == "worker-1"
    assert result.host.expected_gateway_ipv4 == "8.8.8.8"
    assert [(p.role, p.hostname) for p in result.probes] == [
        ("allowed", "allowed.nima-probe.org"),
        ("invalid_tls", "invalid-tls.nima-probe.org"),
        ("denied", "denied.nima-probe.org"),
    ]
    assert result.limits.cleanup_seconds == 60
    assert "8.8.8.8" not in repr(result.host)
    assert "nima-probe" not in repr(result)


@pytest.mark.parametrize(
    "group", [None, "host", "observer", "paths", "network", "runtime", "limits"]
)
@pytest.mark.parametrize("fault", ["unknown", "missing", "wrong_type"])
def test_every_object_is_closed(
    configuration: dict[str, Any],
    group: str | None,
    fault: str,
) -> None:
    payload: object = configuration
    target = configuration if group is None else configuration[group]
    if fault == "unknown":
        target["private-sentinel"] = "do-not-echo"
    elif fault == "missing":
        target.pop(next(iter(target)))
    elif group is None:
        payload = []
    else:
        configuration[group] = []
    with pytest.raises(RemoteConfigError, match="^remote_config$") as error:
        decode_config(json.dumps(payload).encode())
    assert "sentinel" not in str(error.value)


@pytest.mark.parametrize("raw", [b"", b"null", b"[]", b"true", b"{", b"\xff", b"x" * 16385])
def test_invalid_or_oversized_json_has_fixed_errors(raw: bytes) -> None:
    with pytest.raises(RemoteConfigError, match="^remote_config$"):
        decode_config(raw)


def test_duplicate_keys_at_any_depth_and_nonfinite_values_fail(
    configuration: dict[str, Any],
) -> None:
    raw = json.dumps(configuration).encode()
    for bad in (
        raw.replace(b"{", b'{"version":"remote-worker-config-v1",', 1),
        raw.replace(b'"label":', b'"label":"duplicate", "label":', 1),
        raw.replace(b'"run_seconds": 600', b'"run_seconds": NaN'),
        b"[" * 1200 + b"]" * 1200,
    ):
        with pytest.raises(RemoteConfigError):
            decode_config(bad)


@pytest.mark.parametrize(
    "group,field,bad",
    [
        ("host", "label", "worker label"),
        ("host", "label", "x" * 65),
        ("host", "expected_gateway_ipv4", "127.0.0.1"),
        ("host", "expected_gateway_ipv4", "10.0.0.1"),
        ("host", "expected_gateway_ipv4", "203.0.113.1"),
        ("host", "expected_gateway_ipv4", "224.0.0.1"),
        ("host", "expected_gateway_ipv4", "2001:4860:4860::8888"),
        ("observer", "authority", "https://observer.nima-probe.org:443"),
        ("observer", "authority", "observer.nima-probe.org:8443"),
        ("observer", "authority", "allowed.nima-probe.org:443"),
        ("paths", "state_dir", "relative/state"),
        ("paths", "state_dir", "/tmp/../state"),
        ("paths", "state_dir", "/tmp//state"),
        ("paths", "state_dir", "/tmp/.git/state"),
        ("paths", "state_dir", "/PRIVATE/<STATE>"),
        ("paths", "state_dir", "/tmp/state\x00"),
        ("network", "front_subnet", "10.81.0.1/24"),
        ("network", "front_subnet", "10.82.0.0/23"),
        ("network", "front_subnet", "127.0.0.0/24"),
        ("network", "front_subnet", "8.8.8.0/24"),
        ("runtime", "pins_sha256", "latest"),
        ("runtime", "worker_image_id", "sha256:" + "0" * 64),
    ],
)
def test_invalid_declared_context_fails_without_echo(
    configuration: dict[str, Any],
    group: str,
    field: str,
    bad: object,
) -> None:
    configuration[group][field] = bad
    with pytest.raises(RemoteConfigError, match="^remote_config$"):
        decode_config(json.dumps(configuration).encode())


@pytest.mark.parametrize(
    "host",
    [
        "8.8.8.8",
        "allowed.nima-probe.org.",
        "ALLOWED.nima-probe.org",
        "a..org",
        "user@host.org",
        "probe.org/path",
        "*.probe.org",
        "-bad.probe.org",
        "é.probe.org",
        "probe.invalid",
        "placeholder.org",
        "example.com",
        "publicity.businessportal.gr",
        "sub.gov.gr",
        "probe.org:443",
    ],
)
def test_invalid_probe_hosts_and_known_sources_are_rejected(
    configuration: dict[str, Any],
    host: str,
) -> None:
    configuration["probes"][0]["hostname"] = host
    with pytest.raises(RemoteConfigError):
        decode_config(json.dumps(configuration).encode())


@pytest.mark.parametrize(
    "field,maximum",
    [
        ("max_cases", 30),
        ("run_seconds", 600),
        ("cleanup_seconds", 599),
        ("attempt_seconds", 15),
        ("response_bytes", 1048576),
        ("receipt_bytes", 65536),
    ],
)
@pytest.mark.parametrize("fault", ["boolean", "float", "zero", "overflow"])
def test_exact_integer_resource_bounds(
    configuration: dict[str, Any],
    field: str,
    maximum: int,
    fault: str,
) -> None:
    configuration["limits"][field] = {
        "boolean": True,
        "float": 1.0,
        "zero": 0,
        "overflow": maximum + 1,
    }[fault]
    with pytest.raises(RemoteConfigError):
        decode_config(json.dumps(configuration).encode())


def test_case_roles_unique_hosts_and_cleanup_reserve_are_required(
    configuration: dict[str, Any],
) -> None:
    for fault in ("roles", "hosts", "extra", "reserve", "same_paths"):
        value = json.loads(json.dumps(configuration))
        if fault == "roles":
            value["probes"][0]["role"] = "denied"
        if fault == "hosts":
            value["probes"][0]["hostname"] = value["probes"][1]["hostname"]
        if fault == "extra":
            value["probes"][0]["extra"] = True
        if fault == "reserve":
            value["limits"]["run_seconds"] = 60
        if fault == "same_paths":
            value["paths"]["state_dir"] = value["observer"]["credential_file"]
        with pytest.raises(RemoteConfigError):
            decode_config(json.dumps(value).encode())


@pytest.fixture
def private_config(configuration: dict[str, Any], tmp_path: Path) -> Path:
    Path(configuration["paths"]["state_dir"]).mkdir(mode=0o700)
    for name in ("observer.secret", "gateway.secret"):
        file = tmp_path / name
        file.write_bytes(b"private-credential-sentinel")
        file.chmod(0o600)
    file = tmp_path / "remote.json"
    file.write_text(json.dumps(configuration))
    file.chmod(0o600)
    return file


def test_private_read_binds_original_bytes_without_network_or_processes(
    private_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("offline preparation attempted network or subprocess work")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    raw = private_config.read_bytes()
    result = read_config(private_config)
    assert result.config == decode_config(raw)
    assert result.body == raw
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert "private-credential-sentinel" not in repr(result)
    assert sorted(p.name for p in private_config.parent.iterdir()) == [
        "gateway.secret",
        "observer.secret",
        "remote.json",
        "state",
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "config_mode",
        "parent_mode",
        "state_mode",
        "credential_mode",
        "missing_credential",
        "config_symlink",
        "state_symlink",
        "credential_symlink",
        "config_fifo",
        "credential_fifo",
        "config_hardlink",
        "git_directory",
        "git_worktree",
        "huge",
        "missing_state",
    ],
)
def test_real_private_filesystem_rejects_unsafe_inputs_without_repair(
    private_config: Path,
    fault: str,
) -> None:
    root = private_config.parent
    if fault == "config_mode":
        private_config.chmod(0o644)
    if fault == "parent_mode":
        root.chmod(0o755)
    if fault == "state_mode":
        (root / "state").chmod(0o755)
    if fault == "credential_mode":
        (root / "gateway.secret").chmod(0o644)
    if fault == "missing_credential":
        (root / "gateway.secret").unlink()
    if fault.endswith("symlink"):
        target = {
            "config_symlink": private_config,
            "state_symlink": root / "state",
            "credential_symlink": root / "gateway.secret",
        }[fault]
        old = target.with_name(target.name + ".old")
        target.rename(old)
        target.symlink_to(old)
    if fault.endswith("fifo"):
        target = private_config if fault == "config_fifo" else root / "gateway.secret"
        target.unlink()
        os.mkfifo(target, 0o600)
    if fault == "config_hardlink":
        os.link(private_config, root / "alias.json")
    if fault == "git_directory":
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    if fault == "git_worktree":
        (root / ".git").write_text("gitdir: /unread/control")
    if fault == "huge":
        private_config.write_bytes(b"x" * 16385)
    if fault == "missing_state":
        (root / "state").rmdir()
    before = {p.name: (p.lstat().st_mode, p.lstat().st_ino) for p in root.iterdir()}
    with pytest.raises(RemoteConfigError, match="^remote_(config|path)$"):
        read_config(private_config)
    assert before == {p.name: (p.lstat().st_mode, p.lstat().st_ino) for p in root.iterdir()}


def test_missing_input_and_changed_config_have_fixed_errors(
    private_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RemoteConfigError, match="^remote_path$"):
        read_config(private_config.with_name("missing-private-sentinel"))
    original = os.fstat
    identity = private_config.stat().st_ino
    reads = 0

    def changed(fd: int) -> os.stat_result:
        nonlocal reads
        info = original(fd)
        if info.st_ino == identity:
            reads += 1
            if reads == 2:
                with private_config.open("ab") as stream:
                    stream.write(b" ")
                return original(fd)
        return info

    monkeypatch.setattr(os, "fstat", changed)
    with pytest.raises(RemoteConfigError, match="^remote_path$"):
        read_config(private_config)
    assert reads == 2


def test_directory_observation_failure_does_not_leak_descriptors(
    private_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = os.fstat
    ancestor = private_config.parent.parent.stat().st_ino

    def unavailable(fd: int) -> os.stat_result:
        info = original(fd)
        if info.st_ino == ancestor:
            raise OSError("private-path-sentinel")
        return info

    monkeypatch.setattr(os, "fstat", unavailable)
    before = len(list(Path("/proc/self/fd").iterdir()))
    for _ in range(10):
        with pytest.raises(RemoteConfigError, match="^remote_path$"):
            read_config(private_config)
    assert len(list(Path("/proc/self/fd").iterdir())) == before
