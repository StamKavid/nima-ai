"""Reconcile independent fixture observations; never attest deployed privacy."""

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Never
from uuid import UUID

from nima.egress.policy import CASES, CaseKind, FixturePolicy

BROWSER_ROUTES = frozenset({"html", "script", "image", "xhr", "fetch"})


class ReceiptError(ValueError):
    """A fixed reason, never a client error, target, path or credential."""


class ClientResult(StrEnum):
    FIXTURE_BODY = "fixture_body"
    NETWORK_FAILURE = "network_failure"
    PROXY_REJECTED = "proxy_rejected"
    CERTIFICATE_REJECTED = "certificate_rejected"
    ATTEMPTED = "attempted"
    IPV6_UNAVAILABLE = "ipv6_unavailable"


@dataclass(frozen=True, slots=True)
class CaseEvidence:
    case_name: str
    target_counter: str
    client_result: ClientResult
    control_success: bool | None = None
    target_deliveries: int | None = None
    gateway_tunnels: int | None = None
    gateway_rejections: int | None = None
    policy_drops: int | None = None
    observed_routes: frozenset[str] | None = None
    headers_clean: bool | None = None
    gateway_stopped: bool | None = None
    gateway_restarted: bool | None = None


def _positive(value: int | None) -> bool:
    return type(value) is int and value > 0


def validate_case(row: CaseEvidence) -> None:
    spec = next((case for case in CASES if case.name == row.case_name), None)
    if (
        spec is None
        or row.target_counter != spec.target_counter
        or not isinstance(row.client_result, ClientResult)
    ):
        raise ReceiptError("case")
    for value in (
        row.target_deliveries,
        row.gateway_tunnels,
        row.gateway_rejections,
        row.policy_drops,
    ):
        if value is not None and (type(value) is not int or not 0 <= value <= 1000000):
            raise ReceiptError("counter")
    for flag in (
        row.control_success,
        row.headers_clean,
        row.gateway_stopped,
        row.gateway_restarted,
    ):
        if flag is not None and type(flag) is not bool:
            raise ReceiptError("case_evidence")
    if row.observed_routes is not None and (
        type(row.observed_routes) is not frozenset or not row.observed_routes <= BROWSER_ROUTES
    ):
        raise ReceiptError("case_evidence")
    if spec.kind == CaseKind.IPV6_DISABLED:
        if row.client_result != ClientResult.IPV6_UNAVAILABLE or row.control_success is not None:
            raise ReceiptError("disabled_mode")
        return
    if row.control_success is not True:
        raise ReceiptError("control")
    if spec.kind in {CaseKind.ALLOWED, CaseKind.BROWSER_RESOURCES, CaseKind.RESTARTED}:
        required = BROWSER_ROUTES if spec.kind == CaseKind.BROWSER_RESOURCES else {"html"}
        if (
            row.client_result != ClientResult.FIXTURE_BODY
            or not _positive(row.target_deliveries)
            or not _positive(row.gateway_tunnels)
            or row.headers_clean is not True
            or row.observed_routes is None
            or not required <= row.observed_routes
            or (spec.kind == CaseKind.RESTARTED and row.gateway_restarted is not True)
        ):
            raise ReceiptError("allowed_path")
        return
    if row.target_deliveries != 0:
        raise ReceiptError("forbidden_delivery")
    if spec.kind == CaseKind.PACKET_BLOCKED:
        valid = row.client_result in {
            ClientResult.NETWORK_FAILURE,
            ClientResult.ATTEMPTED,
        } and _positive(row.policy_drops)
    elif spec.kind == CaseKind.GATEWAY_REJECTED:
        valid = row.client_result == ClientResult.PROXY_REJECTED and _positive(
            row.gateway_rejections
        )
    elif spec.kind == CaseKind.TLS_REJECTED:
        valid = row.client_result == ClientResult.CERTIFICATE_REJECTED and _positive(
            row.gateway_tunnels
        )
    elif spec.kind == CaseKind.GATEWAY_OUTAGE:
        valid = row.client_result == ClientResult.NETWORK_FAILURE and row.gateway_stopped is True
    else:
        raise ReceiptError("case")
    if not valid:
        raise ReceiptError("case_evidence")


@dataclass(frozen=True, slots=True)
class RuntimeEvidence:
    worker_uid: int
    observer_uid: int
    cap_effective: int
    cap_permitted: int
    cap_bounding: int
    no_new_privs: int
    seccomp: int
    ipv6_disabled: bool
    sandbox_pid: bool
    sandbox_network: bool
    sandbox_seccomp: bool
    root_readonly: bool
    controls_unreachable: bool
    observer_uid_denied: bool
    parent_net_admin_denied: bool
    external_networks: bool
    gateway_forwarding_disabled: bool


@dataclass(frozen=True, slots=True)
class Receipt:
    run_id: UUID
    policy_sha256: str
    runtime_profile_sha256: str
    images: tuple[tuple[str, str], ...]
    started_at: datetime
    finished_at: datetime
    runtime: RuntimeEvidence
    cases: tuple[CaseEvidence, ...]


def validate_receipt(receipt: Receipt) -> None:
    policy = FixturePolicy()
    if (
        not isinstance(receipt.run_id, UUID)
        or receipt.run_id.version != 4
        or receipt.policy_sha256 != policy.digest
        or receipt.runtime_profile_sha256 != policy.seccomp_sha256
        or type(receipt.images) is not tuple
        or len(receipt.images) != 3
        or any(
            type(pair) is not tuple
            or len(pair) != 2
            or type(pair[0]) is not str
            or type(pair[1]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", pair[1]) is None
            for pair in receipt.images
        )
        or {pair[0] for pair in receipt.images} != {"worker", "gateway", "helper"}
    ):
        raise ReceiptError("identity")
    for instant in (receipt.started_at, receipt.finished_at):
        if not isinstance(instant, datetime) or instant.utcoffset() != timedelta(0):
            raise ReceiptError("time")
    if (
        not timedelta(0)
        <= receipt.finished_at - receipt.started_at
        <= timedelta(seconds=policy.max_seconds)
    ):
        raise ReceiptError("time")
    expected = {
        "worker_uid": 10001,
        "observer_uid": 10002,
        "cap_effective": 0,
        "cap_permitted": 0,
        "cap_bounding": 0,
        "no_new_privs": 1,
        "seccomp": 2,
        "ipv6_disabled": True,
        "sandbox_pid": True,
        "sandbox_network": True,
        "sandbox_seccomp": True,
        "root_readonly": True,
        "controls_unreachable": True,
        "observer_uid_denied": True,
        "parent_net_admin_denied": True,
        "external_networks": False,
        "gateway_forwarding_disabled": True,
    }
    if type(receipt.runtime) is not RuntimeEvidence:
        raise ReceiptError("runtime")
    observed = asdict(receipt.runtime)
    if any(
        type(observed[name]) is not type(value) or observed[name] != value
        for name, value in expected.items()
    ):
        raise ReceiptError("runtime")
    if (
        type(receipt.cases) is not tuple
        or len(receipt.cases) != len(CASES)
        or any(type(row) is not CaseEvidence for row in receipt.cases)
        or any(type(row.case_name) is not str for row in receipt.cases)
        or {row.case_name for row in receipt.cases} != {case.name for case in CASES}
    ):
        raise ReceiptError("cases")
    for row in receipt.cases:
        validate_case(row)


def encode_receipt(receipt: Receipt) -> bytes:
    validate_receipt(receipt)
    body = {
        "version": "source-worker-egress-v1",
        "scope": "controlled-fixtures",
        "run_id": str(receipt.run_id),
        "policy_sha256": receipt.policy_sha256,
        "runtime_profile_sha256": receipt.runtime_profile_sha256,
        "images": dict(receipt.images),
        "started_at": receipt.started_at.isoformat(),
        "finished_at": receipt.finished_at.isoformat(),
        "runtime": asdict(receipt.runtime),
        "cases": [
            {
                **asdict(row),
                "client_result": row.client_result.value,
                "observed_routes": sorted(row.observed_routes)
                if row.observed_routes is not None
                else None,
                "result": "passed",
            }
            for row in receipt.cases
        ],
        "isolation_checks_passed": True,
        "internet_egress_verified": False,
        "investigator_ip_protection_verified": False,
        "production_ready": False,
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(raw) > FixturePolicy().max_receipt_bytes:
        raise ReceiptError("report_limit")
    return raw


def _reject_constant(value: str) -> Never:
    raise ReceiptError("receipt")


def _unique(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ReceiptError("receipt")
        result[key] = value
    return result


def read_receipt(raw: bytes) -> Receipt:
    if not 0 < len(raw) <= FixturePolicy().max_receipt_bytes:
        raise ReceiptError("receipt")
    try:
        body = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_reject_constant
        )
        if type(body["cases"]) is not list or len(body["cases"]) != len(CASES):
            raise ReceiptError("receipt")
        rows = []
        for value in body["cases"]:
            row = dict(value)
            if row.pop("result") != "passed":
                raise ReceiptError("receipt")
            row["client_result"] = ClientResult(row["client_result"])
            if row["observed_routes"] is not None:
                row["observed_routes"] = frozenset(row["observed_routes"])
            rows.append(CaseEvidence(**row))
        receipt = Receipt(
            run_id=UUID(body["run_id"]),
            policy_sha256=body["policy_sha256"],
            runtime_profile_sha256=body["runtime_profile_sha256"],
            images=tuple((name, body["images"][name]) for name in ("worker", "gateway", "helper")),
            started_at=datetime.fromisoformat(body["started_at"]),
            finished_at=datetime.fromisoformat(body["finished_at"]),
            runtime=RuntimeEvidence(**body["runtime"]),
            cases=tuple(rows),
        )
        # The published format is canonical. This also rejects unknown root keys,
        # altered flags, duplicate route roles and noncanonical values.
        if encode_receipt(receipt) != raw:
            raise ReceiptError("receipt")
        return receipt
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        raise ReceiptError("receipt") from None


def publish_receipt(output_dir: Path, receipt: Receipt) -> Path:
    # Reuse only private POSIX file primitives, never the manual-evidence format
    # or its root initializer/markers. Validation precedes filesystem changes.
    from nima.evidence import EvidenceError, artifacts

    raw = encode_receipt(receipt)
    marker_name = ".nima-source-worker"
    marker = b"source-worker-egress-v1\n"
    descriptor = None
    try:
        descriptor = artifacts.directory(output_dir, create=True, private=True)
        names = set(os.listdir(descriptor))
        if marker_name in names:
            if artifacts.read(descriptor, marker_name, limit=len(marker), private=True) != marker:
                raise ReceiptError("publication")
        elif any(not name.startswith(".tmp-") for name in names):
            raise ReceiptError("publication")
        artifacts.publish(descriptor, marker_name, marker)
        artifacts.publish(descriptor, ".gitignore", b"*\n")
        filename = str(receipt.run_id) + ".json"
        artifacts.publish(descriptor, filename, raw)
        return output_dir / filename
    except (OSError, EvidenceError):
        raise ReceiptError("publication") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
