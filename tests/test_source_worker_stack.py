"""Controller lifecycle faults, independent of Docker enforcement tests."""

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nima.egress import stack
from nima.egress.commands import CommandResult


class Daemon:
    def __init__(self) -> None:
        self.project = ""
        self.run_id = ""
        self.resources = False
        self.calls: list[tuple[str, ...]] = []
        self.owner = ""
        self.routes: object = [{"dst": "default"}, {"dst": "172.17.0.0/16"}]
        self.image = "sha256:" + "a" * 64
        self.internal = "true"
        self.policy = "a" * 64

    def capture(self, argv: tuple[str, ...], **kwargs: object) -> CommandResult:
        args = argv[2:] if argv[0].endswith("docker") else argv[1:]
        self.calls.append(args)
        out = ""
        if argv[0].endswith("ip"):
            out = json.dumps(self.routes)
        elif args[0] == "info":
            out = json.dumps({"OSType": "linux", "Architecture": "amd64", "Root": "/tmp"})
        elif args[:2] == ("image", "inspect"):
            out = self.image
        elif args[0] == "compose":
            if "up" in args:
                self.resources = True
            if args[-1] in {"network-setup", "network-inspect"}:
                out = json.dumps(
                    {
                        "status": "passed",
                        "metadata_alias": True,
                        "ipv6_disabled": True,
                        "policy_sha256": self.policy,
                        "network_inode": 123,
                    }
                )
        elif args[:2] == ("network", "ls"):
            out = "\n".join(["b" * 64, "c" * 64]) if self.resources else ""
        elif args[:2] == ("ps", "-aq"):
            out = "a" * 64 if self.resources else ""
        elif args[:2] == ("volume", "ls"):
            out = self.project + "_controls" if self.resources else ""
        elif len(args) > 1 and args[1] == "inspect":
            if args[-1] == "{{.Internal}}":
                out = self.internal
            elif args[-1] == "{{json .IPAM.Config}}":
                out = "[]"
            else:
                out = json.dumps(
                    {"run": self.owner or self.run_id, "project": self.project, "role": "worker"}
                )
        elif args[:2] == ("volume", "rm"):
            self.resources = False
        return CommandResult(0, out + "\n", "")


@pytest.fixture
def controller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[stack.FixtureStack, Daemon]:
    daemon = Daemon()
    monkeypatch.setattr(stack, "capture", daemon.capture)
    monkeypatch.setattr(stack, "executable", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        os, "statvfs", lambda path: SimpleNamespace(f_bavail=10 * 1024**3, f_frsize=1)
    )
    control = stack.FixtureStack(tmp_path)
    daemon.project, daemon.run_id = control.project, control.run_id
    return control, daemon


@pytest.mark.parametrize("fault", ["", "external", "owner", "attachment", "network_id", "stopped"])
def test_runtime_topology_requires_owned_internal_networks_and_exact_attachments(
    controller: tuple[stack.FixtureStack, Daemon], monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    control, _ = controller
    front, back = control.project + "_front", control.project + "_back"

    def command(*args: str) -> str:
        if args[:2] == ("network", "ls"):
            return front + "\n" + back
        if args[:2] == ("network", "inspect"):
            return json.dumps(
                {
                    "name": args[2],
                    "internal": fault != "external",
                    "run": "foreign" if fault == "owner" else control.run_id,
                    "id": ("a" if args[2] == front else "b") * 64,
                }
            )
        role = args[1]
        names = (
            (front, back)
            if role == "gateway"
            else (back,)
            if role in {"origin", "bad"}
            else (front,)
        )
        if fault == "attachment":
            names = (*names, "external")
        return json.dumps(
            {
                "role": role,
                "run": control.run_id,
                "running": fault != "stopped",
                "networks": {
                    name: {
                        "NetworkID": (
                            "c" if fault == "network_id" else "a" if name == front else "b"
                        )
                        * 64
                    }
                    for name in names
                },
            }
        )

    monkeypatch.setattr(control, "command", command)
    monkeypatch.setattr(control, "compose", lambda *args: args[-1])
    if fault:
        with pytest.raises(stack.StackError, match="fixture_topology"):
            control.verify_topology()
    else:
        control.verify_topology()


def test_owned_stack_prepares_verifies_and_removes_only_its_resources(
    controller: tuple[stack.FixtureStack, Daemon],
) -> None:
    control, daemon = controller
    control.prepare()
    assert len(control.images) == 3
    assert control.env_file.stat().st_mode & 0o777 == 0o600
    control.start()
    assert control.created
    control.cleanup()
    assert control.cleaned and not control.env_file.exists()
    assert any(row[:2] == ("rm", "--force") for row in daemon.calls)
    assert all("prune" not in row and "down" not in row for row in daemon.calls)


def test_failed_probe_capture_remains_private_in_exception_text(
    controller: tuple[stack.FixtureStack, Daemon], monkeypatch: pytest.MonkeyPatch
) -> None:
    control, _ = controller
    result = CommandResult(1, "private-sentinel", "private-sentinel")
    monkeypatch.setattr(stack, "capture", lambda *args, **kwargs: result)
    with pytest.raises(stack.ProbeCommandError) as error:
        control.command("test", exact=True)
    assert error.value.result is result
    assert "private-sentinel" not in repr(error.value) + str(error.value) + repr(result)


def test_bad_ownership_prevents_every_deletion(
    controller: tuple[stack.FixtureStack, Daemon],
) -> None:
    control, daemon = controller
    control.prepare()
    control.start()
    daemon.owner = "another-run"
    daemon.calls.clear()
    with pytest.raises(stack.StackError, match="ownership"):
        control.cleanup()
    assert not control.cleaned
    assert not any("rm" in row or row[0] == "stop" for row in daemon.calls)


@pytest.mark.parametrize(
    "routes",
    [
        [{"dst": "172.30.240.0/24"}],
        [{"dst": "172.30.0.0/16"}],
        {"bad": "private-sentinel"},
        [{"dst": "nonsense"}],
    ],
)
def test_conflicting_or_invalid_host_routes_fail_before_creation(
    controller: tuple[stack.FixtureStack, Daemon], routes: object
) -> None:
    control, daemon = controller
    daemon.routes = routes
    with pytest.raises(stack.StackError):
        control.prepare()
    assert not control.created and not daemon.resources
    control.cleanup()
    assert control.cleaned


@pytest.mark.parametrize("fault", ["image", "network", "policy"])
def test_startup_failures_do_not_create_verified_state(
    controller: tuple[stack.FixtureStack, Daemon], fault: str
) -> None:
    control, daemon = controller
    if fault == "image":
        daemon.image = "unverified"
        with pytest.raises(stack.StackError):
            control.prepare()
        assert not control.created
    else:
        control.prepare()
        if fault == "network":
            daemon.internal = "false"
        else:
            daemon.policy = "invalid"
        with pytest.raises(stack.StackError):
            control.start()
        assert control.created
        control.cleanup()
        assert control.cleaned


def test_work_deadline_reserves_cleanup_time(
    controller: tuple[stack.FixtureStack, Daemon],
) -> None:
    control, daemon = controller
    control.prepare()
    control.start()
    control.deadline = time.monotonic() + 50
    with pytest.raises(stack.StackError, match="deadline"):
        control.command("info")
    control.cleanup()
    assert control.cleaned


def test_nonzero_command_does_not_expose_output(
    monkeypatch: pytest.MonkeyPatch, controller: tuple[stack.FixtureStack, Daemon]
) -> None:
    control, _ = controller
    monkeypatch.setattr(
        stack,
        "capture",
        Mock(return_value=CommandResult(1, "private-sentinel", "password-sentinel")),
    )
    with pytest.raises(stack.StackError, match="^fixture_command$"):
        control.command("info")


def test_prepare_failure_cleanup_never_queries_or_mutates_docker(
    controller: tuple[stack.FixtureStack, Daemon],
) -> None:
    control, daemon = controller
    control.cleanup()
    assert daemon.calls == [] and control.cleaned


@pytest.mark.parametrize("fault", ["duplicate", "unknown_volume", "foreign_volume", "remaining"])
def test_all_resource_classes_are_checked_before_any_delete(
    monkeypatch: pytest.MonkeyPatch,
    controller: tuple[stack.FixtureStack, Daemon],
    fault: str,
) -> None:
    control, daemon = controller
    control.prepare()
    control.start()
    original = daemon.capture

    def changed(argv: tuple[str, ...], **kwargs: object) -> CommandResult:
        result = original(argv, **kwargs)
        args = argv[2:]
        if args[:2] == ("volume", "ls"):
            if fault == "duplicate":
                return CommandResult(0, result.stdout * 2, "")
            if fault == "unknown_volume":
                return CommandResult(0, control.project + "_unknown\n", "")
        if args[:2] == ("volume", "inspect") and fault == "foreign_volume":
            return CommandResult(0, json.dumps({"run": "foreign", "project": control.project}), "")
        if args[:2] == ("volume", "rm") and fault == "remaining":
            daemon.resources = True
        return result

    monkeypatch.setattr(stack, "capture", changed)
    daemon.calls.clear()
    with pytest.raises(stack.StackError):
        control.cleanup()
    assert not control.cleaned
    if fault != "remaining":
        assert not any("rm" in row or row[0] == "stop" for row in daemon.calls)


@pytest.mark.parametrize(
    "fault", ["info", "ipam_shape", "ipam_entry", "ipam_overlap", "json", "large"]
)
def test_malformed_daemon_observations_never_start_workloads(
    monkeypatch: pytest.MonkeyPatch,
    controller: tuple[stack.FixtureStack, Daemon],
    fault: str,
) -> None:
    control, daemon = controller
    original = daemon.capture

    def changed(argv: tuple[str, ...], **kwargs: object) -> CommandResult:
        result = original(argv, **kwargs)
        args = argv[2:]
        if args[:2] == ("network", "ls"):
            return CommandResult(0, "b" * 64, "")
        if args[:2] == ("network", "inspect"):
            out = {
                "ipam_shape": "{}",
                "ipam_entry": "[1]",
                "ipam_overlap": '[{"Subnet":"172.30.241.0/24"}]',
            }.get(fault, "[]")
            return CommandResult(0, out, "")
        if args[0] == "info":
            info_output = {"info": "{}", "json": "invalid", "large": "x" * 65537}.get(fault)
            if info_output is not None:
                return CommandResult(0, info_output, "")
        return result

    monkeypatch.setattr(stack, "capture", changed)
    with pytest.raises(stack.StackError):
        control.prepare()
    assert not control.created


def test_partial_startup_still_has_owned_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    controller: tuple[stack.FixtureStack, Daemon],
) -> None:
    control, daemon = controller
    control.prepare()
    original = daemon.capture

    def failed(argv: tuple[str, ...], **kwargs: object) -> CommandResult:
        result = original(argv, **kwargs)
        return CommandResult(1, "private-sentinel", "") if "up" in argv else result

    monkeypatch.setattr(stack, "capture", failed)
    with pytest.raises(stack.StackError, match="fixture_command"):
        control.start()
    assert control.created
    control.cleanup()
    assert control.cleaned


def test_cleanup_expiry_cannot_become_success(
    controller: tuple[stack.FixtureStack, Daemon],
) -> None:
    control, _ = controller
    control.deadline = time.monotonic() - 1
    with pytest.raises(stack.StackError, match="deadline"):
        control.cleanup()
    assert not control.cleaned


def test_tool_discovery_is_closed_and_missing_tools_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use the original implementation; the controller fixture normally substitutes it.
    monkeypatch.setattr(Path, "is_file", lambda path: str(path) == "/usr/bin/ip")
    assert stack.executable("ip") == "/usr/bin/ip"
    with pytest.raises(stack.StackError):
        stack.executable("docker")
    with pytest.raises(stack.StackError):
        stack.executable("arbitrary-private-command")
