"""Fictional verified-provider frames for insight composition, never certification."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from nima.analytics.buyer_request import BuyerRequest
from nima.dataops import buyer_acceptance
from nima.dataops.buyer_acceptance import PreparedBuyerAcceptance
from nima.semantics.participation import Supplier
from tests.buyer_acceptance_samples import observation, producer
from tests.test_citation_acceptance import subject


def frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, unknown: bool = False
) -> tuple[BuyerRequest, bytes, PreparedBuyerAcceptance]:
    suppliers = (("111111111",), ("222222222",), ("111111111", "222222222"))
    rows = tuple(
        replace(
            observation(i),
            source_id=f"kimdis:fictional-{i}",
            content_sha256=hashlib.sha256(str(i).encode()).hexdigest(),
            suppliers=tuple(Supplier(j, tax, "GR") for j, tax in enumerate(taxes)),
        )
        for i, taxes in enumerate(suppliers, 1)
    )
    if unknown:
        rows += (replace(observation(4), source_id="kimdis:fictional-4", suppliers=None),)
    request, fresh = producer(rows)
    monkeypatch.setattr(buyer_acceptance, "prepare_buyer_result", lambda *_: fresh)
    path = subject(tmp_path / "reports", fresh.body)
    return request, fresh.body, buyer_acceptance.prepare_buyer_acceptance("fixture", request, path)


def certified(
    parent: bytes, fresh: PreparedBuyerAcceptance
) -> tuple[bytes, PreparedBuyerAcceptance]:
    """Hypothetical compatible certified profile, only for private-composer tests."""
    import json

    from nima.analytics.metric_readout import definition_hash
    from nima.identity.artifacts import encode

    report, sidecar = json.loads(parent), json.loads(fresh.body)
    report["metric"]["definition"]["status"] = "certified"
    definition_hash_value = definition_hash(report["metric"]["definition"])
    report["metric"]["definition_sha256"] = definition_hash_value
    policy = sidecar["policy"]["definition"]
    policy["version"] = "fixture-only-certified"
    policy["uses"]["U3"]["definition_sha256"] = definition_hash_value
    policy_hash = hashlib.sha256(encode(policy)).hexdigest()
    parent = encode(report)
    subject_hash = hashlib.sha256(parent).hexdigest()
    assessment = replace(
        fresh.assessment,
        definition_sha256=definition_hash_value,
        policy_sha256=policy_hash,
        policy_version="fixture-only-certified",
    )
    sidecar["subject"]["artifact_sha256"] = subject_hash
    sidecar["subject"]["metric"].update(status="certified", definition_sha256=definition_hash_value)
    sidecar["policy"]["definition_sha256"] = policy_hash
    from dataclasses import asdict

    sidecar["assessment"] = asdict(assessment)
    return parent, replace(
        fresh, body=encode(sidecar), assessment=assessment, subject_sha256=subject_hash
    )
