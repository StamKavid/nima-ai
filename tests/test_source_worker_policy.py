"""The fixture profile cannot select a live source or broaden its budgets."""

from dataclasses import FrozenInstanceError

import pytest

from nima.egress.policy import CASES, PolicyError, fixture_policy


def test_fixture_policy_is_immutable_bounded_and_reproducible() -> None:
    first = fixture_policy({"version": "source-worker-policy-v1", "profile": "fixtures"})
    second = fixture_policy({"profile": "fixtures", "version": "source-worker-policy-v1"})
    assert first == second
    assert first.digest == second.digest
    assert len(first.digest) == 64
    assert first.gateway_ip == "172.30.240.2"
    assert first.gateway_port == 3128
    assert first.attempt_seconds == 15
    assert first.max_seconds == 600
    assert first.max_response_bytes == 1024**2
    assert first.max_receipt_bytes == 64 * 1024
    assert len(CASES) == len({case.name for case in CASES}) <= 30
    for name in ("gateway_ip", "max_seconds"):
        with pytest.raises(FrozenInstanceError):
            setattr(first, name, "private-secret")


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        "fixtures",
        {"version": "source-worker-policy-v1", "profile": "live"},
        {"version": "source-worker-policy-v1", "profile": "fixtures", "target": "private-secret"},
        {"version": "source-worker-policy-v1", "profile": "fixtures", "bypass": "*"},
        {"version": "source-worker-policy-v1", "profile": "fixtures", "timeout": 999999},
        {"version": "source-worker-policy-v1", "profile": True},
    ],
)
def test_arbitrary_targets_options_or_missing_configuration_fail(value: object) -> None:
    with pytest.raises(PolicyError, match="^policy$"):
        fixture_policy(value)
