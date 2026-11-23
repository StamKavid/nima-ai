"""L5b: the comparison reads imported AFM search runs beside profile imports, one SQL snapshot.

Synthetic procurement parties and the synthetic five-AFM search run; real PostgreSQL.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg import sql

from nima.identity import ComparisonError, registry_cohort
from nima.identity.registry_report import build_report
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.gemi import import_run, import_search_run
from nima.storage.postgres import migrate
from tests.test_gemi_afm_collection import RULES, A, B, C, D, E
from tests.test_gemi_afm_verify import search_run
from tests.test_gemi_import_archive import archive_run
from tests.test_identity_report import seed
from tests.test_kimdis_pages import record


def parties_run(dsn: str, path: Path, afms: tuple[str, ...]) -> UUID:
    rows = [
        {
            **record(str(i)),
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": f"Συνθετικός {i}", "vatNumber": afm, "country": {"key": "GR"}}
                ]
            },
        }
        for i, afm in enumerate(afms)
    ]
    return seed(dsn, path, *rows)


def searched(dsn: str, path: Path) -> UUID:
    root = path / "search"
    run = search_run(root)
    import_search_run(dsn, root, run, RULES)
    return run


def supplier_outcomes(report: dict[str, Any]) -> dict[str, tuple[Any, ...]]:
    result: dict[str, tuple[Any, ...]] = {}
    for item in report["occurrences"]:
        if item["role"] == "supplier":
            comparison = item["comparison"]
            result[item["tax_id"]] = (
                comparison["outcome"],
                tuple(comparison["registry_observation_refs"]),
                tuple(comparison["issues"]),
            )
    return result


def test_a_search_import_is_read_with_its_queries_hits_and_exact_evidence_locations(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A, B, C, D, E))
    selected = searched(pg_dsn, tmp_path)
    cohort = registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
    assert cohort.imports == ()
    (imported,) = cohort.search_imports
    assert imported.import_id == selected and imported.import_version == "gemi-search-import-v1"
    assert (imported.afm_count, imported.request_count, imported.hit_count) == (5, 5, 6)
    assert {q.afm: q.outcome for q in cohort.search_queries} == {
        A: "hit_single",
        B: "hit_multiple",
        C: "not_found_at_observation",
        D: "afm_mismatch",
        E: "truncated",
    }
    assert {q.afm for q in cohort.search_queries if q.truncated} == {E}
    hits = {(h.claim.queried_afm, h.claim.registry_number): h for h in cohort.registry}
    assert len(hits) == 6 and all(h.claim.outcome == "found" for h in hits.values())
    assert hits[(D, "5")].claim.afm_matches is False and hits[(A, "1")].claim.afm_matches
    assert hits[(B, "3")].fields["name_el"].json_pointer == "/searchResults/1/coNameEl"
    assert hits[(B, "2")].fields["registry_number"].json_pointer == "/searchResults/0/arGemi"
    assert hits[(A, "1")].status == 200 and hits[(A, "1")].source_id == "gemi:1"
    order = [
        (r.claim.import_id.int, r.claim.registry_number, r.claim.queried_afm or "")
        for r in cohort.registry
    ]
    assert order == sorted(order)


def test_the_report_gives_each_party_its_outcome_and_marks_the_searched_afms(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A, B, C, D, E))
    selected = searched(pg_dsn, tmp_path)
    report: dict[str, Any] = dict(
        build_report(
            registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
        )
    )
    assert report["report_format"] == "nima-registry-comparison-report-v2"
    assert report["policy_version"] == "registry-comparison-v3"
    assert report["automatic_identity_links"] == 0 and report["registry_imports"] == []
    outcomes = supplier_outcomes(report)
    assert outcomes[A][0] == "reported_identifier_agreement" and outcomes[A][2] == ()
    # B is a head office with one branch: an ordinary agreement. E has two head offices.
    assert outcomes[B][0] == "reported_identifier_agreement" and len(outcomes[B][1]) == 2
    assert outcomes[B][2] == ()
    assert "multiple_registry_numbers_for_reported_afm" in outcomes[E][2]
    assert outcomes[C] == ("queried_not_found_at_observation", (), ())
    assert outcomes[D] == ("no_candidate_in_selected_imports", (), ("search_afm_mismatch",))
    assert (
        outcomes[E][0] == "reported_identifier_agreement" and "search_truncated" in outcomes[E][2]
    )
    queries = report["search_queries"]
    assert len(queries) == 5 and {q["afm"] for q in queries} == {A, B, C, D, E}
    rows = report["registry_observations"]
    assert [r["queried_afm"] for r in rows].count(D) == 1
    assert all(r["identifier_assessment"]["identity_status"] == "unresolved" for r in rows)


def test_profile_and_search_imports_can_be_selected_together(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, ("001234567", A))
    profile_root = tmp_path / "gemi"
    profile_run = archive_run(profile_root)
    import_run(pg_dsn, profile_root, profile_run)
    selected = searched(pg_dsn, tmp_path)
    cohort = registry_cohort.read_comparison_cohort(
        pg_dsn, run, (selected, profile_run), PROJECTION_VERSION
    )
    assert [i.import_id for i in cohort.imports] == [profile_run]
    assert [i.import_id for i in cohort.search_imports] == [selected]
    order = [
        (r.claim.import_id.int, r.claim.registry_number, r.claim.queried_afm or "")
        for r in cohort.registry
    ]
    assert order == sorted(order) and len(order) == 8  # two profile rows and six hits, grouped
    outcomes = supplier_outcomes(dict(build_report(cohort)))
    assert outcomes["001234567"][0] == "reported_identifier_agreement"
    assert outcomes[A][0] == "reported_identifier_agreement"


def test_reading_changes_nothing(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A, B))
    selected = searched(pg_dsn, tmp_path)
    tables = (
        "gemi_search_imports",
        "gemi_search_requests",
        "gemi_search_outcomes",
        "gemi_search_hits",
    )

    def state() -> list[object]:
        with psycopg.connect(pg_dsn) as connection:
            return [
                connection.execute(
                    sql.SQL(
                        "SELECT count(*), md5(string_agg(t::text, ',' ORDER BY t::text)) "
                        "FROM nima.{} t"
                    ).format(sql.Identifier(name))
                ).fetchone()
                for name in tables
            ]

    before = state()
    registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
    assert state() == before


def test_an_unknown_import_is_unavailable_and_an_id_cannot_be_selected_twice(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    selected = searched(pg_dsn, tmp_path)
    with pytest.raises(ComparisonError, match="^registry_import_unavailable$"):
        registry_cohort.read_comparison_cohort(
            pg_dsn, run, (selected, UUID(int=77)), PROJECTION_VERSION
        )
    with pytest.raises(ValueError, match="comparison_configuration"):
        registry_cohort.read_comparison_cohort(
            pg_dsn, run, (selected, selected), PROJECTION_VERSION
        )


def corrupt(dsn: str, table: str, trigger: str, assignment: str) -> None:
    with psycopg.connect(dsn) as connection:
        # Out-of-band administrator corruption, in this disposable database only.
        connection.execute(
            sql.SQL("ALTER TABLE nima.{} DISABLE TRIGGER {}").format(
                sql.Identifier(table), sql.Identifier(trigger)
            )
        )
        connection.execute(
            sql.SQL("UPDATE nima.{} SET ").format(sql.Identifier(table)) + sql.SQL(assignment)
        )


@pytest.mark.parametrize(
    ("table", "trigger", "assignment", "reason"),
    [
        ("gemi_search_imports", "gemi_search_imports_immutable", "hit_count = hit_count + 1", None),
        (
            "gemi_search_imports",
            "gemi_search_imports_immutable",
            "request_count = request_count + 1",
            None,
        ),
        ("gemi_search_imports", "gemi_search_imports_immutable", "afm_count = afm_count - 1", None),
        (
            "gemi_search_imports",
            "gemi_search_imports_immutable",
            "license = 'other'",
            "registry_version",
        ),
        (
            "gemi_search_imports",
            "gemi_search_imports_immutable",
            "normalizer_version = 'gemi-company-v0'",
            "registry_version",
        ),
        (
            "gemi_search_requests",
            "gemi_search_requests_immutable",
            "byte_length = byte_length + 1",
            None,
        ),
        (  # only the answer that has no hit rests on the altered request
            "gemi_search_requests",
            "gemi_search_requests_immutable",
            f"byte_length = byte_length + 1 WHERE afm = '{C}'",
            None,
        ),
        (
            "gemi_profile_versions",
            "gemi_versions_immutable",
            "normalized = jsonb_set(normalized, '{fields,reported_afm,value}', '5')",
            "registry_shape",
        ),
        (
            "gemi_profile_versions",
            "gemi_versions_immutable",
            "normalized = jsonb_set(normalized, '{fields,reported_afm,json_pointer}', '\"/afm\"')",
            "registry_shape",
        ),
    ],
)
def test_a_search_import_that_does_not_add_up_is_refused_without_a_partial_cohort(
    pg_dsn: str, tmp_path: Path, table: str, trigger: str, assignment: str, reason: str | None
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A, B))
    selected = searched(pg_dsn, tmp_path)
    corrupt(pg_dsn, table, trigger, assignment)
    with pytest.raises(ComparisonError) as caught:
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
    assert caught.value.args[0] == (reason or "registry_incomplete")


def test_too_many_selected_observations_fail_visibly_instead_of_truncating(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    selected = searched(pg_dsn, tmp_path)
    monkeypatch.setattr(registry_cohort, "MAX_REGISTRY_OBSERVATIONS", 5)  # the run has 6 hits
    with pytest.raises(ComparisonError, match="^comparison_limit$"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)


def test_profile_and_search_rows_together_may_not_exceed_the_bound(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    profile_root = tmp_path / "gemi"
    profile_run = archive_run(profile_root)
    import_run(pg_dsn, profile_root, profile_run)
    selected = searched(pg_dsn, tmp_path)
    # 2 profile observations and 6 hits: each is within 7, together they are not.
    monkeypatch.setattr(registry_cohort, "MAX_REGISTRY_OBSERVATIONS", 7)
    with pytest.raises(ComparisonError, match="^comparison_limit$"):
        registry_cohort.read_comparison_cohort(
            pg_dsn, run, (selected, profile_run), PROJECTION_VERSION
        )


def test_a_stored_outcome_outside_the_vocabulary_is_a_shape_failure(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    selected = searched(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        # Administrator corruption in this disposable database: drop the CHECK, then break a row.
        connection.execute("ALTER TABLE nima.gemi_search_outcomes DISABLE TRIGGER USER")
        for name in ("gemi_search_outcomes_check", "gemi_search_outcomes_outcome_check"):
            connection.execute(f"ALTER TABLE nima.gemi_search_outcomes DROP CONSTRAINT {name}")
        connection.execute(
            "UPDATE nima.gemi_search_outcomes SET outcome='bogus' WHERE afm=%s", (C,)
        )
    with pytest.raises(ComparisonError, match="^registry_shape$"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)


@pytest.mark.parametrize("value", [1, 0, None, "true", []])
def test_a_flag_that_is_not_a_boolean_is_a_shape_failure(value: object) -> None:
    with pytest.raises(ComparisonError, match="^registry_shape$"):
        registry_cohort._flag(value)
    assert registry_cohort._flag(True) is True and registry_cohort._flag(False) is False


def test_the_compare_command_accepts_a_search_import_and_prints_counts_only(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from nima.__main__ import main

    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A, B, C))
    selected = searched(pg_dsn, tmp_path)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    output = tmp_path / "reports"
    arguments = [
        "identities",
        "compare",
        str(run),
        "--gemi-import",
        str(selected),
        "--projection-version",
        PROJECTION_VERSION,
        "--output-dir",
        str(output),
    ]
    assert main(arguments) == 0
    printed = capsys.readouterr().out
    summary = json.loads(printed)
    assert summary["status"] == "complete" and summary["policy_version"] == "registry-comparison-v3"
    assert summary["search_import_ids"] == [str(selected)] and summary["gemi_import_ids"] == []
    assert summary["searched_afm_count"] == 5 and summary["automatic_identity_links"] == 0
    assert A not in printed and B not in printed
    report = json.loads(next(output.glob("*.json")).read_text())
    assert report["report_format"] == "nima-registry-comparison-report-v2"


def test_hit_counts_that_swap_between_afms_are_caught_even_when_the_total_agrees(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    selected = searched(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("ALTER TABLE nima.gemi_search_outcomes DISABLE TRIGGER USER")
        # Both rows stay within their own CHECK, and the import's total stays six.
        connection.execute(
            "UPDATE nima.gemi_search_outcomes SET hit_count = 3 WHERE afm = %s", (B,)
        )
        connection.execute(
            "UPDATE nima.gemi_search_outcomes SET hit_count = 1 WHERE afm = %s", (E,)
        )
    with pytest.raises(ComparisonError, match="^registry_incomplete$"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)


@pytest.mark.parametrize("column", ["import_version", "connector_version"])
def test_an_import_of_another_version_is_unsupported(
    pg_dsn: str, tmp_path: Path, column: str
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    selected = searched(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        # A later version would be written by a later release; here the CHECK is dropped to say so.
        connection.execute("ALTER TABLE nima.gemi_search_imports DISABLE TRIGGER USER")
        name = f"gemi_search_imports_{column}_check"
        connection.execute(f"ALTER TABLE nima.gemi_search_imports DROP CONSTRAINT {name}")
        connection.execute(f"UPDATE nima.gemi_search_imports SET {column} = 'a-later-version'")
    with pytest.raises(ComparisonError, match="^registry_version$"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)


def test_the_limit_is_checked_before_any_hit_is_read(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    selected = searched(pg_dsn, tmp_path)
    monkeypatch.setattr(registry_cohort, "MAX_REGISTRY_OBSERVATIONS", 5)
    monkeypatch.setattr(
        registry_cohort, "_search_hits", lambda *_: pytest.fail("hits were read past the bound")
    )
    with pytest.raises(ComparisonError, match="^comparison_limit$"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)


def test_a_hit_under_an_outcome_that_returned_no_hit_is_refused(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    run = parties_run(pg_dsn, tmp_path, (A,))
    selected = searched(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn) as connection:
        # Administrator corruption: relabel one AFM's outcome so its two hits have no basis.
        connection.execute("ALTER TABLE nima.gemi_search_outcomes DISABLE TRIGGER USER")
        for name in ("gemi_search_outcomes_check", "gemi_search_outcomes_outcome_check"):
            connection.execute(f"ALTER TABLE nima.gemi_search_outcomes DROP CONSTRAINT {name}")
        connection.execute(
            "UPDATE nima.gemi_search_outcomes SET outcome = 'quarantined' WHERE afm = %s", (B,)
        )
    with pytest.raises(ComparisonError, match="^registry_incomplete$"):
        registry_cohort.read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION)
