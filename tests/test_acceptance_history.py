"""Recorded execution is distinct from data fitness and current policy defaults."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from nima.contracts.acceptance_history import (
    HistoryError,
    Intent,
    Outcome,
    Record,
    assessed_outcome,
    decode_intent,
    decode_outcome,
)


@pytest.fixture
def prepared_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Intent, bytes]:
    from nima.dataops import citation_acceptance as adapter
    from nima.identity.artifacts import encode
    from tests.citation_acceptance_samples import producer
    from tests.test_citation_acceptance import subject
    from tests.test_source_citations import contract, decision

    request, document, result = producer((contract(1, "C"),), (decision(),))
    parent = encode(document)
    monkeypatch.setattr(adapter, "prepare_citation_readout", lambda *_: (parent, result))
    prepared = adapter.prepare_citation_acceptance(
        "fixture", request, subject(tmp_path / "reports", parent)
    )
    return Intent(request.request_sha256, prepared.subject_sha256), prepared.body


def test_assessment_body_binds_parent_request_policy_and_old_profile(
    prepared_body: tuple[Intent, bytes],
) -> None:
    import hashlib

    from nima.contracts.acceptance_history import assessed_outcome

    intent, body = prepared_body
    outcome = assessed_outcome(intent, body)
    assert outcome.data_fitness == "ready"
    assert outcome.acceptance_sha256 == hashlib.sha256(body).hexdigest()
    with pytest.raises(HistoryError, match="^acceptance_history_integrity$"):
        assessed_outcome(replace(intent, subject_sha256="c" * 64), body)


@pytest.mark.parametrize(
    "fault",
    [
        "extra",
        "status",
        "cohort",
        "policy",
        "model",
        "count_bool",
        "count_grain",
        "check",
        "noncanonical",
        "json",
        "limit",
    ],
)
def test_malformed_body_cannot_be_attested(prepared_body: tuple[Intent, bytes], fault: str) -> None:
    import json

    from nima.contracts.acceptance_history import assessed_outcome
    from nima.identity.artifacts import encode

    intent, body = prepared_body
    value = json.loads(body)
    if fault == "extra":
        value["source_label"] = "PRIVATE"
    elif fault == "status":
        value["assessment"]["status"] = "passed"
    elif fault == "cohort":
        value["subject"]["cohort_sha256"] = "f" * 64
    elif fault == "policy":
        value["policy"]["definition_sha256"] = "c" * 64
    elif fault == "model":
        value["subject"]["model"]["definition_sha256"] = "c" * 64
    elif fault == "count_bool":
        value["assessment"]["counts"][0]["value"] = True
    elif fault == "count_grain":
        value["assessment"]["counts"][0]["grain"] = "PRIVATE"
    elif fault == "check":
        value["assessment"]["checks"][0]["reason"] = "PRIVATE"
    body = encode(value)
    if fault == "noncanonical":
        body += b" "
    elif fault == "json":
        body = b"{"
    elif fault == "limit":
        body = b"x" * 65537
    with pytest.raises(HistoryError):
        assessed_outcome(intent, body)


def test_intent_identity_is_stable_and_profiles_are_recorded() -> None:
    value = Intent("a" * 64, "b" * 64)
    assert decode_intent(value.payload()) == value
    assert decode_intent(dict(reversed(list(value.payload().items())))).digest == value.digest
    assert replace(value, request_sha256="c" * 64).digest != value.digest
    assert replace(value, subject_sha256="c" * 64).digest != value.digest
    assert replace(value, policy_sha256="c" * 64).digest != value.digest
    assert value.supported
    assert not replace(value, policy_sha256="c" * 64).supported
    assert (
        not {"attempt_id", "dsn", "archive_root", "started_at", "database_principal"}
        & value.payload().keys()
    )


@pytest.mark.parametrize("fitness", ["ready", "limited", "blocked", "not_assessed"])
def test_assessed_is_not_an_execution_success_boolean(fitness: str) -> None:
    result = Outcome("a" * 64, "assessed", fitness, "b" * 64, None)
    assert result.data_fitness == fitness
    assert result.payload()["execution_state"] == "assessed"


@pytest.mark.parametrize("fitness", [None, "blocked", "ready"])
def test_refusal_carries_no_assessment(fitness: str | None) -> None:
    if fitness is None:
        value = Outcome("a" * 64, "refused", None, None, "acceptance_evidence")
        assert value.acceptance_sha256 is None
    else:
        with pytest.raises(HistoryError, match="^acceptance_history_integrity$"):
            Outcome("a" * 64, "refused", fitness, None, "acceptance_evidence")


@pytest.mark.parametrize(
    "change",
    [
        {"request_sha256": None},
        {"subject_sha256": "z" * 64},
        {"policy_sha256": "a" * 63},
        {"policy_version": None},
        {"policy_version": "1.0"},
        {"policy_version": "1" * 65},
        {"recorder_version": None},
        {"recorder_version": "a" * 97},
    ],
)
def test_invalid_intent(change: dict[str, Any]) -> None:
    with pytest.raises(HistoryError):
        replace(Intent("a" * 64, "b" * 64), **change)


@pytest.mark.parametrize("decoder", [decode_intent, decode_outcome])
@pytest.mark.parametrize("value", [None, [], {}, {"extra": "PRIVATE"}])
def test_closed_decoders_reject_other_shapes(decoder: Any, value: object) -> None:
    with pytest.raises(HistoryError, match="acceptance_history_integrity"):
        decoder(value)


def test_decoder_digests_and_extra_fields() -> None:
    intent = Intent("a" * 64, "b" * 64)
    result = Outcome(intent.digest, "refused", None, None, "acceptance_contract")
    assert decode_outcome(result.payload()) == result
    assert len(result.digest) == 64
    for decoder, value in [(decode_intent, intent.payload()), (decode_outcome, result.payload())]:
        value["extra"] = True
        with pytest.raises(HistoryError):
            decoder(value)
    assert str(HistoryError("PRIVATE")) == "acceptance_history_integrity"
    with pytest.raises(HistoryError):
        assessed_outcome(replace(intent, policy_version="2.0.0"), b"{}")


@pytest.mark.parametrize(
    "change",
    [
        {"intent_sha256": None},
        {"execution_state": "pending"},
        {"data_fitness": []},
        {"acceptance_sha256": "wrong"},
        {"refusal_code": "acceptance_input"},
    ],
)
def test_invalid_assessed_envelope(change: dict[str, Any]) -> None:
    with pytest.raises(HistoryError):
        replace(Outcome("a" * 64, "assessed", "ready", "b" * 64, None), **change)


@pytest.mark.parametrize(
    "change",
    [
        {"attempt_id": "not UUID"},
        {"intent": None},
        {"started_at": None},
        {"started_at": datetime(2026, 1, 1)},
        {"recorded_at": datetime.now(UTC)},
        {"body": b"unexpected"},
        {"outcome": "wrong", "recorded_at": datetime.now(UTC)},
        {
            "outcome": lambda: Outcome("f" * 64, "refused", None, None, "acceptance_input"),
            "recorded_at": datetime.now(UTC),
        },
    ],
)
def test_invalid_record(change: dict[str, Any]) -> None:
    change = {k: v() if callable(v) else v for k, v in change.items()}
    pending = Record(uuid4(), Intent("a" * 64, "b" * 64), datetime.now(UTC), None, None)
    assert pending.execution_state == "pending"
    with pytest.raises(HistoryError):
        replace(pending, **change)


def test_assessed_record_rechecks_exact_stored_body(prepared_body: tuple[Intent, bytes]) -> None:
    intent, body = prepared_body
    outcome = assessed_outcome(intent, body)
    clock = datetime.now(UTC)
    record = Record(uuid4(), intent, clock, outcome, clock, body)
    assert record.execution_state == "assessed"
    assert record.payload()["outcome_sha256"] == outcome.digest
    assert record.payload(reused=False)["verification_scope"] == "fresh_recording_attempt"
    for change in (
        {"body": None},
        {"body": body + b" "},
        {"recorded_at": "wrong"},
        {"recorded_at": datetime(2026, 1, 1)},
        {"outcome": replace(outcome, data_fitness="blocked")},
    ):
        with pytest.raises(HistoryError):
            replace(record, **change)


# Independent mutations of each binding/shape; no policy evaluation is used by
# the historical decoder, and the policy definition remains pinned by its hash.
@pytest.mark.parametrize(
    "path,replacement",
    [
        ("version", "other"),
        ("subject", None),
        ("subject.version", "other"),
        ("subject.request", {}),
        ("policy.definition", {}),
        ("assessment.policy_sha256", "c" * 64),
        ("assessment.policy_id", "other"),
        ("assessment.policy_version", "2.0.0"),
        ("assessment.request_sha256", "c" * 64),
        ("subject.cohort_sha256", "bad"),
        ("assessment.use", "other"),
        ("assessment.amount_eligibility", "eligible"),
        ("subject.model.id", "other"),
        ("subject.model.status", "other"),
        ("assessment.facts_sha256", "bad"),
        ("subject.model.sql_sha256", "c" * 64),
        ("assessment.provider_status", "other"),
        ("assessment.required_checks", []),
        ("subject.run_profiles", None),
        ("subject.run_profiles", [{}] * 11),
        ("subject.evidence_scope", "other"),
        ("subject.raw_bytes", "other"),
        ("interpretation_limits", None),
        ("interpretation_limits", [1]),
        ("assessment.checks", None),
        ("assessment.checks", []),
        ("assessment.counts", None),
        ("assessment.limitations", None),
        ("assessment.limitations", ["other"]),
    ],
)
def test_all_body_bindings_are_closed(
    prepared_body: tuple[Intent, bytes],
    path: str,
    replacement: Any,
) -> None:
    import json

    from nima.identity.artifacts import encode

    intent, body = prepared_body
    value = json.loads(body)
    fields = path.split(".")
    target = value
    for key in fields[:-1]:
        target = target[key]
    target[fields[-1]] = replacement
    with pytest.raises(HistoryError):
        assessed_outcome(intent, encode(value))


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_check",
        "duplicate_count",
        "count_negative",
        "count_large",
        "limit_unsorted",
        "limit_on_ready",
    ],
)
def test_closed_rows_and_limitations(prepared_body: tuple[Intent, bytes], fault: str) -> None:
    import json

    from nima.identity.artifacts import encode

    intent, body = prepared_body
    value = json.loads(body)
    result = value["assessment"]
    if fault == "duplicate_check":
        result["checks"][1] = result["checks"][0]
    elif fault == "duplicate_count":
        result["counts"][1] = result["counts"][0]
    elif fault == "count_negative":
        result["counts"][0]["value"] = -1
    elif fault == "count_large":
        result["counts"][0]["value"] = 2**63
    elif fault == "limit_unsorted":
        result["limitations"] = ["partial_capture"] * 2
    else:
        result["limitations"] = ["partial_capture"]
    with pytest.raises(HistoryError):
        assessed_outcome(intent, encode(value))
