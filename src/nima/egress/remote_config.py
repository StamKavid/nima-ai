"""Closed offline operator intent; no DNS, Docker, source access or attestation.

https://docs.python.org/3.12/library/json.html#json.loads
https://docs.python.org/3.12/library/ipaddress.html
"""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Never

from nima.evidence import EvidenceError, artifacts

CONFIG_LIMIT = 16 * 1024
ROLES = ("allowed", "invalid_tls", "denied")


class RemoteConfigError(ValueError):
    """Fixed public reason; never include configuration or filesystem values."""


@dataclass(frozen=True, slots=True, repr=False)
class Host:
    label: str
    expected_gateway_ipv4: str


@dataclass(frozen=True, slots=True, repr=False)
class Probe:
    role: str
    hostname: str


@dataclass(frozen=True, slots=True, repr=False)
class Observer:
    authority: str
    credential_file: str


@dataclass(frozen=True, slots=True, repr=False)
class Paths:
    state_dir: str
    gateway_credentials_file: str


@dataclass(frozen=True, slots=True, repr=False)
class Network:
    front_subnet: str
    back_subnet: str


@dataclass(frozen=True, slots=True, repr=False)
class Runtime:
    pins_sha256: str
    gateway_image_id: str
    helper_image_id: str
    worker_image_id: str


@dataclass(frozen=True, slots=True, repr=False)
class Limits:
    max_cases: int
    run_seconds: int
    cleanup_seconds: int
    attempt_seconds: int
    response_bytes: int
    receipt_bytes: int


@dataclass(frozen=True, slots=True, repr=False)
class RemoteConfig:
    host: Host
    probes: tuple[Probe, ...]
    observer: Observer
    paths: Paths
    network: Network
    runtime: Runtime
    limits: Limits


@dataclass(frozen=True, slots=True, repr=False)
class ConfigDocument:
    config: RemoteConfig
    body: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def _fail() -> Never:
    raise RemoteConfigError("remote_config")


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _group(value: object, fields: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(fields.split()):
        _fail()
    return {key: value[key] for key in fields.split()}


def _text(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 4096:
        _fail()
    if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        _fail()
    return value


def _hostname(value: object) -> str:
    host = _text(value)
    labels = host.split(".")
    if (
        len(host) > 253
        or len(labels) < 2
        or labels[-1].isdecimal()
        or any(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) is None for p in labels)
        or labels[-1] in {"test", "invalid", "localhost", "local", "internal", "example", "onion"}
        or any(
            p in {"example", "placeholder", "changeme", "change-me", "your-domain"} for p in labels
        )
        or any(
            host == d or host.endswith("." + d)
            for d in (
                "example.com",
                "example.net",
                "example.org",
                "gov.gr",
                "businessportal.gr",
                "eprocurement.gov.gr",
                "ted.europa.eu",
            )
        )
    ):
        _fail()
    return host


def _path(value: object) -> str:
    text = _text(value)
    path = Path(text)
    if not path.is_absolute() or str(path) != text or ".git" in path.parts or ".." in path.parts:
        _fail()
    if "${" in text or "<" in text or ">" in text or path == Path("/"):
        _fail()
    return text


def _integer(value: object, maximum: int, *, minimum: int = 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail()
    return value


def _hash(value: object, *, image: bool = False) -> str:
    text = _text(value)
    if re.fullmatch(("sha256:" if image else "") + r"[0-9a-f]{64}", text) is None:
        _fail()
    if len(set(text.removeprefix("sha256:"))) == 1 and text.removeprefix("sha256:")[0] in "0f":
        _fail()
    return text


def _subnet(value: object) -> IPv4Network:
    network = IPv4Network(_text(value), strict=True)
    if network.prefixlen > 30 or not any(
        network.subnet_of(IPv4Network(p))
        for p in (
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
        )
    ):
        _fail()
    return network


def _constant(value: str) -> Never:
    _fail()


def decode_config(raw: bytes) -> RemoteConfig:
    """Validate bounded bytes and lexical intent only; no filesystem or network I/O.

    read_config additionally validates existing private paths. Hash syntax here
    declares pins; image/policy approval and actual host observations come later.
    """
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= CONFIG_LIMIT:
            _fail()
        root = _group(
            json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant),
            "version host probes observer paths network runtime limits",
        )
        if root["version"] != "remote-worker-config-v1":
            _fail()
        host = _group(root["host"], "label expected_gateway_ipv4")
        label = _text(host["label"])
        if re.fullmatch(r"[A-Za-z0-9-]{1,64}", label) is None or label.lower() in {
            "placeholder",
            "changeme",
            "change-me",
            "example",
        }:
            _fail()
        address = IPv4Address(_text(host["expected_gateway_ipv4"]))
        if not address.is_global or address.is_multicast or address.is_reserved:
            _fail()
        probes = root["probes"]
        if type(probes) is not list or len(probes) != 3:
            _fail()
        parsed = []
        for item in probes:
            probe = _group(item, "role hostname")
            parsed.append(Probe(_text(probe["role"]), _hostname(probe["hostname"])))
        if {p.role for p in parsed} != set(ROLES) or len({p.hostname for p in parsed}) != 3:
            _fail()
        observer = _group(root["observer"], "authority credential_file")
        authority = _text(observer["authority"])
        if not authority.endswith(":443"):
            _fail()
        observer_host = _hostname(authority[:-4])
        if observer_host in {p.hostname for p in parsed}:
            _fail()
        paths = _group(root["paths"], "state_dir gateway_credentials_file")
        state, gateway, credential = (
            _path(paths["state_dir"]),
            _path(paths["gateway_credentials_file"]),
            _path(observer["credential_file"]),
        )
        if len({state, gateway, credential}) != 3:
            _fail()
        network = _group(root["network"], "front_subnet back_subnet")
        front, back = _subnet(network["front_subnet"]), _subnet(network["back_subnet"])
        if front.overlaps(back):
            _fail()
        runtime = _group(
            root["runtime"], "pins_sha256 gateway_image_id helper_image_id worker_image_id"
        )
        limits = _group(
            root["limits"],
            "max_cases run_seconds cleanup_seconds attempt_seconds response_bytes receipt_bytes",
        )
        bounded = Limits(
            _integer(limits["max_cases"], 30),
            _integer(limits["run_seconds"], 600),
            _integer(limits["cleanup_seconds"], 599, minimum=60),
            _integer(limits["attempt_seconds"], 15),
            _integer(limits["response_bytes"], 1024**2),
            _integer(limits["receipt_bytes"], 64 * 1024),
        )
        if bounded.cleanup_seconds >= bounded.run_seconds:
            _fail()
        return RemoteConfig(
            Host(label, str(address)),
            tuple(sorted(parsed, key=lambda p: ROLES.index(p.role))),
            Observer(authority, credential),
            Paths(state, gateway),
            Network(str(front), str(back)),
            Runtime(
                _hash(runtime["pins_sha256"]),
                _hash(runtime["gateway_image_id"], image=True),
                _hash(runtime["helper_image_id"], image=True),
                _hash(runtime["worker_image_id"], image=True),
            ),
            bounded,
        )
    except (ValueError, TypeError, RecursionError):
        raise RemoteConfigError("remote_config") from None


def private_directory(path: Path) -> int:
    """Open owner-only storage outside Git, rejecting unsafe writable ancestors.

    The caller owns the returned descriptor. Sticky ancestors (for example /tmp)
    may contain an owner-only child; no directory permissions are changed.
    """
    descriptor: int | None = None
    try:
        _path(str(path))
        descriptor = artifacts.directory(path, private=True)
        current = os.dup(descriptor)
        try:
            while True:
                info = os.fstat(current)
                if stat.S_IMODE(info.st_mode) & 0o022 and not info.st_mode & stat.S_ISVTX:
                    raise RemoteConfigError("remote_path")
                try:
                    os.stat(".git", dir_fd=current, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    marker = os.stat(".git", dir_fd=current, follow_symlinks=False)
                    if not stat.S_ISDIR(marker.st_mode):
                        raise RemoteConfigError("remote_path")
                    git = os.open(
                        ".git", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
                    )
                    try:
                        # Managed workspaces can have empty read-only .git guards.
                        # Any content (or a worktree pointer file) denotes Git state.
                        with os.scandir(git) as entries:
                            if next(entries, None) is not None:
                                raise RemoteConfigError("remote_path")
                    finally:
                        os.close(git)
                parent = os.open("..", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                try:
                    above = os.fstat(parent)
                    if (above.st_dev, above.st_ino) == (info.st_dev, info.st_ino):
                        break
                    os.close(current)
                    current, parent = parent, -1
                finally:
                    if parent != -1:
                        os.close(parent)
        finally:
            os.close(current)
        result, descriptor = descriptor, None
        return result
    except (OSError, EvidenceError, ValueError):
        raise RemoteConfigError("remote_path") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_private(path: Path, *, limit: int) -> bytes:
    """Reuse stable no-follow reads with private remote storage requirements."""
    descriptor = private_directory(path.parent)
    try:
        _path(str(path))
        info = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        if info.st_nlink != 1:
            raise RemoteConfigError("remote_path")
        return artifacts.read(descriptor, path.name, limit=limit, private=True)
    except (OSError, EvidenceError, ValueError):
        raise RemoteConfigError("remote_path") from None
    finally:
        os.close(descriptor)


def validate_paths(config: RemoteConfig) -> None:
    """Check paths now; verification must recheck them before runtime use.

    Credential references are metadata-only: their contents are never read here.
    """
    try:
        os.close(private_directory(Path(config.paths.state_dir)))
        for text in (config.observer.credential_file, config.paths.gateway_credentials_file):
            path = Path(text)
            parent = private_directory(path.parent)
            try:
                file = os.open(
                    path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
                )
                try:
                    info = os.fstat(file)
                    artifacts.check_private(info, 0o600)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1
                        or not 0 < info.st_size <= CONFIG_LIMIT
                    ):
                        raise RemoteConfigError("remote_path")
                    entry = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                    if (info.st_dev, info.st_ino, info.st_ctime_ns) != (
                        entry.st_dev,
                        entry.st_ino,
                        entry.st_ctime_ns,
                    ):
                        raise RemoteConfigError("remote_path")
                finally:
                    os.close(file)
            finally:
                os.close(parent)
    except (OSError, EvidenceError, ValueError):
        raise RemoteConfigError("remote_path") from None


def read_config(path: Path) -> ConfigDocument:
    """Read one stable original snapshot and validate private references offline."""
    raw = read_private(path, limit=CONFIG_LIMIT)
    config = decode_config(raw)
    validate_paths(config)
    return ConfigDocument(config, raw)
