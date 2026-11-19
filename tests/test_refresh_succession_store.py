"""An explicit approval creates one paused generation, retaining original evidence."""

from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.storage.refresh_lifecycle import retire
from nima.storage.refresh_succession import supersede
from nima.storage.workflows import WorkflowError
from tests.test_graph_support import database_snapshot
from tests.test_refresh_store import new_policy


def retired(dsn: str, root: Path) -> tuple[UUID, UUID]:
    _, old = new_policy(dsn, root)
    retire(dsn, old, "operator_stop")
    return old, uuid4()


def test_atomic_fresh_successor_retains_scope_and_original_generation(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.storage.refresh import RefreshStore

    old, new = retired(pg_dsn, tmp_path / "raw")
    before = database_snapshot(pg_dsn)
    result = supersede(pg_dsn, old, new, authorize_new_budgets=True)
    assert result["successor_state"] == "paused" and result["reused"] is False
    assert result["budget_profile"] == "nima-refresh-budgets-v1"
    assert result["new_budgets_authorized"] is True
    assert result["predecessor_id"] == str(old) and result["successor_id"] == str(new)
    assert "database_principal" not in result and str(tmp_path) not in str(result)
    store = RefreshStore(pg_dsn)
    assert store.options(old) == store.options(new)
    after = database_snapshot(pg_dsn)
    for table in before.keys() - {"refresh_policies", "refresh_events", "refresh_successions"}:
        assert after[table] == before[table]
    assert all(row in after["refresh_policies"] for row in before["refresh_policies"])
    assert len(after["refresh_policies"]) == 2 and len(after["refresh_successions"]) == 1
    assert not (tmp_path / "raw").exists()


def test_reuse_preserves_approval_after_activation_and_runtime_change(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.storage import refresh_succession
    from nima.storage.refresh import RefreshStore

    old, new = retired(pg_dsn, tmp_path / "raw")
    first = supersede(pg_dsn, old, new, authorize_new_budgets=True)
    with RefreshStore(pg_dsn).lease(new) as session:
        session.state("enabled")
    before = database_snapshot(pg_dsn)

    def forbidden(*args: object) -> None:
        pytest.fail("A reused approval was reinterpreted as new work")

    monkeypatch.setattr(refresh_succession, "policy_parameters", forbidden)
    again = supersede(pg_dsn, old, new, authorize_new_budgets=True)
    assert again == {**first, "reused": True, "successor_state": "enabled"}
    assert database_snapshot(pg_dsn) == before


@pytest.mark.parametrize(
    "fault", ["authorization", "same", "existing", "not_retired", "other_target"]
)
def test_invalid_authority_or_identity_leaves_no_partial_successor(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    store, old = new_policy(pg_dsn, tmp_path / "raw")
    new = uuid4()
    expected = "succession_conflict"
    if fault != "not_retired":
        retire(pg_dsn, old, "operator_stop")
    else:
        expected = "succession_not_retired"
    if fault == "same":
        new = old
    elif fault == "existing":
        store.create(new, store.options(old))
    elif fault == "other_target":
        supersede(pg_dsn, old, uuid4(), authorize_new_budgets=True)
    elif fault == "authorization":
        expected = "succession_authorization"
    before = database_snapshot(pg_dsn)
    with pytest.raises(WorkflowError, match="^" + expected + "$"):
        supersede(pg_dsn, old, new, authorize_new_budgets=fault != "authorization")
    assert database_snapshot(pg_dsn) == before


@pytest.mark.parametrize("operation", ["update", "delete", "truncate", "cascade"])
def test_authorization_is_immutable_even_for_owner(
    pg_dsn: str, tmp_path: Path, operation: str
) -> None:
    old, new = retired(pg_dsn, tmp_path / "raw")
    supersede(pg_dsn, old, new, authorize_new_budgets=True)
    statements = {
        "update": "UPDATE nima.refresh_successions SET budget_profile=budget_profile",
        "delete": "DELETE FROM nima.refresh_successions",
        "truncate": "TRUNCATE nima.refresh_successions",
        "cascade": "TRUNCATE nima.refresh_policies CASCADE",
    }
    with psycopg.connect(pg_dsn) as c, pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        c.execute(statements[operation])
