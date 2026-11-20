"""An adapter says what to ask and where it came from; the engine refuses anything unsafe first.

The guard runs before any network call, so a mis-wired adapter cannot send traffic to a host it
did not declare, put credentials in a recorded URL, or record provenance that is not a clean,
single-line statement. A refusal is a programming error (``SourceRequestError``), never a
stored run failure.
"""

from dataclasses import replace
from typing import Any, cast

import pytest

from nima.sources.base import (
    DEFAULT_MAX_BYTES,
    NormalizedPage,
    SourcePageError,
    SourceProvenance,
    SourceRequest,
    SourceRequestError,
    checked_provenance,
    checked_request,
)

ENDPOINT = "https://feed.example.invalid/v1/items"
PROVENANCE = SourceProvenance(
    endpoint=ENDPOINT,
    documentation_url="https://feed.example.invalid/docs",
    license="CC BY 4.0",
)
REQUEST = SourceRequest(
    method="POST",
    url=ENDPOINT,
    params={"page": 0},
    json={"q": "x"},
    accept="application/json",
)


class FakeAdapter:
    name = "fake"
    connector_version = "fake-connector-v1"
    normalizer_version = "fake-normalized-v1"

    def __init__(self, provenance: SourceProvenance = PROVENANCE, request: SourceRequest = REQUEST):
        self.provenance, self.request = provenance, request

    def query_payload(self) -> dict[str, object]:
        return {}

    def request_for(self, page: int) -> SourceRequest:
        return replace(self.request, params={**self.request.params, "page": page})

    def normalize_page(self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES) -> NormalizedPage:
        raise SourcePageError("not used by the request guard")


class FixedAdapter(FakeAdapter):
    """Returns its request unchanged, so a test controls every field the guard sees."""

    def request_for(self, page: int) -> SourceRequest:
        return self.request


def test_a_valid_adapter_passes_and_the_request_carries_the_page() -> None:
    adapter = FakeAdapter()
    assert checked_provenance(adapter) == PROVENANCE
    assert checked_request(adapter, 3).params == {"page": 3}
    assert checked_request(adapter, 0).url == ENDPOINT


def test_a_get_without_a_body_is_valid() -> None:
    adapter = FakeAdapter(request=replace(REQUEST, method="GET", json=None, accept="text/csv"))
    assert checked_request(adapter, 1).method == "GET"


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://feed.example.invalid/v1/items",
        "ftp://feed.example.invalid/v1/items",
        "https://",
        "https:///v1/items",
        "https://user:secret@feed.example.invalid/v1/items",
        "https://user@feed.example.invalid/v1/items",
        "https://:secret@feed.example.invalid/v1/items",
        "https://feed.example.invalid/v1/items?token=abc",
        "https://feed.example.invalid/v1/items#frag",
        "https://feed.example.invalid:99999/v1/items",
        "https://[::1/v1/items",
        "https://feed.example.invalid/v1/ items",
        "https://feed.example.invalid/v1/items\n",
        "",
        "https://feed.example.invalid/" + "a" * 2100,
    ],
)
def test_an_unsafe_endpoint_is_refused_before_any_request(endpoint: str) -> None:
    adapter = FakeAdapter(
        provenance=replace(PROVENANCE, endpoint=endpoint), request=replace(REQUEST, url=endpoint)
    )
    with pytest.raises(SourceRequestError):
        checked_provenance(adapter)
    with pytest.raises(SourceRequestError):
        checked_request(adapter, 0)


@pytest.mark.parametrize(
    "change",
    [
        {"documentation_url": "http://feed.example.invalid/docs"},
        {"documentation_url": ""},
        {"documentation_url": "https://feed.example.invalid/docs\nInjected: 1"},
        {"license": ""},
        {"license": "CC BY\n4.0"},
        {"license": "x" * 2100},
    ],
)
def test_provenance_text_must_be_a_clean_single_line(change: dict[str, str]) -> None:
    with pytest.raises(SourceRequestError):
        checked_provenance(FakeAdapter(provenance=replace(PROVENANCE, **change)))


def test_a_request_to_a_different_url_than_the_declared_endpoint_is_refused() -> None:
    other = "https://elsewhere.example.invalid/v1/items"
    with pytest.raises(SourceRequestError):
        checked_request(FakeAdapter(request=replace(REQUEST, url=other)), 0)


@pytest.mark.parametrize(
    "change",
    [
        {"method": "DELETE"},
        {"method": "GET"},  # a GET must not carry a body
        {"accept": ""},
        {"accept": "application/json\nX: 1"},
        {"accept": "json"},
        {"params": {"": 1}},
        {"params": {"page": 1.5}},
        {"params": {"page": True}},
        {"params": {1: 1}},
        {"json": ["not", "a", "mapping"]},
    ],
)
def test_malformed_requests_are_refused(change: dict[str, Any]) -> None:
    with pytest.raises(SourceRequestError):
        checked_request(FixedAdapter(request=replace(REQUEST, **change)), 0)


@pytest.mark.parametrize("page", [-1, True, 1.0, "0", None])
def test_the_page_number_must_be_a_non_negative_integer(page: object) -> None:
    with pytest.raises(SourceRequestError):
        checked_request(FakeAdapter(), cast(int, page))


def test_the_refusal_names_no_source_content() -> None:
    adapter = FakeAdapter(request=replace(REQUEST, url="https://leak.example.invalid/secret-path"))
    with pytest.raises(SourceRequestError) as error:
        checked_request(adapter, 0)
    assert "leak" not in str(error.value) and "secret" not in str(error.value)


def test_a_provenance_or_request_of_the_wrong_type_is_refused() -> None:
    wrong_provenance = FakeAdapter()
    wrong_provenance.provenance = cast(SourceProvenance, {"endpoint": ENDPOINT})
    wrong_request = FixedAdapter(request=cast(SourceRequest, {"url": ENDPOINT}))
    with pytest.raises(SourceRequestError):
        checked_provenance(wrong_provenance)
    with pytest.raises(SourceRequestError):
        checked_request(wrong_provenance, 0)
    with pytest.raises(SourceRequestError):
        checked_request(wrong_request, 0)
