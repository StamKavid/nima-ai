"""Client failure alone cannot prove packet enforcement or proxy rejection."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from nima.egress.policy import CASES, CaseKind, FixturePolicy
from nima.egress.receipt import (
    CaseEvidence,
    ClientResult,
    Receipt,
    ReceiptError,
    RuntimeEvidence,
    encode_receipt,
    publish_receipt,
    read_receipt,
    validate_case,
)


def blocked() -> CaseEvidence:
    return CaseEvidence(
        case_name="http_direct_ipv4",
        target_counter="tcp_accepts",
        client_result=ClientResult.NETWORK_FAILURE,
        control_success=True,
        target_deliveries=0,
        policy_drops=1,
    )


def test_network_failure_needs_control_and_an_observed_packet_drop() -> None:
    validate_case(blocked())
    for row in (
        replace(blocked(), control_success=False),
        replace(blocked(), control_success=None),
        replace(blocked(), target_deliveries=1),
        replace(blocked(), target_deliveries=None),
        replace(blocked(), policy_drops=0),
        replace(blocked(), policy_drops=None),
        replace(blocked(), policy_drops=True),
        replace(blocked(), target_counter="application_requests"),
        replace(blocked(), case_name="private-secret"),
        replace(blocked(), client_result=ClientResult.FIXTURE_BODY),
    ):
        with pytest.raises(ReceiptError) as error:
            validate_case(row)
        assert "private-secret" not in str(error.value)


def test_gateway_denial_and_tls_failure_need_their_own_evidence() -> None:
    denied = CaseEvidence(
        case_name="http_invalid_auth",
        target_counter="application_requests",
        client_result=ClientResult.PROXY_REJECTED,
        control_success=True,
        target_deliveries=0,
        gateway_rejections=1,
    )
    validate_case(denied)
    with pytest.raises(ReceiptError):
        validate_case(replace(denied, gateway_rejections=0))
    tls = replace(
        denied,
        case_name="http_invalid_tls",
        client_result=ClientResult.CERTIFICATE_REJECTED,
        gateway_rejections=None,
        gateway_tunnels=1,
    )
    validate_case(tls)
    with pytest.raises(ReceiptError):
        validate_case(replace(tls, client_result=ClientResult.NETWORK_FAILURE))


def test_browser_success_requires_all_resource_roles_and_clean_origin_headers() -> None:
    row = CaseEvidence(
        case_name="browser_resources",
        target_counter="application_requests",
        client_result=ClientResult.FIXTURE_BODY,
        control_success=True,
        target_deliveries=5,
        gateway_tunnels=1,
        headers_clean=True,
        observed_routes=frozenset({"html", "script", "image", "xhr", "fetch"}),
    )
    validate_case(row)
    for missing in row.observed_routes or ():
        with pytest.raises(ReceiptError):
            validate_case(
                replace(row, observed_routes=(row.observed_routes or frozenset()) - {missing})
            )
    with pytest.raises(ReceiptError):
        validate_case(replace(row, headers_clean=False))


def complete() -> Receipt:
    rows = []
    for case in CASES:
        allowed = case.kind in {CaseKind.ALLOWED, CaseKind.BROWSER_RESOURCES, CaseKind.RESTARTED}
        outcomes = {
            CaseKind.ALLOWED: ClientResult.FIXTURE_BODY,
            CaseKind.BROWSER_RESOURCES: ClientResult.FIXTURE_BODY,
            CaseKind.RESTARTED: ClientResult.FIXTURE_BODY,
            CaseKind.PACKET_BLOCKED: ClientResult.NETWORK_FAILURE,
            CaseKind.GATEWAY_REJECTED: ClientResult.PROXY_REJECTED,
            CaseKind.TLS_REJECTED: ClientResult.CERTIFICATE_REJECTED,
            CaseKind.GATEWAY_OUTAGE: ClientResult.NETWORK_FAILURE,
            CaseKind.IPV6_DISABLED: ClientResult.IPV6_UNAVAILABLE,
        }
        rows.append(
            CaseEvidence(
                case_name=case.name,
                target_counter=case.target_counter,
                client_result=outcomes[case.kind],
                control_success=None if case.kind == CaseKind.IPV6_DISABLED else True,
                target_deliveries=5 if allowed else 0,
                gateway_tunnels=1 if allowed or case.kind == CaseKind.TLS_REJECTED else 0,
                gateway_rejections=1 if case.kind == CaseKind.GATEWAY_REJECTED else 0,
                policy_drops=1 if case.kind == CaseKind.PACKET_BLOCKED else 0,
                observed_routes=frozenset({"html", "script", "image", "xhr", "fetch"})
                if allowed
                else None,
                headers_clean=True if allowed else None,
                gateway_stopped=case.kind == CaseKind.GATEWAY_OUTAGE,
                gateway_restarted=case.kind == CaseKind.RESTARTED,
            )
        )
    start = datetime(2026, 11, 12, tzinfo=UTC)
    return Receipt(
        run_id=UUID("00000000-0000-4000-8000-000000000001"),
        policy_sha256=FixturePolicy().digest,
        runtime_profile_sha256=FixturePolicy().seccomp_sha256,
        images=tuple((name, "sha256:" + "a" * 64) for name in ("worker", "gateway", "helper")),
        started_at=start,
        finished_at=start + timedelta(seconds=10),
        runtime=RuntimeEvidence(
            worker_uid=10001,
            observer_uid=10002,
            cap_effective=0,
            cap_permitted=0,
            cap_bounding=0,
            no_new_privs=1,
            seccomp=2,
            ipv6_disabled=True,
            sandbox_pid=True,
            sandbox_network=True,
            sandbox_seccomp=True,
            root_readonly=True,
            controls_unreachable=True,
            observer_uid_denied=True,
            parent_net_admin_denied=True,
            external_networks=False,
            gateway_forwarding_disabled=True,
        ),
        cases=tuple(rows),
    )


def test_only_complete_reconciled_fixtures_can_receive_a_passing_receipt() -> None:
    receipt = complete()
    raw = encode_receipt(receipt)
    body = json.loads(raw)
    assert len(raw) <= 64 * 1024
    assert body["scope"] == "controlled-fixtures"
    assert body["isolation_checks_passed"] is True
    for name in (
        "internet_egress_verified",
        "investigator_ip_protection_verified",
        "production_ready",
    ):
        assert body[name] is False
    assert len(body["cases"]) == len(CASES)
    for rows in ((), receipt.cases[:-1], receipt.cases[:-1] + receipt.cases[:1]):
        with pytest.raises(ReceiptError, match="^cases$"):
            encode_receipt(replace(receipt, cases=rows))


@pytest.mark.parametrize(
    "runtime",
    [
        replace(complete().runtime, worker_uid=0),
        replace(complete().runtime, observer_uid=10001),
        replace(complete().runtime, cap_effective=4096),
        replace(complete().runtime, cap_bounding=False),
        replace(complete().runtime, no_new_privs=0),
        replace(complete().runtime, seccomp=0),
        replace(complete().runtime, ipv6_disabled=False),
        replace(complete().runtime, sandbox_network=False),
        replace(complete().runtime, controls_unreachable=False),
        replace(complete().runtime, observer_uid_denied=False),
        replace(complete().runtime, parent_net_admin_denied=False),
        replace(complete().runtime, external_networks=True),
        replace(complete().runtime, gateway_forwarding_disabled=False),
    ],
)
def test_unverified_or_broader_runtime_never_passes(runtime: RuntimeEvidence) -> None:
    receipt = complete()
    with pytest.raises(ReceiptError, match="^runtime$"):
        encode_receipt(replace(receipt, runtime=runtime))


def test_identity_and_time_bounds_are_mandatory() -> None:
    receipt = complete()
    for invalid in (
        replace(receipt, policy_sha256="private-secret"),
        replace(receipt, runtime_profile_sha256="b" * 64),
        replace(receipt, images=()),
        replace(receipt, finished_at=receipt.started_at - timedelta(seconds=1)),
        replace(receipt, finished_at=receipt.started_at + timedelta(seconds=601)),
        replace(receipt, started_at=receipt.started_at.replace(tzinfo=None)),
    ):
        with pytest.raises(ReceiptError) as error:
            encode_receipt(invalid)
        assert "private-secret" not in str(error.value)


def test_outage_and_disabled_mode_cannot_be_inferred_from_generic_failure() -> None:
    rows = {row.case_name: row for row in complete().cases}
    with pytest.raises(ReceiptError):
        validate_case(replace(rows["http_gateway_outage"], gateway_stopped=False))
    with pytest.raises(ReceiptError):
        validate_case(replace(rows["ipv6_disabled"], control_success=True))


def test_existing_unowned_directory_is_not_adopted(tmp_path: Path) -> None:
    note = tmp_path / "notes.txt"
    note.write_bytes(b"private operator material")
    with pytest.raises(ReceiptError, match="^publication$"):
        publish_receipt(tmp_path, complete())
    assert note.read_bytes() == b"private operator material"
    assert set(path.name for path in tmp_path.iterdir()) == {"notes.txt"}


def test_independent_reader_rejects_tampering_and_unknown_fields() -> None:
    receipt = complete()
    raw = encode_receipt(receipt)
    assert read_receipt(raw) == receipt
    for field, value in (
        ("investigator_ip_protection_verified", True),
        ("production_ready", True),
        ("version", "publicity-manual-evidence-v1"),
        ("secret", "private-secret"),
        ("cases", []),
    ):
        body = json.loads(raw)
        body[field] = value
        changed = json.dumps(body, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        with pytest.raises(ReceiptError, match="^receipt$"):
            read_receipt(changed)
    for changed in (b"", b"x" * 65537, b'{"scope":1,"scope":2}', b'{"x":NaN}', b"[" * 2000):
        with pytest.raises(ReceiptError, match="^receipt$"):
            read_receipt(changed)


def test_private_publication_is_idempotent_and_preserves_conflicting_evidence(
    tmp_path: Path,
) -> None:
    receipt = complete()
    root = tmp_path / "receipts"
    path = publish_receipt(root, receipt)
    assert path == root / (str(receipt.run_id) + ".json")
    assert root.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    assert read_receipt(path.read_bytes()) == receipt
    inode = path.stat().st_ino
    assert publish_receipt(root, receipt) == path
    assert path.stat().st_ino == inode
    with pytest.raises(ReceiptError, match="^publication$"):
        publish_receipt(
            root, replace(receipt, finished_at=receipt.finished_at + timedelta(seconds=1))
        )
    assert read_receipt(path.read_bytes()) == receipt
    assert not list(root.glob(".tmp-*"))
    assert not (root / ".nima-publicity").exists()


def test_failed_or_redirected_publication_never_creates_a_passing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReceiptError, match="^publication$"):
        publish_receipt(alias, complete())
    assert list(outside.iterdir()) == []
    from nima.evidence import artifacts

    original = artifacts.publish

    def fail(parent: int, name: str, body: bytes) -> None:
        if name.endswith(".json"):
            raise OSError("private-secret-path")
        original(parent, name, body)

    monkeypatch.setattr(artifacts, "publish", fail)
    with pytest.raises(ReceiptError, match="^publication$"):
        publish_receipt(outside, complete())
    assert not list(outside.glob("*.json"))
