"""Fields every cohort-based request shares: explicit runs, a UTC cutoff and archive roots."""

from datetime import datetime
from typing import cast
from uuid import UUID

from nima.analytics.request import (
    RequestError,
    cutoff_value,
    path_value,
    uuid_value,
)
from nima.graph.pilot_archive import ArchiveBinding


def cohort_fields(
    data: dict[str, object],
) -> tuple[tuple[UUID, ...], datetime, tuple[ArchiveBinding, ...]]:
    """Validate the run IDs, cutoff and archive bindings of a decoded request."""
    raw_runs, raw_bindings = data["run_ids"], data["archive_bindings"]
    if (
        not isinstance(raw_runs, list)
        or not 1 <= len(raw_runs) <= 10
        or not isinstance(raw_bindings, list)
    ):
        raise RequestError("analytics_input")
    runs = tuple(sorted(uuid_value(run) for run in raw_runs))
    if len(set(runs)) != len(runs):
        raise RequestError("analytics_input")
    bindings = []
    for binding in raw_bindings:
        if not isinstance(binding, dict) or set(binding) != {"run_id", "root"}:
            raise RequestError("analytics_input")
        fields = cast(dict[str, object], binding)
        bindings.append(
            ArchiveBinding("kimdis", uuid_value(fields["run_id"]), path_value(fields["root"]))
        )
    if sorted(binding.run_id for binding in bindings) != list(runs):
        raise RequestError("analytics_input")
    return (
        runs,
        cutoff_value(data["observation_cutoff"]),
        tuple(sorted(bindings, key=lambda binding: binding.run_id)),
    )
