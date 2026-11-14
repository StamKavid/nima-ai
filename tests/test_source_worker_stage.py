"""A passing HTTP stage must never become a passing full isolation receipt."""

import json
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from nima.egress.policy import CaseKind
from nima.egress.probe_http import HTTP_CASES
from nima.egress.receipt import CaseEvidence, ClientResult, ReceiptError, read_receipt
from nima.egress.stage import HttpStage, StageError, encode_stage, publish_stage, read_stage


@pytest.fixture
def stage() -> HttpStage:
    rows = []
    for case in HTTP_CASES:
        kind = case.kind
        result = {
            CaseKind.ALLOWED: ClientResult.FIXTURE_BODY,
            CaseKind.RESTARTED: ClientResult.FIXTURE_BODY,
            CaseKind.PACKET_BLOCKED: ClientResult.NETWORK_FAILURE,
            CaseKind.GATEWAY_REJECTED: ClientResult.PROXY_REJECTED,
            CaseKind.TLS_REJECTED: ClientResult.CERTIFICATE_REJECTED,
            CaseKind.GATEWAY_OUTAGE: ClientResult.NETWORK_FAILURE,
            CaseKind.IPV6_DISABLED: ClientResult.IPV6_UNAVAILABLE,
        }[kind]
        rows.append(
            CaseEvidence(
                case.name,
                case.target_counter,
                result,
                control_success=None if kind == CaseKind.IPV6_DISABLED else True,
                target_deliveries=1 if kind in {CaseKind.ALLOWED, CaseKind.RESTARTED} else 0,
                gateway_tunnels=1,
                gateway_rejections=1,
                policy_drops=1,
                observed_routes=frozenset({"html"}),
                headers_clean=True,
                gateway_stopped=kind == CaseKind.GATEWAY_OUTAGE,
                gateway_restarted=kind == CaseKind.RESTARTED,
            )
        )
    now = datetime.now(UTC)
    return HttpStage(
        uuid4(),
        tuple((name, "sha256:" + "a" * 64) for name in ("worker", "helper", "gateway")),
        "a" * 64,
        123,
        now,
        now + timedelta(seconds=20),
        20.0,
        True,
        tuple(rows),
    )


def test_http_report_is_explicitly_incomplete_and_cannot_pass_full_validator(
    stage: HttpStage,
) -> None:
    raw = encode_stage(stage)
    value = json.loads(raw)
    assert value["http_stage_passed"] is True
    assert value["complete_matrix"] is value["isolation_checks_passed"] is False
    assert len(value["pending_cases"]) == 10
    assert (
        value["investigator_ip_protection_verified"]
        is value["internet_egress_verified"]
        is value["production_ready"]
        is False
    )
    assert read_stage(raw) == stage
    with pytest.raises(ReceiptError):
        read_receipt(raw)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_case",
        "duplicate_case",
        "invalid_case",
        "cleanup",
        "elapsed",
        "nan",
        "utc",
        "duration",
        "image",
        "network",
    ],
)
def test_stage_requires_complete_http_evidence_and_cleanup(stage: HttpStage, fault: str) -> None:
    bad = {
        "missing_case": replace(stage, cases=stage.cases[:-1]),
        "duplicate_case": replace(stage, cases=(stage.cases[0], *stage.cases[:-1])),
        "invalid_case": replace(
            stage, cases=(replace(stage.cases[0], control_success=False), *stage.cases[1:])
        ),
        "cleanup": replace(stage, cleanup_verified=False),
        "elapsed": replace(stage, elapsed_seconds=601),
        "nan": replace(stage, elapsed_seconds=float("nan")),
        "utc": replace(stage, started_at=stage.started_at.replace(tzinfo=None)),
        "duration": replace(stage, finished_at=stage.started_at + timedelta(seconds=601)),
        "image": replace(stage, images=(("worker", "latest"),)),
        "network": replace(stage, network_inode=True),
    }[fault]
    with pytest.raises(StageError):
        encode_stage(bad)


@pytest.mark.parametrize(
    "fault", ["flag", "pending", "unknown", "duplicate", "truncated", "huge", "type"]
)
def test_canonical_report_rejects_tampering(stage: HttpStage, fault: str) -> None:
    raw = encode_stage(stage)
    value = json.loads(raw)
    if fault == "flag":
        value["production_ready"] = True
    elif fault == "pending":
        value["pending_cases"] = []
    elif fault == "unknown":
        value["secret"] = "private-sentinel"
    elif fault == "type":
        value["images"] = []
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if fault == "duplicate":
        raw = raw.replace(b"{", b'{"complete_matrix":false,', 1)
    elif fault == "truncated":
        raw = raw[:-5]
    elif fault == "huge":
        raw = b"x" * 65537
    with pytest.raises(StageError):
        read_stage(raw)


def test_private_publication_is_atomic_and_idempotent(tmp_path: Path, stage: HttpStage) -> None:
    output = tmp_path / "http"
    file = publish_stage(output, stage)
    assert read_stage(file.read_bytes()) == stage
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert publish_stage(output, stage) == file
    assert (output / ".gitignore").read_bytes() == b"*\n"
    with pytest.raises(StageError):
        publish_stage(output, replace(stage, elapsed_seconds=21))


@pytest.mark.parametrize("fault", ["unrelated", "symlink", "wide", "invalid"])
def test_unsafe_or_invalid_publications_cannot_create_success(
    tmp_path: Path, stage: HttpStage, fault: str
) -> None:
    output = tmp_path / "http"
    if fault == "unrelated":
        output.mkdir(mode=0o700)
        (output / "file").write_text("private-sentinel")
    elif fault == "symlink":
        output.symlink_to(tmp_path, target_is_directory=True)
    elif fault == "wide":
        output.mkdir(mode=0o755)
        output.chmod(0o755)
    else:
        stage = replace(stage, cleanup_verified=False)
    with pytest.raises(StageError):
        publish_stage(output, stage)
    assert not (output / (str(stage.run_id) + ".json")).exists()
