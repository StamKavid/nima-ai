"""UUID-owned closed fixtures on the local Docker daemon; no live profile.

Images must already be built/pulled. The 600-second runtime includes preparation
and cleanup, with the final 60 seconds reserved for cleanup. Never prune or run
Compose down: validate every exact resource identity before any deletion.
"""

import json
import os
import re
import secrets
import time
from ipaddress import ip_network
from pathlib import Path
from typing import Any
from uuid import uuid4

from nima.egress.commands import capture
from nima.egress.policy import FixturePolicy
from nima.egress.preflight import check_host
from nima.egress.seccomp import build_profile
from nima.evidence import artifacts

ROOT = Path(__file__).resolve().parents[3]
SUBNETS = ("172.30.240.0/24", "172.30.241.0/24")
VOLUMES = {
    "fixture-private",
    "fixture-public",
    "gateway-private",
    "gateway-admin",
    "controls",
    "browser-home",
}
SERVICES = {
    "initialize",
    "anchor",
    "nss",
    "origin",
    "bad",
    "canary",
    "observer",
    "worker",
    "gateway",
    "gateway-validate",
    "network-setup",
    "network-inspect",
    "metadata",
    "network-probe",
}


class StackError(RuntimeError):
    """Fixed codes; never include Docker output or private fixture configuration."""


def executable(name: str) -> str:
    if name not in {"docker", "ip"}:
        raise StackError("fixture_tool")
    for base in ("/usr/bin", "/usr/local/bin", "/usr/sbin", "/sbin", "/bin"):
        path = Path(base) / name
        if path.is_file():
            return str(path)
    raise StackError("fixture_tool")


def _json(raw: str) -> Any:
    # Docker/helper responses only. Callers check the required shape and values;
    # traffic-counter decoding is a separate boundary in the HTTP runner.
    if len(raw) > 65536:
        raise StackError("fixture_observation")
    try:
        return json.loads(raw)
    except (ValueError, RecursionError):
        raise StackError("fixture_observation") from None


def _network(raw: str) -> tuple[str, int]:
    value = _json(raw)
    if (
        type(value) is not dict
        or value.get("status") != "passed"
        or value.get("metadata_alias") is not True
        or value.get("ipv6_disabled") is not True
        or type(value.get("policy_sha256")) is not str
        or re.fullmatch(r"[0-9a-f]{64}", value["policy_sha256"]) is None
        or type(value.get("network_inode")) is not int
        or not 0 < value["network_inode"] < 2**64
    ):
        raise StackError("fixture_policy")
    return value["policy_sha256"], value["network_inode"]


class FixtureStack:
    def __init__(self, state: Path) -> None:
        os.close(artifacts.directory(state, private=True))
        self.state = state.absolute()
        self.run_id = str(uuid4())
        self.project = "nima-egress-" + self.run_id.replace("-", "")
        self.docker = executable("docker")
        self.started = time.monotonic()
        self.deadline = self.started + FixturePolicy().max_seconds
        self.in_cleanup = False
        self.created = self.cleaned = False
        self.images: tuple[tuple[str, str], ...] = ()
        self.network_identity: tuple[str, int] | None = None
        self.environment = {
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "DOCKER_TLS",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
            }
        }
        self.env_file = self.state / "fixture.env"
        self.auth = ("nima-fixture-" + secrets.token_urlsafe(12), secrets.token_urlsafe(32))

    def remaining(self) -> float:
        left = self.deadline - time.monotonic() - (0 if self.in_cleanup else 60)
        if left <= 0:
            raise StackError("fixture_deadline")
        return left

    def command(self, *arguments: str, timeout: float = 90, exact: bool = False) -> str:
        result = capture(
            (self.docker, "--host=unix:///var/run/docker.sock", *arguments),
            cwd=ROOT,
            env=self.environment,
            timeout=min(timeout, self.remaining()),
        )
        if result.returncode:
            raise StackError("fixture_command")
        return result.stdout if exact else result.stdout.strip()

    def compose(self, *arguments: str, exact: bool = False) -> str:
        if arguments[0] in {"up", "run", "start"}:
            self.created = True  # Set before the request, including partial startup.
        return self.command(
            "compose",
            "--env-file",
            str(self.env_file),
            "-p",
            self.project,
            "-f",
            str(ROOT / "infra/compose.source-worker-test.yml"),
            *arguments,
            exact=exact,
        )

    def _routes(self) -> None:
        result = capture(
            (executable("ip"), "-j", "-4", "route", "show", "table", "all"),
            cwd=ROOT,
            env={"LC_ALL": "C"},
            timeout=min(10, self.remaining()),
        )
        routes = _json(result.stdout)
        if result.returncode or type(routes) is not list or len(routes) > 1024:
            raise StackError("fixture_routes")
        try:
            for row in routes:
                if type(row) is not dict or type(row.get("dst")) is not str:
                    raise ValueError
                if row["dst"] in {"default", "0.0.0.0/0"}:
                    continue
                route = ip_network(row["dst"], strict=False)
                if route.version != 4 or any(route.overlaps(ip_network(net)) for net in SUBNETS):
                    raise ValueError
        except (ValueError, TypeError):
            raise StackError("fixture_routes") from None

    def prepare(self) -> None:
        info = _json(
            self.command(
                "info",
                "--format",
                '{"OSType":"{{.OSType}}","Architecture":"{{.Architecture}}","Root":"{{.DockerRootDir}}"}',
            )
        )
        if type(info) is not dict or type(info.get("Root")) is not str:
            raise StackError("fixture_info")
        filesystem = os.statvfs(info["Root"])
        check_host(info, filesystem.f_bavail * filesystem.f_frsize)
        self._routes()
        for identity in self.command("network", "ls", "-q").splitlines():
            configs = _json(
                self.command("network", "inspect", identity, "--format", "{{json .IPAM.Config}}")
            )
            if configs is not None and type(configs) is not list:
                raise StackError("fixture_subnet")
            for entry in configs or []:
                if type(entry) is not dict:
                    raise StackError("fixture_subnet")
                subnet = entry.get("Subnet")
                if subnet and any(ip_network(subnet).overlaps(ip_network(net)) for net in SUBNETS):
                    raise StackError("fixture_subnet")
        pins = _json((ROOT / "infra/source-worker/pins.json").read_text())
        images = []
        for role, name in (
            ("worker", "nima-egress-worker:local"),
            ("helper", "nima-egress-helper:local"),
            ("gateway", pins["images"]["gateway"]),
        ):
            identity = self.command("image", "inspect", name, "--format", "{{.Id}}")
            if re.fullmatch(r"sha256:[0-9a-f]{64}", identity) is None:
                raise StackError("fixture_image")
            images.append((role, identity))
        self.images = tuple(images)
        profile = self.state / "seccomp.json"
        with profile.open("xb") as file:
            file.write(build_profile((ROOT / "infra/source-worker/seccomp.json").read_bytes()))
        profile.chmod(0o600)
        resolver = self.state / "resolv.conf"
        with resolver.open("xb") as file:
            file.write(b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n")
        resolver.chmod(0o644)  # Public literals inside the private state directory.
        values = {
            "NIMA_RUN_ID": self.run_id,
            "NIMA_WORKER_IMAGE": dict(self.images)["worker"],
            "NIMA_HELPER_IMAGE": dict(self.images)["helper"],
            "NIMA_SECCOMP_PATH": str(profile),
            "NIMA_RESOLV_PATH": str(resolver),
            "NIMA_FIXTURE_USERNAME": self.auth[0],
            "NIMA_FIXTURE_PASSWORD": self.auth[1],
        }
        descriptor = os.open(
            self.env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "w") as file:
            file.write("".join(key + "=" + value + "\n" for key, value in values.items()))
        self.compose("config", "--quiet")

    def start(self) -> None:
        self.compose(
            "up", "-d", "--wait", "--wait-timeout", "60", "anchor", "origin", "bad", "canary"
        )
        networks = self.command(
            "network", "ls", "-q", "--filter", "label=com.docker.compose.project=" + self.project
        ).splitlines()
        if len(networks) != 2 or any(
            self.command("network", "inspect", identity, "--format", "{{.Internal}}") != "true"
            for identity in networks
        ):
            raise StackError("fixture_network")
        self.compose("run", "--rm", "--no-deps", "nss")
        self.compose("run", "--rm", "--no-deps", "gateway-validate")
        self.compose("up", "-d", "--wait", "--no-deps", "gateway")
        installed = _network(self.compose("run", "--rm", "--no-deps", "network-setup"))
        observed = _network(self.compose("run", "--rm", "--no-deps", "network-inspect"))
        if installed != observed:
            raise StackError("fixture_policy")
        self.network_identity = observed

    def cleanup(self) -> None:
        self.in_cleanup = True
        if self.created:
            selected: dict[str, list[str]] = {}
            for kind in ("container", "network", "volume"):
                arguments = ("ps", "-aq") if kind == "container" else (kind, "ls", "-q")
                ids = self.command(
                    *arguments, "--filter", "label=com.docker.compose.project=" + self.project
                ).splitlines()
                if len(ids) > 64 or len(ids) != len(set(ids)):
                    raise StackError("fixture_resource_identity")
                for identity in ids:
                    if (
                        kind == "volume"
                        and identity not in {self.project + "_" + name for name in VOLUMES}
                    ) or (kind != "volume" and re.fullmatch(r"[0-9a-f]{12,64}", identity) is None):
                        raise StackError("fixture_resource_identity")
                    labels = ".Config.Labels" if kind == "container" else ".Labels"
                    template = (
                        '{"run":"{{index '
                        + labels
                        + ' "io.nima.fixture.run_id"}}","project":"{{index '
                        + labels
                        + ' "com.docker.compose.project"}}","role":"{{index '
                        + labels
                        + ' "com.docker.compose.service"}}"}'
                    )
                    owner = _json(self.command(kind, "inspect", identity, "--format", template))
                    if (
                        type(owner) is not dict
                        or owner.get("run") != self.run_id
                        or owner.get("project") != self.project
                        or (kind == "container" and owner.get("role") not in SERVICES)
                    ):
                        raise StackError("fixture_resource_ownership")
                selected[kind] = ids
            # Validate all three resource classes before deleting any of them.
            if selected["container"]:
                self.command("stop", "--time", "3", *selected["container"])
                self.command("rm", "--force", "--volumes", *selected["container"])
            for kind in ("network", "volume"):
                if selected[kind]:
                    self.command(kind, "rm", *selected[kind])
            for args in (("ps", "-aq"), ("network", "ls", "-q"), ("volume", "ls", "-q")):
                if self.command(
                    *args, "--filter", "label=com.docker.compose.project=" + self.project
                ):
                    raise StackError("fixture_cleanup")
        self.env_file.unlink(missing_ok=True)
        self.remaining()
        self.cleaned = True
