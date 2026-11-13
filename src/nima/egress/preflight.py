"""Fail closed on unsupported prerequisites; never attest deployed privacy.

https://playwright.dev/python/docs/docker
https://playwright.dev/python/docs/browsers#chromium-new-headless-mode
"""

import argparse
import json
import os
import re
import socket
from importlib.metadata import version
from pathlib import Path
from typing import Never

from nima.egress.seccomp import build_profile

MIN_FREE_BYTES = 8 * 1024**3
PLAYWRIGHT = "1.65.1"
CHROMIUM = "158.0.8127.18"


class PrerequisiteError(ValueError):
    """A fixed code without raw configuration, paths or browser diagnostics."""


def check_host(info: object, free_bytes: int) -> None:
    if (
        not isinstance(info, dict)
        or info.get("OSType") != "linux"
        or info.get("Architecture") not in ("amd64", "x86_64")
    ):
        raise PrerequisiteError("platform")
    if type(free_bytes) is not int or free_bytes < MIN_FREE_BYTES:
        raise PrerequisiteError("disk")


def check_process(status: str, *, helper: bool = False) -> None:
    required = {"Uid", "CapEff", "CapPrm", "CapBnd", "NoNewPrivs", "Seccomp"}
    observed = {}
    for line in status.splitlines():
        name, _, value = line.partition(":")
        if name in required:
            if name in observed:
                raise PrerequisiteError("process")
            observed[name] = value.strip()
    try:
        if (
            set(observed) != required
            or observed["Uid"].split() != (["0"] if helper else ["10001"]) * 4
            or any(
                int(observed[name], 16) != (0x1000 if helper else 0)
                for name in ("CapEff", "CapPrm", "CapBnd")
            )
            or observed["NoNewPrivs"] != "1"
            or observed["Seccomp"] != "2"
        ):
            raise ValueError
    except ValueError:
        raise PrerequisiteError("process") from None


def check_sandbox(page: str) -> None:
    for label in ("PID namespaces", "Network namespaces", "Seccomp-BPF sandbox"):
        if re.search(re.escape(label) + r"\s+Yes\b", page) is None:
            raise PrerequisiteError("sandbox")


def check_socket_mark(*, helper: bool) -> None:
    """Exercise NET_ADMIN without sending any packet or changing host policy."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, 1)
        except PermissionError:
            if helper:
                raise PrerequisiteError("network_admin") from None
        else:
            if not helper:
                raise PrerequisiteError("unexpected_network_admin")


def helper_check() -> None:
    check_process(Path("/proc/self/status").read_text(), helper=True)
    check_socket_mark(helper=True)


def check_namespaces() -> None:
    """Probe sandbox primitives in a child; never change the controller namespace."""
    try:
        os.chroot("/")
    except PermissionError:
        pass
    else:
        raise PrerequisiteError("unexpected_chroot")
    child = os.fork()
    if child == 0:
        try:
            os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNET | os.CLONE_NEWPID)
            os.chroot("/proc/self/fdinfo/")
        except OSError:
            os._exit(1)
        os._exit(0)
    _, status = os.waitpid(child, 0)
    if status != 0:
        raise PrerequisiteError("user_namespaces")


def namespaces_check() -> None:
    check_process(Path("/proc/self/status").read_text())
    check_socket_mark(helper=False)
    check_namespaces()


def classify_browser_failure(message: str) -> str:
    """Extract only fixed known signals; never publish driver output."""
    for marker, code in (
        ("Failed to move to new namespace", "browser_namespace_denied"),
        ("sys_chroot", "browser_sandbox_chroot"),
        ("Failed to unshare", "browser_namespace_denied"),
        ("No usable sandbox!", "browser_sandbox_unavailable"),
        ("Chromium sandboxing failed!", "browser_sandbox_unavailable"),
        ("Executable doesn't exist", "browser_binary_missing"),
        ("ENOENT", "browser_binary_missing"),
        ("error while loading shared libraries", "browser_library_missing"),
        ("SUID sandbox helper binary", "browser_setuid_sandbox_unavailable"),
        ("setuid sandbox is not running as root", "browser_setuid_sandbox_unavailable"),
        ("Missing X server", "browser_display_unavailable"),
        ("without having a XServer", "browser_display_unavailable"),
        ("ProcessSingleton", "browser_profile_unavailable"),
        ("Read-only file system", "browser_readonly_failure"),
        ("No space left on device", "browser_disk_unavailable"),
        ("Cannot allocate memory", "browser_memory_unavailable"),
        ("EACCES", "browser_permission_denied"),
        ("pthread_create", "browser_thread_unavailable"),
        ("chrome_crashpad_handler: --database is required", "browser_crashpad_database"),
        ("Resource temporarily unavailable", "browser_resource_unavailable"),
        ("Operation not permitted", "browser_operation_denied"),
        ("Permission denied", "browser_permission_denied"),
        ("signal=SIGSYS", "browser_syscall_signal"),
        ("signal=SIGTRAP", "browser_trap_signal"),
    ):
        if marker.casefold() in message.casefold():
            return code
    for prefix, code in (
        ("BrowserType.launch:", "browser_launch_failed"),
        ("Page.goto:", "browser_navigation_failed"),
        ("Locator.inner_text:", "browser_content_failed"),
        ("Browser.close:", "browser_close_failed"),
    ):
        if message.startswith(prefix):
            return code
    return "browser_operation_failed"


def browser_check() -> None:
    from playwright.sync_api import Error

    try:
        _check_browser()
    except Error as exc:
        raise PrerequisiteError(classify_browser_failure(str(exc))) from None


def _check_browser() -> None:
    from playwright.sync_api import sync_playwright

    check_process(Path("/proc/self/status").read_text())
    check_socket_mark(helper=False)
    if version("playwright") != PLAYWRIGHT:
        raise PrerequisiteError("package_version")
    with sync_playwright() as client:
        executable = Path(client.chromium.executable_path)
        if not executable.is_file():
            raise PrerequisiteError("browser_binary_missing")
        if not os.access(executable, os.X_OK):
            raise PrerequisiteError("browser_binary_not_executable")
        browser = client.chromium.launch(
            channel="chromium",
            headless=True,
            chromium_sandbox=True,
            args=["--disable-background-networking", "--no-first-run"],
            timeout=15000,
        )
        try:
            if browser.version != CHROMIUM:
                raise PrerequisiteError("browser_version")
            page = browser.new_page()
            page.goto("chrome://sandbox", wait_until="domcontentloaded", timeout=15000)
            check_sandbox(page.locator("body").inner_text())
            page.goto("data:text/html,<p>Nima fixture</p>", timeout=15000)
            if page.locator("body").inner_text() != "Nima fixture":
                raise PrerequisiteError("browser_page")
        finally:
            browser.close()


def report(status: str, failure: str | None = None) -> None:
    print(
        json.dumps(
            {
                "version": "source-worker-preflight-v1",
                "scope": "prerequisites",
                "status": status,
                "failure": failure,
                "investigator_ip_protection_verified": False,
                "internet_egress_verified": False,
                "production_ready": False,
            }
        )
    )


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        report("failed", "configuration")
        self.exit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser()
    modes = parser.add_subparsers(dest="mode", required=True)
    host = modes.add_parser("host")
    host.add_argument("--info-file", type=Path, required=True)
    host.add_argument("--free-bytes", type=int, required=True)
    modes.add_parser("browser")
    modes.add_parser("helper")
    modes.add_parser("namespaces")
    profile = modes.add_parser("profile")
    profile.add_argument("--output", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        if args.mode == "profile":
            raw = build_profile(Path("infra/source-worker/seccomp.json").read_bytes())
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
        elif args.mode == "host":
            with args.info_file.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise PrerequisiteError("configuration")
            check_host(json.loads(raw), args.free_bytes)
        elif args.mode == "helper":
            helper_check()
        elif args.mode == "namespaces":
            namespaces_check()
        else:
            browser_check()
    except PrerequisiteError as exc:
        report("failed", str(exc))
        return 1
    except KeyboardInterrupt:
        report("failed", "interrupted")
        return 130
    except Exception:
        # Chromium/driver exceptions may embed local paths, flags or configuration.
        report("failed", "observation_unavailable")
        return 1
    report("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
