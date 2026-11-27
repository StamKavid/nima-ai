"""Recorded execution is distinct from data fitness and current policy defaults."""

from dataclasses import replace
from pathlib import Path

import pytest

from nima.contracts.acceptance_history import HistoryError, Intent, Outcome, decode_intent


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
