"""The one place that knows which adapters exist; the engine asks here instead of importing one.

A concrete source module is imported only by this registry and by that source's own code. The
engine (storage, ingestion, replay, projection) depends on ``nima.sources.base`` and on this
registry, so adding a source means adding an adapter and one line here, not changing the engine.
"""

from collections.abc import Callable

from nima.sources.base import PayloadSource, SourceAdapter
from nima.sources.kimdis import KimdisAdapter

DEFAULT_SOURCE = "kimdis"
# The default source's processing identity, exported for the many modules that store or check it.
DEFAULT_NORMALIZER_VERSION = KimdisAdapter.normalizer_version

_ADAPTERS: dict[str, Callable[[PayloadSource | None], SourceAdapter]] = {
    KimdisAdapter.name: KimdisAdapter,
}


class UnknownSourceError(ValueError):
    """A source name that has no registered adapter."""


def known_sources() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def adapter_for(name: str, query: PayloadSource | None = None) -> SourceAdapter:
    factory = _ADAPTERS.get(name)
    if factory is None:
        raise UnknownSourceError("unknown source adapter")
    return factory(query)


def default_adapter(query: PayloadSource | None = None) -> SourceAdapter:
    return adapter_for(DEFAULT_SOURCE, query)
