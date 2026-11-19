"""Source-neutral page types and the adapter protocol the acquisition engine depends on.

An adapter knows one source's wire format and nothing about transport or storage; the engine
knows archiving, checkpoints, leases, the outbox and quarantine and nothing about a source's
fields. This module imports nothing from the rest of the project so either side may use it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

DEFAULT_MAX_BYTES = 8 * 1024 * 1024


class SourcePageError(ValueError):
    """The page envelope is unusable (bad framing, pagination, size or source contract).

    A bad individual record is not this error: it becomes a ``PageIssue`` and is quarantined,
    while the raw page bytes are kept.
    """


@dataclass(frozen=True)
class NormalizedRecord:
    index: int  # position of the record in the source page
    source_id: str  # namespaced, for example "kimdis:<reference>"
    content_sha256: str  # hash of the parsed source content of this record only
    normalized: Mapping[str, object]  # JSON-ready; money as exact decimal text, never float


@dataclass(frozen=True)
class PageIssue:
    index: int
    reason: str  # fixed text; never copies source content


@dataclass(frozen=True)
class NormalizedPage:
    number: int
    size: int
    total_records: int
    total_pages: int
    last: bool
    record_count: int
    records: tuple[NormalizedRecord, ...]
    issues: tuple[PageIssue, ...]
    source_ids: tuple[str, ...]  # identifiers seen on the page, including quarantined records


class SourceAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def connector_version(self) -> str: ...

    @property
    def normalizer_version(self) -> str: ...

    def query_payload(self) -> dict[str, object]: ...

    def normalize_page(
        self, raw: bytes, *, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> NormalizedPage: ...
