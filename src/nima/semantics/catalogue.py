"""The metric catalogue: every metric, its status and the hashes that bind its definition.

The catalogue is read-only and holds no rule of its own; each entry is computed from the metric's
own module, so the published page cannot drift from the code without a test failing. Status moves
only by an owner decision: ``reviewed`` needs a dated review record on the catalogue page and
``certified`` a recorded real-data reconciliation, and tests refuse a promotion that leaves neither.
"""

from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import cast

from nima.semantics import buyer_concentration, cpv_period, observed_change, participation


@dataclass(frozen=True)
class CatalogueEntry:
    scenario: str
    metric_id: str
    status: str
    definition_sha256: str
    sql_sha256: str
    provider: str
    document: str


_METRICS: tuple[tuple[str, ModuleType, str], ...] = (
    ("U1", participation, "docs/semantics/participation.md"),
    ("U2", cpv_period, "docs/semantics/cpv-period.md"),
    ("U3", buyer_concentration, "docs/semantics/buyer-concentration.md"),
    ("U4", observed_change, "docs/semantics/observed-change.md"),
)


def entries() -> tuple[CatalogueEntry, ...]:
    result = []
    for scenario, module, document in _METRICS:
        definition = cast(Callable[[], dict[str, object]], module.definition)()
        digest = cast(Callable[[], str], module.definition_sha256)()
        result.append(
            CatalogueEntry(
                scenario,
                str(definition["metric"]),
                str(definition["status"]),
                digest,
                str(definition["sql_sha256"]),
                module.__name__,
                document,
            )
        )
    return tuple(result)
