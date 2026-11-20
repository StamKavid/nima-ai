"""Shared record selection: the latest observed revision of each source record.

"Latest" always means latest observed within the given cohort and inclusive UTC cutoff; it never
means source-current or legally effective, and source date text is never an ordering key. The
cutoff is applied first, then the latest observed time is chosen per source ID, before any other
filter. Identical versions collapse; different versions tied at that time are ambiguous and both
stay visible, so a caller can exclude the record and report the conflict instead of choosing a
winner by row order or hash.

Only four facts are needed, so any source's observations can be selected the same way.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class Observed(Protocol):
    @property
    def source_id(self) -> str: ...

    @property
    def observation_id(self) -> int: ...

    @property
    def content_sha256(self) -> str: ...

    @property
    def observed_at(self) -> datetime: ...


@dataclass(frozen=True)
class Selected[T: Observed]:
    source_id: str
    current: tuple[T, ...]
    versions: Mapping[str, T]

    @property
    def ambiguous(self) -> bool:
        return len(self.versions) != 1

    @property
    def chosen(self) -> T:
        """The first observation at the latest time; meaningful when the record is not ambiguous."""
        return self.current[0]


def _select[T: Observed](source_id: str, rows: list[T]) -> Selected[T]:
    latest = max(row.observed_at for row in rows)
    current = tuple(row for row in rows if row.observed_at == latest)
    return Selected(source_id, current, {row.content_sha256: row for row in current})


def select_latest[T: Observed](
    observations: Iterable[T], cutoff: datetime
) -> tuple[Selected[T], ...]:
    """Observations at or before ``cutoff``, one selection per source ID, in source ID order."""
    grouped: dict[str, list[T]] = {}
    for row in observations:
        if row.observed_at <= cutoff:
            grouped.setdefault(row.source_id, []).append(row)
    return tuple(_select(source_id, grouped[source_id]) for source_id in sorted(grouped))
