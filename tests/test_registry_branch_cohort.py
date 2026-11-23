"""L5c-1 on stored profile evidence: the registry's own is_branch flag reaches the comparison."""

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from nima.identity import registry_cohort
from nima.identity.registry_report import build_report
from nima.ingestion.gemi import collect
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.gemi import import_run
from nima.storage.postgres import migrate
from tests.test_collection import Clock
from tests.test_gemi_contracts import profile
from tests.test_identity_report import seed
from tests.test_kimdis_pages import record

AFM = "001234567"
ISSUE = "multiple_registry_numbers_for_reported_afm"


def imported(dsn: str, path: Path, *, second_is_branch: bool | None) -> UUID:
    """One import of two companies that report the same AFM; the second one's flag varies."""

    def handle(request: httpx.Request) -> httpx.Response:
        number = int(request.url.path.rsplit("/", 1)[1])
        changes: dict[str, object] = {"afm": AFM}
        if number == 1:
            changes["isBranch"] = False
        elif second_is_branch is not None:
            changes["isBranch"] = second_is_branch
        return httpx.Response(
            200, content=profile(number, **changes), headers={"content-type": "application/json"}
        )

    root = path / "gemi"
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = collect(
            ("1", "2"), root, api_key="synthetic-test-credential", client=client, clock=Clock()
        )
    run = UUID(result.run_id)
    import_run(dsn, root, run)
    return run


def outcome(dsn: str, path: Path, selected: UUID) -> tuple[str, int, tuple[str, ...]]:
    rows = [
        {
            **record("1"),
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": "Synthetic", "vatNumber": AFM, "country": {"key": "GR"}}
                ]
            },
        }
    ]
    run = seed(dsn, path, *rows)
    report: dict[str, Any] = dict(
        build_report(
            registry_cohort.read_comparison_cohort(dsn, run, (selected,), PROJECTION_VERSION)
        )
    )
    (supplier,) = [o for o in report["occurrences"] if o["role"] == "supplier"]
    comparison = supplier["comparison"]
    return (
        comparison["outcome"],
        len(comparison["registry_observation_refs"]),
        tuple(comparison["issues"]),
    )


@pytest.mark.parametrize(
    ("second", "issues"),
    [(True, ()), (False, (ISSUE,)), (None, (ISSUE,))],
    ids=["branch", "second-head-office", "unknown"],
)
def test_a_stored_profiles_branch_flag_decides_whether_a_shared_afm_is_a_conflict(
    pg_dsn: str, tmp_path: Path, second: bool | None, issues: tuple[str, ...]
) -> None:
    migrate(pg_dsn)
    selected = imported(pg_dsn, tmp_path, second_is_branch=second)
    assert outcome(pg_dsn, tmp_path, selected) == ("reported_identifier_agreement", 2, issues)
