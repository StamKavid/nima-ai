"""Browser configuration/classification tests; Docker counters prove real delivery."""

import json
import os
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from playwright.sync_api import Error as BrowserError

from nima.egress import probe_browser
from nima.egress.bootstrap import credentials
from nima.egress.preflight import CHROMIUM
from nima.egress.receipt import ClientResult
from nima.egress.runtime import ProcessState, validate_process


@pytest.fixture
def process() -> ProcessState:
    return ProcessState(10001, 0, 0, 0, 1, 2, True, 123)


@pytest.mark.parametrize("fault", ["uid", "cap", "seccomp", "readonly", "namespace"])
def test_process_evidence_cannot_be_configuration_claims(process: ProcessState, fault: str) -> None:
    value = {
        "uid": replace(process, uid=10002),
        "cap": replace(process, cap_effective=1),
        "seccomp": replace(process, seccomp=0),
        "readonly": replace(process, root_readonly=False),
        "namespace": replace(process, network_inode=True),
    }[fault]
    with pytest.raises(ValueError):
        validate_process(value, uid=10001)


@pytest.mark.parametrize("case", [row.name for row in probe_browser.BROWSER_CASES])
def test_browser_cases_keep_sandbox_tls_and_fixed_destinations(
    monkeypatch: pytest.MonkeyPatch, process: ProcessState, case: str
) -> None:
    auth = credentials("fixture-user-" + "u" * 16, "p" * 43)
    browser, page, context = Mock(), Mock(), MagicMock()
    context.__enter__.return_value = context
    browser.version = CHROMIUM
    browser.new_context.return_value = context
    context.new_page.return_value = page
    page.locator.return_value.inner_text.return_value = (
        "PID namespaces Yes Network namespaces Yes Seccomp-BPF sandbox Yes Nima fixture"
    )
    page.content.return_value = "Nima fixture"
    page.evaluate.return_value = "gathering"

    def goto(url: str, **kwargs: object) -> object:
        if url == "chrome://sandbox" or url.startswith("data:"):
            return None
        if case == "browser_resources":
            return SimpleNamespace(status=200)
        if case in {"browser_redirect_host", "browser_invalid_auth"}:
            raise BrowserError("net::ERR_HTTP_RESPONSE_CODE_FAILURE private-sentinel")
        if case == "browser_invalid_tls":
            raise BrowserError("net::ERR_CERT_AUTHORITY_INVALID private-sentinel")
        if case == "browser_gateway_outage":
            raise BrowserError("net::ERR_PROXY_CONNECTION_FAILED private-sentinel")
        raise BrowserError("net::ERR_CONNECTION_TIMED_OUT private-sentinel")

    page.goto.side_effect = goto
    engine = SimpleNamespace(chromium=Mock())
    engine.chromium.launch.return_value = browser

    @contextmanager
    def playwright() -> Iterator[SimpleNamespace]:
        yield engine

    monkeypatch.setattr(probe_browser, "sync_playwright", playwright)
    monkeypatch.setattr(probe_browser, "observe_process", Mock(return_value=process))
    monkeypatch.setattr(probe_browser, "private_controls", Mock())
    monkeypatch.setattr(probe_browser, "require_metadata_alias", Mock())
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: b"nameserver 172.30.240.4\noptions ndots:0 timeout:1 attempts:1\n",
    )
    result = probe_browser.execute(case, auth)
    assert result.process == process and result.chromium == CHROMIUM
    assert result.sandbox_pid and result.sandbox_network and result.sandbox_seccomp
    launch = engine.chromium.launch.call_args.kwargs
    assert launch["chromium_sandbox"] is True and launch["channel"] == "chromium"
    assert not any("no-sandbox" in arg or "ignore-certificate" in arg for arg in launch["args"])
    assert context.__exit__.called and browser.close.called
    options = browser.new_context.call_args.kwargs
    assert options.get("ignore_https_errors", False) is False
    if case == "browser_proxy_bypass":
        assert options["proxy"]["bypass"] == "172.30.240.4"
    if case == "browser_quic":
        assert "--origin-to-force-quic-on=172.30.240.4:443" in launch["args"]
    if case == "browser_stun":
        assert "stun:172.30.240.4:3478" in page.evaluate.call_args.args[0]
        assert result.client_result == ClientResult.ATTEMPTED
    raw = probe_browser.encode_result(case, result)
    assert "private-sentinel" not in raw.decode() and auth.password not in raw.decode()
    assert probe_browser.read_result(raw, case) == result


def test_unknown_case_is_rejected_before_browser_or_process_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = Mock()
    monkeypatch.setattr(probe_browser, "observe_process", observe)
    with pytest.raises(probe_browser.BrowserProbeError):
        probe_browser.execute(
            "https://private-sentinel.test", credentials("fixture-user-" + "u" * 16, "p" * 43)
        )
    observe.assert_not_called()


@pytest.mark.parametrize(
    "fault", ["extra", "case", "sandbox", "process", "version", "duplicate", "limit"]
)
def test_browser_wire_result_rejects_forged_runtime(process: ProcessState, fault: str) -> None:
    result = probe_browser.BrowserResult(
        ClientResult.FIXTURE_BODY, CHROMIUM, process, True, True, True, True
    )
    raw = probe_browser.encode_result("browser_resources", result)
    body = json.loads(raw)
    if fault == "extra":
        body["secret"] = "private-sentinel"
    elif fault == "case":
        body["case_name"] = "browser_quic"
    elif fault == "sandbox":
        body["observation"]["sandbox_pid"] = False
    elif fault == "process":
        body["observation"]["process"]["cap_bounding"] = 1
    elif fault == "version":
        body["observation"]["chromium"] = "wrong"
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if fault == "duplicate":
        raw = raw.replace(b"{", b'{"case_name":"browser_resources",', 1)
    elif fault == "limit":
        raw = b"x" * 4097
    with pytest.raises(probe_browser.BrowserProbeError):
        probe_browser.read_result(raw, "browser_resources")


@pytest.mark.parametrize(
    "case,error",
    [
        ("browser_invalid_tls", "net::ERR_CONNECTION_TIMED_OUT"),
        ("browser_invalid_auth", "net::ERR_PROXY_CONNECTION_FAILED"),
        ("browser_redirect_host", "Target page has been closed"),
        ("browser_gateway_outage", "net::ERR_CERT_AUTHORITY_INVALID"),
        ("browser_resources", "net::ERR_CONNECTION_TIMED_OUT"),
        ("browser_dns", "JavaScript exception"),
    ],
)
def test_unrelated_browser_failures_do_not_count_as_expected_denial(case: str, error: str) -> None:
    with pytest.raises(probe_browser.BrowserProbeError):
        probe_browser._failure(case, BrowserError(error + " private-sentinel"))


@pytest.mark.parametrize(
    "marker,code",
    [
        ("ERR_QUIC_HANDSHAKE_FAILED", "browser_quic_handshake"),
        ("ERR_QUIC_GOAWAY_REQUEST_CAN_BE_RETRIED", "browser_quic_disabled"),
    ],
)
def test_quic_diagnostic_classification_never_exposes_driver_text(marker: str, code: str) -> None:
    with pytest.raises(probe_browser.BrowserProbeError, match=code) as error:
        probe_browser._failure("browser_quic", BrowserError(marker + " private-sentinel"))
    assert "private-sentinel" not in str(error.value)


@pytest.mark.parametrize("fault", ["none", "configuration", "driver", "interrupt"])
def test_cli_redacts_errors_and_restores_alarm(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    process: ProcessState,
    fault: str,
) -> None:
    monkeypatch.setenv("NIMA_FIXTURE_USERNAME", "fixture-user-" + "u" * 16)
    monkeypatch.setenv("NIMA_FIXTURE_PASSWORD", "p" * 43)
    timers: list[float] = []
    monkeypatch.setattr(signal, "signal", Mock(return_value=signal.SIG_DFL))
    monkeypatch.setattr(signal, "setitimer", lambda which, value: timers.append(value))
    probe = Mock(
        return_value=probe_browser.BrowserResult(
            ClientResult.FIXTURE_BODY, CHROMIUM, process, True, True, True, True
        )
    )
    if fault == "driver":
        probe.side_effect = BrowserError("private-sentinel")
    elif fault == "interrupt":
        probe.side_effect = KeyboardInterrupt()
    monkeypatch.setattr(probe_browser, "execute", probe)
    result = probe_browser.main(
        ["private-sentinel"] if fault == "configuration" else ["browser_resources"]
    )
    raw = capsys.readouterr().out
    assert "private-sentinel" not in raw and "p" * 43 not in raw
    assert result == {"none": 0, "configuration": 2, "driver": 1, "interrupt": 130}[fault]
    assert timers == ([] if fault == "configuration" else [15, 0])


def test_expired_browser_worker_cannot_hang_in_driver_cleanup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Exited(BaseException):
        pass

    exit_call = Mock(side_effect=Exited)
    monkeypatch.setattr(os, "_exit", exit_call)
    with pytest.raises(Exited):
        probe_browser._expired(signal.SIGALRM, None)
    exit_call.assert_called_once_with(1)
    assert json.loads(capsys.readouterr().out)["failure"] == "browser_attempt_deadline"


@pytest.mark.parametrize("uid,readonly", [(10001, True), (10002, True), (10001, False)])
def test_process_snapshot_is_read_from_kernel_observations(
    monkeypatch: pytest.MonkeyPatch, uid: int, readonly: bool
) -> None:
    from nima.egress import runtime

    raw = (
        f"Uid:\t{uid} {uid} {uid} {uid}\nCapEff:\t0\nCapPrm:\t0\n"
        "CapBnd:\t0\nNoNewPrivs:\t1\nSeccomp:\t2\n"
    )
    monkeypatch.setattr(
        runtime,
        "Path",
        lambda name: SimpleNamespace(
            read_text=lambda: raw, stat=lambda: SimpleNamespace(st_ino=456)
        ),
    )
    monkeypatch.setattr(
        os, "statvfs", lambda name: SimpleNamespace(f_flag=os.ST_RDONLY if readonly else 0)
    )
    if readonly:
        state = runtime.observe_process(uid=uid)
        assert state.uid == uid and state.network_inode == 456 and state.root_readonly
    else:
        with pytest.raises(ValueError):
            runtime.observe_process(uid=uid)
