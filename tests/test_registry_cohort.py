"""Read selected procurement/registry assertions through one real SQL snapshot."""

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Never, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql

from nima.identity import AssessmentError, ComparisonError, registry_cohort
from nima.projections.worker import PROJECTION_VERSION, drain
from nima.sources.gemi import Assertion, normalize_profile
from nima.storage.gemi import import_run
from nima.storage.postgres import Connection
from tests.test_collection import QUERY, body
from tests.test_gemi_contracts import profile
from tests.test_gemi_import import counts as registry_counts
from tests.test_gemi_import_archive import archive_run, snapshot
from tests.test_identity_report import seed
from tests.test_kimdis_pages import record
from tests.test_page_store import counts as procurement_counts
from tests.test_page_store import store


def registry_import(dsn: str, path: Path, raw: bytes | None = None) -> UUID:
    root = path / "gemi"
    run = archive_run(root, raw)
    import_run(dsn, root, run)
    return run


def test_selected_snapshot_preserves_assertions_dates_provenance_and_unknowns(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(
        pg_dsn,
        tmp_path,
        {
            **record(),
            "submissionDate": "2020-01-02",
            "lastUpdateDate": None,
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": " Άλφα ΑΕ ", "vatNumber": "001234567", "country": {"key": "GR"}}
                ]
            },
        },
    )
    raw = profile(incorporationDate="1999-01-01", lastStatusChange=None)
    selected = registry_import(pg_dsn, tmp_path, raw)
    registry_import(pg_dsn, tmp_path, profile(coNameEl="Unselected"))
    before = procurement_counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")
    cohort = registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
    assert cohort.run_id == run and cohort.projection_version == PROJECTION_VERSION
    assert len(cohort.parties) == cohort.coverage["expected_mentions"] == 2
    assert all(party.source_submitted_at == "2020-01-02" for party in cohort.parties)
    assert all(party.source_updated_at is None for party in cohort.parties)
    assert all(party.json_pointer == "/content/0" for party in cohort.parties)
    assert cohort.parties[1].claim()["name"] == " Άλφα ΑΕ "
    assert len(cohort.imports) == 1 and cohort.imports[0].import_id == selected
    assert cohort.imports[0].license == "ODC-BY-1.0"
    assert len(cohort.imports[0].manifest_sha256) == 64
    found, missing = cohort.registry
    assert found.claim.import_id == missing.claim.import_id == selected
    assert found.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert found.source_id == "gemi:1" and found.normalizer_version == "gemi-company-v1"
    assert found.fields["name_el"] == Assertion("  Άλφα ΑΕ ", "/coNameEl")
    assert found.fields["incorporation_date"] == Assertion("1999-01-01", "/incorporationDate")
    assert found.fields["last_status_change"] == Assertion(None, "/lastStatusChange")
    assert found.fields["is_branch"] == Assertion(None, None)
    assert "names_en" not in found.fields and "activities" not in found.fields
    assert found.observed_at != cohort.imports[0].imported_at
    assert missing.claim.outcome == "not_found_at_observation" and missing.status == 404
    assert missing.source_id is missing.normalizer_version is None and not missing.fields
    with pytest.raises(TypeError):
        cast(dict[str, Assertion], found.fields)["name_el"] = Assertion("changed", None)
    assert (
        procurement_counts(pg_dsn),
        registry_counts(pg_dsn),
        snapshot(tmp_path / "gemi"),
    ) == before


@pytest.mark.parametrize(
    "fault", ["empty", "duplicate", "too_many", "wrong_type", "version", "budget"]
)
def test_invalid_selectors_fail_before_database_access(fault: str) -> None:
    imports: tuple[UUID, ...] = (uuid4(),)
    version = PROJECTION_VERSION
    limit = 10000
    if fault == "empty":
        imports = ()
    elif fault == "duplicate":
        imports = (imports[0], imports[0])
    elif fault == "too_many":
        imports = tuple(uuid4() for _ in range(11))
    elif fault == "wrong_type":
        imports = (cast(UUID, "private-sentinel"),)
    elif fault == "version":
        version = "private-sentinel"
    else:
        limit = 0
    with pytest.raises(ValueError, match="comparison_configuration"):
        registry_cohort.read_comparison_cohort(
            "private-sentinel", uuid4(), imports, version, max_mentions=limit
        )


def test_missing_selected_import_is_not_silently_ignored(pg_dsn: str, tmp_path: Path) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with pytest.raises(ComparisonError, match="registry_import_unavailable"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected, uuid4()), PROJECTION_VERSION)


def test_selected_fields_preserve_null_pointers_and_omit_aliases_without_mutation() -> None:
    fields = normalize_profile(profile(afm=None, lastStatusChange=None), "1").payload()["fields"]
    before = deepcopy(fields)
    selected = registry_cohort._fields(fields, "1")
    assert fields == before
    assert selected["reported_afm"] == Assertion(None, "/afm")
    assert selected["last_status_change"] == Assertion(None, "/lastStatusChange")
    assert selected["is_branch"] == Assertion(None, None)
    assert selected["name_el"] == Assertion("  Άλφα ΑΕ ", "/coNameEl")
    assert len(selected) == 11 and "names_en" not in selected
    with pytest.raises(TypeError):
        cast(dict[str, Assertion], selected)["reported_afm"] = Assertion("changed", "/afm")


@pytest.mark.parametrize(
    "field,member,value",
    [
        ("reported_afm", "value", 23),
        ("is_branch", "value", 0),
        ("legal_type_id", "value", True),
        ("incorporation_date", "value", "2026-02-30"),
        ("last_status_change", "value", "20261110"),
        ("reported_afm", "json_pointer", "/private-sentinel"),
        ("reported_afm", "json_pointer", None),
        ("registry_number", "value", 2),
    ],
)
def test_malformed_selected_assertions_fail_with_fixed_reason(
    field: str, member: str, value: object
) -> None:
    fields = cast(
        dict[str, dict[str, object]], normalize_profile(profile(), "1").payload()["fields"]
    )
    fields[field][member] = value
    with pytest.raises(ComparisonError, match="registry_shape") as error:
        registry_cohort._fields(fields, "1")
    assert str(error.value) == "registry_shape"


def test_selector_order_and_repeated_versions_preserve_all_observations(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(
        pg_dsn,
        tmp_path,
        record("unknown"),
        {**record("empty"), "contractingDataDetails": {"contractingMembersDataList": []}},
    )
    selected = tuple(
        registry_import(pg_dsn, tmp_path, profile(afm=afm))
        for afm in ("001234567", "123456789", "001234567")
    )
    first = registry_cohort.read_comparison_cohort(pg_dsn, run, selected, PROJECTION_VERSION)
    assert (
        registry_cohort.read_comparison_cohort(
            pg_dsn, run, tuple(reversed(selected)), PROJECTION_VERSION
        )
        == first
    )
    assert len(first.registry) == 6 and len(first.parties) == 2
    found = {row.claim.import_id: row for row in first.registry if row.claim.outcome == "found"}
    assert [found[item].claim.reported_afm for item in selected] == [
        "001234567",
        "123456789",
        "001234567",
    ]
    assert found[selected[0]].raw_sha256 == found[selected[2]].raw_sha256
    assert first.coverage["unknown_supplier_lists"] == first.coverage["empty_supplier_lists"] == 1


def test_cohort_excludes_later_collection_and_imports_from_another_connection(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, body(), observed_at=datetime.now(UTC))
    drain(pg_dsn)
    selected = registry_import(pg_dsn, tmp_path)
    original = registry_cohort._preflight

    def concurrent_append(
        connection: Connection, selected_run: UUID, imports: tuple[UUID, ...], version: str
    ) -> int:
        assert connection.execute("SHOW transaction_read_only").fetchone() == ("on",)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction), connection.transaction():
            connection.execute("UPDATE nima.ingest_runs SET next_page=next_page")
        reserved = original(connection, selected_run, imports, version)
        database.commit_page(run, body(page=1), observed_at=datetime.now(UTC))
        drain(pg_dsn)
        registry_import(pg_dsn, tmp_path, profile(coNameEl="Later"))
        return reserved

    monkeypatch.setattr(registry_cohort, "_preflight", concurrent_append)
    cohort = registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
    assert cohort.coverage["observation_count"] == len(cohort.parties) == 1
    assert len(cohort.registry) == 2 and {row.claim.import_id for row in cohort.registry} == {
        selected
    }
    monkeypatch.undo()
    assert (
        registry_cohort.read_comparison_cohort(
            pg_dsn, run, (selected,), PROJECTION_VERSION
        ).coverage["observation_count"]
        == 2
    )


def test_selected_import_committed_after_snapshot_is_not_mixed_into_it(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    root = tmp_path / "gemi"
    selected = archive_run(root)
    original = registry_cohort._preflight

    def concurrent_import(
        connection: Connection, selected_run: UUID, imports: tuple[UUID, ...], version: str
    ) -> int:
        assert connection.execute("SELECT count(*) FROM nima.gemi_imports").fetchone() == (0,)
        import_run(pg_dsn, root, selected)
        return original(connection, selected_run, imports, version)

    monkeypatch.setattr(registry_cohort, "_preflight", concurrent_import)
    with pytest.raises(ComparisonError, match="registry_import_unavailable"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
    assert registry_counts(pg_dsn) == (1, 2, 1, 2, 0)


@pytest.mark.parametrize(
    "fault", ["version", "source", "counts", "shape", "missing_field", "pointer"]
)
def test_unsupported_or_inconsistent_stored_registry_evidence_is_rejected(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        if fault in {"version", "source", "counts"}:
            connection.execute("ALTER TABLE nima.gemi_imports DISABLE TRIGGER USER")
            if fault == "version":
                connection.execute("UPDATE nima.gemi_imports SET normalizer_version='unsupported'")
            elif fault == "source":
                connection.execute("UPDATE nima.gemi_imports SET source_url='private-sentinel'")
            else:
                connection.execute("UPDATE nima.gemi_imports SET response_count=response_count+1")
        else:
            connection.execute("ALTER TABLE nima.gemi_profile_versions DISABLE TRIGGER USER")
            if fault == "shape":
                connection.execute(
                    "UPDATE nima.gemi_profile_versions SET normalized="
                    "jsonb_set(normalized, '{fields,reported_afm,value}', '23')"
                )
            elif fault == "pointer":
                connection.execute(
                    "UPDATE nima.gemi_profile_versions SET normalized="
                    "jsonb_set(normalized, '{fields,reported_afm,json_pointer}', "
                    "'\"/private-sentinel\"')"
                )
            else:
                connection.execute(
                    "UPDATE nima.gemi_profile_versions SET normalized="
                    "jsonb_set(normalized, '{fields}', "
                    "(normalized->'fields') - 'reported_afm')"
                )
    reason = (
        "registry_version"
        if fault in {"version", "source"}
        else ("registry_incomplete" if fault == "counts" else "registry_shape")
    )
    with pytest.raises(ComparisonError, match=reason) as error:
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
    assert "private-sentinel" not in str(error.value)


def test_missing_profile_reference_fails_instead_of_dropping_the_observation(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        constraint = connection.execute(
            "SELECT conname FROM pg_constraint WHERE "
            "conrelid='nima.gemi_observations'::regclass "
            "AND confrelid='nima.gemi_profile_versions'::regclass"
        ).fetchone()
        assert constraint is not None
        connection.execute(
            sql.SQL("ALTER TABLE nima.gemi_observations DROP CONSTRAINT {}").format(
                sql.Identifier(str(constraint[0]))
            )
        )
        connection.execute("ALTER TABLE nima.gemi_profile_versions DISABLE TRIGGER USER")
        connection.execute("DELETE FROM nima.gemi_profile_versions")
    with pytest.raises(ComparisonError, match="registry_incomplete"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)


@pytest.mark.parametrize("bound", ["bytes", "observations"])
def test_aggregate_bounds_fail_before_any_label_materialization(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    run = seed(pg_dsn, tmp_path, record())
    selected = registry_import(pg_dsn, tmp_path)
    monkeypatch.setattr(
        registry_cohort, "MAX_INPUT_BYTES" if bound == "bytes" else "MAX_REGISTRY_OBSERVATIONS", 1
    )

    def prohibited_transfer(*args: object, **kwargs: object) -> Never:
        raise AssertionError("evidence_transfer_before_budget")

    for name in ("read_cohort_in_transaction", "_parties", "_imports", "_registry_evidence"):
        monkeypatch.setattr(registry_cohort, name, prohibited_transfer)
    with pytest.raises(ComparisonError, match="comparison_limit"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)


def test_incomplete_projection_and_mention_overflow_never_become_empty_cohorts(
    pg_dsn: str, tmp_path: Path
) -> None:
    run = seed(pg_dsn, tmp_path, record("one"), record("two"))
    selected = registry_import(pg_dsn, tmp_path)
    with pytest.raises(AssessmentError, match="assessment_limit"):
        registry_cohort.read_comparison_cohort(
            pg_dsn, run, (selected,), PROJECTION_VERSION, max_mentions=1
        )
    database = store(pg_dsn, tmp_path)
    pending = uuid4()
    database.start_run(pending, QUERY)
    database.commit_page(pending, body(), observed_at=datetime.now(UTC))
    with pytest.raises(AssessmentError, match="projection_incomplete"):
        registry_cohort.read_comparison_cohort(pg_dsn, pending, (selected,), PROJECTION_VERSION)
