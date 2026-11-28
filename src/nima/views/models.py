"""Immutable presentation inputs; independent of preparation and HTML rendering."""

from dataclasses import dataclass, field

from nima.insights.buyer_participation import Status

MAX_HTML_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class PreparedViewEntry:
    label: str
    report_body: bytes = field(repr=False)
    insight_body: bytes = field(repr=False)
    assessment_body: bytes = field(repr=False)
    status: Status


@dataclass(frozen=True)
class PreparedBuyerView:
    entries: tuple[PreparedViewEntry, ...]
    originals: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True)
class BuyerViewExport:
    artifact_sha256: str
    entry_states: tuple[Status, ...]
