"""Observed runtime snapshots fail closed without exposing kernel diagnostics."""

import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nima.egress import runtime
from nima.egress.runtime import ProcessState


@pytest.mark.parametrize("role", ["observer", "gateway"])
def test_snapshot_reads_process_and_gateway_forwarding(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    state = ProcessState(10002, 0, 0, 0, 1, 2, True, 123)
    process = Mock(return_value=state)
    kernel_read = Mock(return_value="0\n")
    monkeypatch.setattr(runtime, "observe_process", process)
    monkeypatch.setattr(runtime, "Path", lambda name: SimpleNamespace(read_text=kernel_read))
    value = runtime.snapshot(role)
    process.assert_called_once_with(uid=10002)
    assert value == {
        "version": "source-worker-runtime-v1",
        "role": role,
        "process": asdict(state),
        "gateway_forwarding_disabled": True if role == "gateway" else None,
    }
    assert kernel_read.call_count == int(role == "gateway")


@pytest.mark.parametrize("forwarding", ["1\n", "0", "private-sentinel", "0\n0\n"])
def test_gateway_forwarding_must_be_observed_disabled(
    monkeypatch: pytest.MonkeyPatch, forwarding: str
) -> None:
    monkeypatch.setattr(runtime, "observe_process", Mock())
    monkeypatch.setattr(runtime, "Path", lambda name: SimpleNamespace(read_text=lambda: forwarding))
    with pytest.raises(ValueError, match="runtime_forwarding"):
        runtime.snapshot("gateway")


@pytest.mark.parametrize("args", [[], ["worker"], ["gateway", "observer"], ["private-sentinel"]])
def test_snapshot_cli_rejects_configuration_before_io(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    observe = Mock()
    monkeypatch.setattr(runtime, "observe_process", observe)
    assert runtime.main(args) == 2
    observe.assert_not_called()
    assert "private-sentinel" not in capsys.readouterr().out


@pytest.mark.parametrize("failure", [None, ValueError("private-sentinel"), KeyboardInterrupt()])
def test_runtime_cli_emits_only_structured_result_or_fixed_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: BaseException | None,
) -> None:
    value = {"version": "source-worker-runtime-v1", "role": "observer"}
    monkeypatch.setattr(runtime, "snapshot", Mock(return_value=value, side_effect=failure))
    assert runtime.main(["observer"]) == (
        0 if failure is None else 130 if isinstance(failure, KeyboardInterrupt) else 1
    )
    raw = capsys.readouterr().out
    assert "private-sentinel" not in raw
    if failure is None:
        assert json.loads(raw) == value
    else:
        assert json.loads(raw)["status"] == "failed"


def test_unknown_snapshot_role_rejected_without_reading_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = Mock()
    monkeypatch.setattr(runtime, "observe_process", observe)
    with pytest.raises(ValueError, match="configuration"):
        runtime.snapshot("private-sentinel")
    observe.assert_not_called()


@pytest.mark.parametrize("failed", [False, True])
def test_privilege_evidence_requires_actual_probe_completion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failed: bool
) -> None:
    from nima.egress import probe_network

    state = ProcessState(10001, 0, 0, 0, 1, 2, True, 123)
    probe = Mock(side_effect=ValueError("private-sentinel") if failed else None)
    observe = Mock(return_value=state)
    controls = Mock()
    monkeypatch.setattr(probe_network, "probe", probe)
    monkeypatch.setattr(probe_network, "observe_process", observe)
    monkeypatch.setattr(probe_network, "private_controls", controls)
    assert probe_network.main(["evidence"]) == int(failed)
    value = json.loads(capsys.readouterr().out)
    probe.assert_called_once_with()
    if failed:
        observe.assert_not_called()
        assert "process" not in value and value["status"] == "failed"
    else:
        observe.assert_called_once_with()
        controls.assert_called_once_with()
        assert value == {
            "version": "source-worker-privileges-v1",
            "process": asdict(state),
            "observer_uid_denied": True,
            "parent_net_admin_denied": True,
            "controls_unreachable": True,
        }
