"""Validation identities exclude execution time, principal, location and UUID."""

from dataclasses import replace

import pytest

from nima.contracts.history import HistoryError, Intent, Outcome, decode_intent, decode_outcome


def intent() -> Intent:
    return Intent("a" * 64, "b" * 64, "1.0.0", "c" * 64)


def test_stable_intent_and_outcome_identities_are_bound_to_policy_and_inputs() -> None:
    first = intent()
    assert first.digest == intent().digest and len(first.digest) == 64
    assert replace(first, artifact_sha256="d" * 64).digest != first.digest
    assert replace(first, contract_version="1.0.1").digest != first.digest
    assert decode_intent(first.payload()) == first
    with pytest.raises(HistoryError):
        decode_intent({**first.payload(), "validator_version": "other"})
    result = Outcome(first.digest, "passed", "byte_equivalence", "ok", "d" * 64, 7, 5)
    assert decode_outcome(result.payload()) == result
    assert result.digest == decode_outcome(result.payload()).digest
    assert not {"attempt_id", "recorded_at", "database_principal"} & result.payload().keys()


@pytest.mark.parametrize(
    "changes",
    [
        {"request_sha256": "x" * 64},
        {"artifact_sha256": "A" * 64},
        {"contract_sha256": "../private-sentinel"},
        {"contract_version": "01.0.0"},
    ],
)
def test_invalid_intent(changes: dict[str, str]) -> None:
    with pytest.raises(HistoryError, match="^validation_configuration$"):
        replace(intent(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "unknown"},
        {"reason": "private-sentinel"},
        {"check": "unknown"},
        {"snapshot_sha256": None},
        {"observation_count": True},
        {"record_count": 8},
        {"observation_count": 501},
    ],
)
def test_outcomes_are_closed_and_counts_are_exact(changes: dict[str, object]) -> None:
    result = Outcome(intent().digest, "passed", "byte_equivalence", "ok", "d" * 64, 7, 5)
    payload = {**result.payload(), **changes}
    with pytest.raises(HistoryError, match="^validation_integrity$"):
        decode_outcome(payload)


def test_failed_attempt_cannot_claim_verified_snapshot_or_counts() -> None:
    failed = Outcome(intent().digest, "failed", "artifact_integrity", "artifact_digest")
    assert failed.snapshot_sha256 is None
    with pytest.raises(HistoryError):
        replace(failed, snapshot_sha256="f" * 64)
    with pytest.raises(HistoryError):
        decode_outcome({**failed.payload(), "unexpected": "private-sentinel"})
