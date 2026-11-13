"""Prerequisite decisions are not successful collection/isolation receipts."""

import json
from pathlib import Path

import pytest

from nima.egress.preflight import (
    PrerequisiteError,
    check_host,
    check_namespaces,
    check_process,
    check_sandbox,
    classify_browser_failure,
    main,
)


def status(**changes: str) -> str:
    values = {
        "Uid": "10001\t10001\t10001\t10001",
        "CapEff": "0000000000000000",
        "CapPrm": "0000000000000000",
        "CapBnd": "0000000000000000",
        "NoNewPrivs": "1",
        "Seccomp": "2",
        **changes,
    }
    return "\n".join(f"{k}:\t{v}" for k, v in values.items())


def test_accepts_only_supported_host_and_sufficient_disk() -> None:
    check_host({"OSType": "linux", "Architecture": "x86_64"}, 8 * 1024**3)
    with pytest.raises(PrerequisiteError, match="^disk$"):
        check_host({"OSType": "linux", "Architecture": "amd64"}, 8 * 1024**3 - 1)
    for value in (
        {},
        {"OSType": "windows", "Architecture": "amd64"},
        {"OSType": "linux", "Architecture": "aarch64"},
    ):
        with pytest.raises(PrerequisiteError, match="^platform$"):
            check_host(value, 20 * 1024**3)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Uid", "0\t0\t0\t0"),
        ("Uid", "10001\t0\t10001\t10001"),
        ("CapEff", "1000"),
        ("CapPrm", "1000"),
        ("CapBnd", "1000"),
        ("NoNewPrivs", "0"),
        ("Seccomp", "0"),
        ("CapEff", "invalid-secret-value"),
    ],
)
def test_rejects_privileged_or_ambiguous_workload(field: str, value: str) -> None:
    with pytest.raises(PrerequisiteError, match="^process$"):
        check_process(status(**{field: value}))


def test_process_and_sandbox_need_actual_complete_observations() -> None:
    check_process(status())
    with pytest.raises(PrerequisiteError):
        check_process("")
    for page in (
        "",
        "Seccomp-BPF sandbox Yes",
        "PID namespaces No\nNetwork namespaces Yes\nSeccomp-BPF sandbox Yes",
    ):
        with pytest.raises(PrerequisiteError, match="^sandbox$"):
            check_sandbox(page)
    check_sandbox("PID namespaces\tYes\nNetwork namespaces\tYes\nSeccomp-BPF sandbox\tYes")


def test_seccomp_is_the_exact_reviewed_profile() -> None:
    import hashlib

    root = Path("infra/source-worker")
    pins = json.loads((root / "pins.json").read_bytes())
    assert (
        hashlib.sha256((root / "seccomp.json").read_bytes()).hexdigest()
        == pins["seccomp"]["sha256"]
    )
    assert "Apache License" in (root / "LICENSE.seccomp").read_text()


def test_host_receipt_does_not_attest_privacy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "info.json"
    path.write_text('{"OSType":"linux","Architecture":"amd64"}')
    assert main(["host", "--info-file", str(path), "--free-bytes", str(8 * 1024**3)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "passed"
    assert receipt["scope"] == "prerequisites"
    assert receipt["investigator_ip_protection_verified"] is False
    assert receipt["internet_egress_verified"] is False
    assert receipt["production_ready"] is False
    assert main(["host", "--info-file", str(path), "--free-bytes", "1"]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "disk"


def test_raw_arguments_and_browser_exceptions_are_not_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--private-value-secret"]) == 2
    assert "secret" not in capsys.readouterr().out

    def fail() -> None:
        raise RuntimeError("private-path-and-credentials")

    monkeypatch.setattr("nima.egress.preflight.browser_check", fail)
    assert main(["browser"]) == 1
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out)["failure"] == "observation_unavailable"
    assert "private" not in output.out


def test_helper_has_only_network_admin_in_the_target_namespace() -> None:
    helper = status(Uid="0\t0\t0\t0", CapEff="1000", CapPrm="1000", CapBnd="1000")
    check_process(helper, helper=True)
    with pytest.raises(PrerequisiteError, match="^process$"):
        check_process(status(), helper=True)


@pytest.mark.parametrize(
    ("message", "code"),
    [
        (
            "private: Failed to move to new namespace: Operation not permitted",
            "browser_namespace_denied",
        ),
        ("private: No usable sandbox!", "browser_sandbox_unavailable"),
        ("BrowserType.launch: Chromium sandboxing failed! private", "browser_sandbox_unavailable"),
        ("Page.goto: net::ERR_INVALID_URL at private", "browser_navigation_failed"),
        ("private: Executable doesn't exist at /private/path", "browser_binary_missing"),
        ("BrowserType.launch: executable doesn't exist at /private/path", "browser_binary_missing"),
        ("BrowserType.launch: spawn /private/path ENOENT", "browser_binary_missing"),
        ("private: error while loading shared libraries: secret.so", "browser_library_missing"),
        ("private unknown diagnostics", "browser_operation_failed"),
    ],
)
def test_browser_failure_codes_never_echo_diagnostics(message: str, code: str) -> None:
    assert classify_browser_failure(message) == code


def test_namespace_failure_in_child_is_a_failed_prerequisite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_chroot(path: str) -> None:
        raise PermissionError

    monkeypatch.setattr("os.chroot", deny_chroot)
    monkeypatch.setattr("os.fork", lambda: 123)
    monkeypatch.setattr("os.waitpid", lambda pid, flags: (123, 256))
    with pytest.raises(PrerequisiteError, match="^user_namespaces$"):
        check_namespaces()


def test_runtime_profile_changes_only_the_child_namespace_chroot_rule() -> None:
    import hashlib

    from nima.egress.seccomp import build_profile

    root = Path("infra/source-worker")
    upstream = (root / "seccomp.json").read_bytes()
    original = json.loads(upstream)
    raw = build_profile(upstream)
    derived = json.loads(raw)
    extra = derived["syscalls"].pop()
    assert derived == original
    assert extra["names"] == ["chroot"]
    assert extra["action"] == "SCMP_ACT_ALLOW"
    assert extra["args"] == []
    assert extra["includes"] == extra["excludes"] == {}
    pins = json.loads((root / "pins.json").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == pins["seccomp"]["runtime_sha256"]
    with pytest.raises(ValueError, match="^profile_identity$"):
        build_profile(upstream + b" ")


def test_parent_chroot_privilege_is_never_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.chroot", lambda path: None)
    monkeypatch.setattr("os.fork", lambda: 123)
    monkeypatch.setattr("os.waitpid", lambda pid, flags: (123, 0))
    with pytest.raises(PrerequisiteError, match="^unexpected_chroot$"):
        check_namespaces()
