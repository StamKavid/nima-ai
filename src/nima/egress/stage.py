"""Private, incomplete HTTP-stage evidence; never a full isolation attestation."""

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from nima.egress.policy import CASES, FixturePolicy
from nima.egress.probe_http import HTTP_CASES
from nima.egress.receipt import CaseEvidence, ClientResult, ReceiptError, validate_case
from nima.evidence import EvidenceError, artifacts


class StageError(ValueError):
    """Fixed reasons only; no workload data or private configuration."""


@dataclass(frozen=True, slots=True)
class HttpStage:
    run_id: UUID
    images: tuple[tuple[str, str], ...]
    packet_policy_sha256: str
    network_inode: int
    started_at: datetime
    finished_at: datetime
    elapsed_seconds: float
    cleanup_verified: bool
    cases: tuple[CaseEvidence, ...]


def encode_stage(stage: HttpStage) -> bytes:
    policy = FixturePolicy()
    if (
        not isinstance(stage.run_id, UUID)
        or stage.run_id.version != 4
        or type(stage.images) is not tuple
        or len(stage.images) != 3
        or any(
            type(pair) is not tuple
            or len(pair) != 2
            or type(pair[0]) is not str
            or type(pair[1]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", pair[1]) is None
            for pair in stage.images
        )
        or {pair[0] for pair in stage.images} != {"worker", "helper", "gateway"}
        or type(stage.packet_policy_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", stage.packet_policy_sha256) is None
        or type(stage.network_inode) is not int
        or not 0 < stage.network_inode < 2**64
        or stage.cleanup_verified is not True
    ):
        raise StageError("stage_identity")
    if any(
        not isinstance(instant, datetime) or instant.utcoffset() != timedelta(0)
        for instant in (stage.started_at, stage.finished_at)
    ) or not timedelta(0) <= stage.finished_at - stage.started_at <= timedelta(
        seconds=policy.max_seconds
    ):
        raise StageError("stage_time")
    if (
        type(stage.elapsed_seconds) not in (int, float)
        or not math.isfinite(stage.elapsed_seconds)
        or not 0 <= stage.elapsed_seconds <= policy.max_seconds
    ):
        raise StageError("stage_time")
    if (
        type(stage.cases) is not tuple
        or any(type(row) is not CaseEvidence for row in stage.cases)
        or tuple(row.case_name for row in stage.cases) != tuple(case.name for case in HTTP_CASES)
    ):
        raise StageError("stage_cases")
    try:
        for row in stage.cases:
            validate_case(row)
    except ReceiptError:
        raise StageError("stage_case_evidence") from None
    body = {
        "version": "source-worker-http-stage-v1",
        "scope": "controlled-fixtures",
        "run_id": str(stage.run_id),
        "images": dict(stage.images),
        "policy_sha256": policy.digest,
        "runtime_profile_sha256": policy.seccomp_sha256,
        "packet_policy_sha256": stage.packet_policy_sha256,
        "network_inode": stage.network_inode,
        "started_at": stage.started_at.isoformat(),
        "finished_at": stage.finished_at.isoformat(),
        "elapsed_seconds": stage.elapsed_seconds,
        "cleanup_verified": stage.cleanup_verified,
        "cases": [
            {
                **asdict(row),
                "client_result": row.client_result.value,
                "observed_routes": sorted(row.observed_routes)
                if row.observed_routes is not None
                else None,
            }
            for row in stage.cases
        ],
        "http_stage_passed": True,
        "pending_cases": [case.name for case in CASES if case not in HTTP_CASES],
        "complete_matrix": False,
        "isolation_checks_passed": False,
        "internet_egress_verified": False,
        "investigator_ip_protection_verified": False,
        "production_ready": False,
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if len(raw) > policy.max_receipt_bytes:
        raise StageError("stage_limit")
    return raw


def read_stage(raw: bytes) -> HttpStage:
    if not 0 < len(raw) <= FixturePolicy().max_receipt_bytes:
        raise StageError("stage_report")
    try:
        body = json.loads(raw)
        if (
            type(body) is not dict
            or type(body["images"]) is not dict
            or type(body["cases"]) is not list
        ):
            raise StageError("stage_report")
        rows = tuple(
            CaseEvidence(
                **{
                    **row,
                    "client_result": ClientResult(row["client_result"]),
                    "observed_routes": frozenset(row["observed_routes"])
                    if row["observed_routes"] is not None
                    else None,
                }
            )
            for row in body["cases"]
        )
        stage = HttpStage(
            UUID(body["run_id"]),
            tuple((name, body["images"][name]) for name in ("worker", "helper", "gateway")),
            body["packet_policy_sha256"],
            body["network_inode"],
            datetime.fromisoformat(body["started_at"]),
            datetime.fromisoformat(body["finished_at"]),
            body["elapsed_seconds"],
            body["cleanup_verified"],
            rows,
        )
        if encode_stage(stage) != raw:
            raise StageError("stage_report")
        return stage
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError, OverflowError):
        raise StageError("stage_report") from None


def publish_stage(output_dir: Path, stage: HttpStage) -> Path:
    raw = encode_stage(stage)  # Validate before touching output storage.
    marker_name, marker = ".nima-source-worker-http", b"source-worker-http-stage-v1\n"
    descriptor = None
    try:
        descriptor = artifacts.directory(output_dir, create=True, private=True)
        names = set(os.listdir(descriptor))
        if marker_name in names:
            if artifacts.read(descriptor, marker_name, limit=len(marker), private=True) != marker:
                raise StageError("stage_publication")
        elif any(not name.startswith(".tmp-") for name in names):
            raise StageError("stage_publication")
        artifacts.publish(descriptor, marker_name, marker)
        artifacts.publish(descriptor, ".gitignore", b"*\n")
        filename = str(stage.run_id) + ".json"
        artifacts.publish(descriptor, filename, raw)
        return output_dir / filename
    except (OSError, EvidenceError):
        raise StageError("stage_publication") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
