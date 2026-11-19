"""Explicit post-publication checks: separate journal writes, no source repair."""

import hashlib
import os
from pathlib import Path
from uuid import UUID

from nima.analytics.export import prepare_readout
from nima.analytics.request import ReadoutRequest, RequestError, read_request
from nima.analytics.result import MAX_RESULT_BYTES, ReadoutError
from nima.contracts import ContractError, contract, validate_output
from nima.contracts.history import HistoryError, Intent, Outcome, digest, valid_digest
from nima.evidence import EvidenceError, artifacts
from nima.storage.validations import Journal


def _artifact(path: Path) -> bytes:
    fd = artifacts.directory(path.parent, private=True)
    try:
        if os.stat(path.name, dir_fd=fd, follow_symlinks=False).st_nlink != 1:
            raise EvidenceError("input_changed")
        body = artifacts.read(fd, path.name, limit=MAX_RESULT_BYTES, private=True)
        if os.stat(path.name, dir_fd=fd, follow_symlinks=False).st_nlink != 1:
            raise EvidenceError("input_changed")
        return body
    finally:
        os.close(fd)


def _check(dsn: str, request: ReadoutRequest, report: Path, intent: Intent) -> Outcome:
    def result(status: str, check: str, reason: str) -> Outcome:
        return Outcome(intent.digest, status, check, reason)

    try:
        body = _artifact(report)
    except (EvidenceError, OSError):
        return result("blocked", "artifact_integrity", "artifact_unavailable")
    if hashlib.sha256(body).hexdigest() != intent.artifact_sha256:
        return result("failed", "artifact_integrity", "artifact_digest")
    try:
        prepared = prepare_readout(dsn, request)
    except ReadoutError as error:
        if error.reason == "analytics_contract":
            return result("failed", "output_contract", "contract_rejected")
        return result("blocked", "reconstruction", "inputs_unavailable")
    try:
        validate_output(
            body,
            metric=prepared.snapshot.metric.payload(),
            observation_count=len(prepared.snapshot.observations),
        )
        current = contract()
        if (
            current["version"] != intent.contract_version
            or digest(current) != intent.contract_sha256
        ):
            return result("blocked", "reconstruction", "inputs_unavailable")
    except ContractError:
        return result("failed", "output_contract", "contract_rejected")
    if body != prepared.body:
        return result("failed", "byte_equivalence", "bytes_differ")
    return Outcome(
        intent.digest,
        "passed",
        "byte_equivalence",
        "ok",
        prepared.snapshot.input_sha256,
        len(prepared.snapshot.observations),
        prepared.snapshot.metric.total,
    )


def validate_readout(
    source_dsn: str, journal_dsn: str, attempt: UUID, request_file: Path, report: Path
) -> dict[str, object]:
    if (
        not isinstance(source_dsn, str)
        or not source_dsn.strip()
        or not isinstance(report, Path)
        or not report.is_absolute()
        or any(p in {"..", ".git"} for p in report.parts)
        or "\x00" in str(report)
        or str(report).startswith("//")
        or report.suffix != ".json"
        or not valid_digest(report.stem)
    ):
        raise HistoryError("validation_configuration")
    try:
        request = read_request(request_file)
        metadata = contract()
        intent = Intent(request.request_sha256, report.stem, metadata["version"], digest(metadata))
    except RequestError:
        raise HistoryError("validation_configuration") from None
    except ContractError:
        raise HistoryError("validation_policy") from None
    with Journal(journal_dsn, attempt, intent).session() as journal:
        stored = journal.read()
        if stored["status"] != "pending":
            return {**stored, "reused": True}
        outcome = _check(source_dsn, request, report, intent)
        return {**journal.finish(outcome), "reused": False}
