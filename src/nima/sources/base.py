"""Source-neutral page types and the adapter protocol the acquisition engine depends on.

An adapter knows one source's wire format and nothing about transport or storage; the engine
knows archiving, checkpoints, leases, the outbox and quarantine and nothing about a source's
fields. This module imports nothing from the rest of the project so either side may use it.
"""

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import urlsplit

DEFAULT_MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT = 2048
ACCEPT = re.compile(r"^[a-z]+/[a-z0-9.+-]+$")
INVALID = "source_request_invalid"


class SourcePageError(ValueError):
    """The page envelope is unusable (bad framing, pagination, size or source contract).

    A bad individual record is not this error: it becomes a ``PageIssue`` and is quarantined,
    while the raw page bytes are kept.
    """


@dataclass(frozen=True)
class NormalizedRecord:
    index: int  # position of the record in the source page
    evidence_pointer: str  # source-defined locator of the record inside the archived response
    source_id: str  # namespaced, for example "kimdis:<reference>"
    content_sha256: str  # hash of the parsed source content of this record only
    normalized: Mapping[str, object]  # JSON-ready; money as exact decimal text, never float


@dataclass(frozen=True)
class PageIssue:
    index: int
    evidence_pointer: str
    reason: str  # fixed text; never copies source content


@dataclass(frozen=True)
class NormalizedPage:
    number: int
    size: int
    total_records: int
    total_pages: int
    last: bool
    record_count: int
    response_sha256: str  # hash of the archived response bytes the pointers refer to
    records: tuple[NormalizedRecord, ...]
    issues: tuple[PageIssue, ...]
    source_ids: tuple[str, ...]  # identifiers seen on the page, including quarantined records
    record_hashes: tuple[str, ...]  # content hash of every record on the page, by index


class SourceRequestError(ValueError):
    """An adapter's provenance or request is unsafe or inconsistent.

    Raised before any network call, as a programming error in the adapter. The message is fixed
    and never repeats what the adapter supplied.
    """


@dataclass(frozen=True)
class SourceProvenance:
    """Where a source's data comes from, recorded in every archive manifest it produces."""

    endpoint: str  # base URL every request goes to; https only, no credentials or query string
    documentation_url: str  # recorded in the manifest as "source"
    license: str  # as the publisher states it


@dataclass(frozen=True)
class SourceRequest:
    """What to ask for one page. The engine decides how: timeouts, limits, retries, archiving."""

    method: Literal["GET", "POST"]
    url: str  # must equal the adapter's provenance.endpoint
    params: Mapping[str, str | int]
    json: Mapping[str, object] | None  # a GET carries no body
    accept: str  # media type, for example "application/json" or "text/csv"


class PayloadSource(Protocol):
    """Anything that can describe its request as a JSON payload (for example a run's query)."""

    def payload(self) -> dict[str, object]: ...


class QueryPayload:
    """A run's saved query as plain JSON, for code that holds the payload but no query object.

    The payload is copied on the way in and on the way out, so neither side can change it.
    """

    def __init__(self, value: Mapping[str, object]) -> None:
        self._value: dict[str, object] = deepcopy(dict(value))

    def payload(self) -> dict[str, object]:
        return deepcopy(self._value)


class SourceAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def connector_version(self) -> str: ...

    @property
    def normalizer_version(self) -> str: ...

    @property
    def provenance(self) -> SourceProvenance: ...

    def query_payload(self) -> dict[str, object]: ...

    def request_for(self, page: int) -> SourceRequest: ...

    def normalize_page(
        self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> NormalizedPage: ...


def _text(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT or not value.isprintable():
        raise SourceRequestError(INVALID)
    return value


def _https_url(value: object) -> str:
    text = _text(value)
    try:
        parts = urlsplit(text)
        parts.port  # noqa: B018 - validates the port; an invalid one raises ValueError
    except ValueError:
        raise SourceRequestError(INVALID) from None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None  # any userinfo, a password-only one included
        or parts.query
        or parts.fragment
        or any(c.isspace() for c in text)
    ):
        raise SourceRequestError(INVALID)
    return text


def checked_provenance(adapter: SourceAdapter) -> SourceProvenance:
    """The adapter's provenance, refused unless every field is a clean single-line statement."""
    provenance = adapter.provenance
    if not isinstance(provenance, SourceProvenance):
        raise SourceRequestError(INVALID)
    _https_url(provenance.endpoint)
    _https_url(provenance.documentation_url)
    _text(provenance.license)
    return provenance


def checked_request(adapter: SourceAdapter, page: int) -> SourceRequest:
    """The request for one page, refused before any network call unless it is safe and consistent.

    It must be a GET or POST to exactly the endpoint the adapter declared, with an ordinary media
    type, simple parameters and, for a POST only, a JSON object body.
    """
    if type(page) is not int or page < 0:
        raise SourceRequestError(INVALID)
    provenance = checked_provenance(adapter)
    request = adapter.request_for(page)
    if (
        not isinstance(request, SourceRequest)
        or request.method not in ("GET", "POST")
        or request.url != provenance.endpoint
        or not ACCEPT.match(_text(request.accept))
        or not isinstance(request.params, Mapping)
        or (request.json is not None and not isinstance(request.json, Mapping))
        or (request.method == "GET" and request.json is not None)
    ):
        raise SourceRequestError(INVALID)
    for key, value in request.params.items():
        _text(key)
        if type(value) is not int:
            _text(value)
    return request
