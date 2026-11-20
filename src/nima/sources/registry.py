"""The one place that knows which adapters exist; the engine asks here instead of importing one.

A concrete source module is imported only by this registry and by that source's own code. The
engine (storage, ingestion, replay, projection) depends on ``nima.sources.base`` and on this
registry, so adding a source means adding an adapter and one line here, not changing the engine.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from nima.sources.base import PayloadSource, SourceAdapter
from nima.sources.kimdis import KimdisAdapter

DEFAULT_SOURCE = "kimdis"
# The default source's processing identity, exported for the many modules that store or check it.
DEFAULT_NORMALIZER_VERSION = KimdisAdapter.normalizer_version


@dataclass(frozen=True)
class RegisteredSource:
    connector_version: str  # identifies the adapter a saved run belongs to
    create: Callable[[PayloadSource | None], SourceAdapter]
    from_payload: Callable[[Mapping[str, object]], SourceAdapter]


_SOURCES: dict[str, RegisteredSource] = {
    KimdisAdapter.name: RegisteredSource(
        KimdisAdapter.connector_version, KimdisAdapter, KimdisAdapter.from_payload
    ),
}


class UnknownSourceError(ValueError):
    """A source name that has no registered adapter."""


def known_sources() -> tuple[str, ...]:
    return tuple(sorted(_SOURCES))


def adapter_for(name: str, query: PayloadSource | None = None) -> SourceAdapter:
    source = _SOURCES.get(name)
    if source is None:
        raise UnknownSourceError("unknown source adapter")
    return source.create(query)


def adapter_from_run(connector_version: str, payload: Mapping[str, object]) -> SourceAdapter:
    """The adapter a saved run was created with, rebuilt from its connector version and query.

    An unregistered connector version raises ``UnknownSourceError``; a payload the source cannot
    read raises ``ValueError``. Both are raised before any request is made.
    """
    for source in _SOURCES.values():
        if source.connector_version == connector_version:
            return source.from_payload(payload)
    raise UnknownSourceError("unknown source adapter")


def default_adapter(query: PayloadSource | None = None) -> SourceAdapter:
    return adapter_for(DEFAULT_SOURCE, query)
