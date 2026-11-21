"""Run-cohort fields shared by every readout request: bounds, duplicates and archive bindings."""

import json
from typing import Any
from uuid import uuid4

import pytest

from nima.analytics.buyer_request import decode_buyer_request
from nima.analytics.request import RequestError


def payload(count: int) -> dict[str, Any]:
    runs = [str(uuid4()) for _ in range(count)]
    return {
        "version": "nima-buyer-concentration-request-v1",
        "source": "kimdis.contract",
        "run_ids": runs,
        "observation_cutoff": "2026-06-01T00:00:00+00:00",
        "buyer": "B1",
        "archive_bindings": [{"run_id": run, "root": f"/archive/{run}"} for run in runs],
    }


def test_one_to_ten_runs_are_accepted_and_sorted() -> None:
    for count in (1, 10):
        request = decode_buyer_request(json.dumps(payload(count)).encode())
        assert len(request.run_ids) == count == len(request.archive_bindings)
        assert list(request.run_ids) == sorted(request.run_ids)
        assert [b.run_id for b in request.archive_bindings] == list(request.run_ids)


@pytest.mark.parametrize("count", [0, 11])
def test_zero_or_eleven_runs_are_refused(count: int) -> None:
    with pytest.raises(RequestError, match="^analytics_input$"):
        decode_buyer_request(json.dumps(payload(count)).encode())


def test_a_missing_or_extra_binding_is_refused() -> None:
    fewer = payload(2)
    fewer["archive_bindings"].pop()
    more = payload(2)
    more["archive_bindings"].append({"run_id": str(uuid4()), "root": "/archive/x"})
    for body in (fewer, more):
        with pytest.raises(RequestError, match="^analytics_input$"):
            decode_buyer_request(json.dumps(body).encode())
