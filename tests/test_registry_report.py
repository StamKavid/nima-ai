"""Canonical private comparison artifacts from immutable and real SQL evidence."""

import hashlib
import json
import stat
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from nima.identity import AssessmentError, artifacts, registry_report
from nima.identity.registry_cohort import (
    ComparisonCohort,
    ImportEvidence,
    PartyEvidence,
    RegistryEvidence,
    _fields,
)
from nima.identity.registry_policy import RegistryObservation
from nima.projections.worker import PROJECTION_VERSION
from nima.sources.gemi import normalize_profile
from tests.test_gemi_contracts import profile


def cohort() -> ComparisonCohort:
    imports = tuple(
        ImportEvidence(
            UUID(int=i),
            "gemi-import-v1",
            "gemi-company-v1",
            str(i) * 64,
            "https://example.org/source",
            "ODC-BY-1.0",
            "publisher",
            "2026-11-14T00:00:00+00:00",
            1,
            0,
            1,
        )
        for i in (1, 2, 3)
    )
    registry = tuple(
        RegistryEvidence(
            RegistryObservation(item.import_id, "1", "found", afm),
            1,
            200,
            "a" * 64,
            "2026-11-13T00:00:00+00:00",
            "gemi:1",
            "gemi-company-v1",
            _fields(normalize_profile(profile(afm=afm), "1").payload()["fields"], "1"),
        )
        for item, afm in zip(imports, ("001234567", "123456789", "001234567"), strict=True)
    )
    party = PartyEvidence(
        "kimdis:1",
        "kimdis-contract-v1",
        "b" * 64,
        1,
        "supplier",
        0,
        " Άλφα ΑΕ ",
        "001234567",
        None,
        "GR",
        "c" * 64,
        "/content/0",
        "2026-11-12T00:00:00+00:00",
        "2020-01-01",
        None,
    )
    return ComparisonCohort(
        UUID(int=10),
        PROJECTION_VERSION,
        MappingProxyType({"expected_mentions": 2}),
        (replace(party, observation_id=2), party),
        imports,
        registry,
    )


def test_catalog_references_preserve_repeated_versions_and_original_provenance() -> None:
    inputs = cohort()
    report = json.loads(artifacts.encode(registry_report.build_report(inputs)))
    assert report["report_format"] == "nima-registry-comparison-report-v1"
    assert report["policy_version"] == "registry-comparison-v3"
    assert report["archive_integrity"] == "not_checked" and report["automatic_identity_links"] == 0
    rows = report["occurrences"]
    assert [row["observation_id"] for row in rows] == [1, 2]
    assert all(row["name"] == " Άλφα ΑΕ " for row in rows)
    assert all(row["comparison"]["registry_observation_refs"] == [0, 2] for row in rows)
    assert all(row["comparison"]["outcome"] == "reported_identifier_agreement" for row in rows)
    assert all(row["assessment"]["identity_status"] == "unresolved" for row in rows)
    assert all(row["assessment"]["issuer_country"] is None for row in rows)
    catalog = report["registry_observations"]
    assert len(catalog) == len(report["registry_imports"]) == 3
    assert catalog[0]["fields"]["reported_afm"]["value"] == "001234567"
    assert catalog[0]["fields"]["reported_afm"]["json_pointer"] == "/afm"
    assert all(
        "reported_afm_changed_for_registry_number" in row["identifier_assessment"]["issues"]
        for row in catalog
    )
    shuffled = replace(
        inputs,
        parties=tuple(reversed(inputs.parties)),
        imports=tuple(reversed(inputs.imports)),
        registry=tuple(reversed(inputs.registry)),
    )
    assert artifacts.encode(report) == artifacts.encode(registry_report.build_report(shuffled))
    assert inputs == cohort()


def test_private_publication_replay_and_summary_exclude_source_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = cohort()
    monkeypatch.setattr(registry_report, "read_comparison_cohort", lambda *a, **kw: inputs)
    output = tmp_path / "reports"
    summary = registry_report.compare_run(
        "private-dsn",
        inputs.run_id,
        tuple(row.import_id for row in inputs.imports),
        PROJECTION_VERSION,
        output,
    )
    assert summary == registry_report.compare_run(
        "private-dsn",
        inputs.run_id,
        tuple(reversed(tuple(row.import_id for row in inputs.imports))),
        PROJECTION_VERSION,
        output,
    )
    files = list(output.glob("*.json"))
    assert len(files) == 1
    assert summary["report_sha256"] == hashlib.sha256(files[0].read_bytes()).hexdigest()
    assert files[0].read_bytes() == artifacts.encode(registry_report.build_report(inputs))
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert (output / ".gitignore").read_bytes() == b"*\n"
    assert summary["mention_count"] == 2 and summary["registry_observation_count"] == 3
    assert summary["automatic_identity_links"] == 0
    for value in ("Άλφα", "001234567", str(output), "private-dsn"):
        assert value not in json.dumps(summary, ensure_ascii=False)


def test_exact_canonical_output_bound_precedes_directory_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = cohort()
    body = artifacts.encode(registry_report.build_report(inputs))
    monkeypatch.setattr(registry_report, "read_comparison_cohort", lambda *a, **kw: inputs)
    monkeypatch.setattr(artifacts, "MAX_REPORT_BYTES", len(body) - 1)
    output = tmp_path / "reports"
    with pytest.raises(AssessmentError, match="assessment_limit"):
        registry_report.compare_run("", inputs.run_id, (UUID(int=1),), PROJECTION_VERSION, output)
    assert not output.exists()
    monkeypatch.setattr(artifacts, "MAX_REPORT_BYTES", len(body))
    registry_report.compare_run("", inputs.run_id, (UUID(int=1),), PROJECTION_VERSION, output)
    assert next(output.glob("*.json")).read_bytes() == body


@pytest.mark.parametrize("fault", ["conflict", "symlink", "public", "io"])
def test_report_publication_rejects_unsafe_paths_or_conflicting_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    inputs = cohort()
    monkeypatch.setattr(registry_report, "read_comparison_cohort", lambda *a, **kw: inputs)
    output = tmp_path / "reports"
    reason = "output_path"
    if fault == "symlink":
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        output.symlink_to(target, target_is_directory=True)
        reason = "output_io"
    elif fault == "io":
        output.write_bytes(b"private-sentinel")
        reason = "output_io"
    else:
        output.mkdir(mode=0o700)
        if fault == "public":
            output.chmod(0o755)
        if fault == "conflict":
            digest = hashlib.sha256(
                artifacts.encode(registry_report.build_report(inputs))
            ).hexdigest()
            (output / (digest + ".json")).write_bytes(b"private-sentinel")
            reason = "output_conflict"
    with pytest.raises(AssessmentError, match=reason) as error:
        registry_report.compare_run(
            "private-sentinel", inputs.run_id, (UUID(int=1),), PROJECTION_VERSION, output
        )
    assert "private-sentinel" not in str(error.value)
    if fault == "conflict":
        assert next(output.glob("*.json")).read_bytes() == b"private-sentinel"
    assert not list(tmp_path.rglob(".tmp-*"))


def test_sql_to_report_replay_coverage_change_and_source_state(
    pg_dsn: str,
    tmp_path: Path,
) -> None:
    from datetime import UTC, datetime

    from nima.projections.worker import drain
    from tests.test_collection import QUERY, body
    from tests.test_gemi_import import counts as registry_counts
    from tests.test_gemi_import_archive import snapshot
    from tests.test_identity_report import seed
    from tests.test_kimdis_pages import record
    from tests.test_page_store import counts, store
    from tests.test_registry_cohort import registry_import

    row = {
        **record(),
        "contractingDataDetails": {
            "contractingMembersDataList": [
                {"name": " Άλφα ΑΕ ", "vatNumber": "001234567", "country": {"key": "GR"}}
            ]
        },
    }
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    database.commit_page(run, body(0, 2, **row), observed_at=datetime.now(UTC))
    drain(pg_dsn)
    selected = tuple(
        registry_import(pg_dsn, tmp_path, profile(afm=afm))
        for afm in ("001234567", "123456789", "001234567")
    )
    output = tmp_path / "reports"
    before = counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")
    summary = registry_report.compare_run(pg_dsn, run, selected, PROJECTION_VERSION, output)
    assert summary == registry_report.compare_run(
        pg_dsn, run, tuple(reversed(selected)), PROJECTION_VERSION, output
    )
    assert (counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")) == before
    report = json.loads(next(output.glob("*.json")).read_bytes())
    assert len(report["registry_observations"]) == 6
    assert (
        sum(row["outcome"] == "not_found_at_observation" for row in report["registry_observations"])
        == 3
    )
    assert report["coverage"]["observation_count"] == 1
    suppliers = [row for row in report["occurrences"] if row["role"] == "supplier"]
    assert len(suppliers) == 1
    assert suppliers[0]["comparison"]["outcome"] == "reported_identifier_agreement"
    assert len(suppliers[0]["comparison"]["registry_observation_refs"]) == 2
    assert summary["automatic_identity_links"] == 0
    # New selected procurement evidence changes coverage and report identity.
    database.commit_page(
        run, body(1, 2, **{**row, "referenceNumber": "later"}), observed_at=datetime.now(UTC)
    )
    drain(pg_dsn)
    changed_before = counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")
    changed = registry_report.compare_run(pg_dsn, run, selected, PROJECTION_VERSION, output)
    assert changed["report_sha256"] != summary["report_sha256"]
    assert len(list(output.glob("*.json"))) == 2
    assert (counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")) == changed_before
    # Another run is not added to the selected run's coverage.
    seed(pg_dsn, tmp_path, record("unselected"))
    assert changed == registry_report.compare_run(pg_dsn, run, selected, PROJECTION_VERSION, output)


@pytest.mark.parametrize("empty_parties", [False, True])
def test_real_all_404_import_keeps_unknown_outcomes_and_empty_cohort(
    pg_dsn: str,
    tmp_path: Path,
    empty_parties: bool,
) -> None:
    import httpx

    from nima.ingestion.gemi import collect
    from nima.storage.gemi import import_run
    from tests.test_collection import Clock
    from tests.test_identity_report import seed
    from tests.test_kimdis_pages import record

    run = seed(pg_dsn, tmp_path, *(() if empty_parties else (record(),)))
    root = tmp_path / "gemi"
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(404, content=b"missing"))
    ) as client:
        collected = collect(
            ("1", "2"), root, api_key="synthetic-credential", client=client, clock=Clock()
        )
    selected = UUID(collected.run_id)
    import_run(pg_dsn, root, selected)
    output = tmp_path / "reports"
    summary = registry_report.compare_run(pg_dsn, run, (selected,), PROJECTION_VERSION, output)
    report = json.loads(next(output.glob("*.json")).read_bytes())
    assert summary["status"] == "complete" and summary["registry_observation_count"] == 2
    assert summary["mention_count"] == (0 if empty_parties else 1)
    assert all(
        row["outcome"] == "not_found_at_observation" and row["fields"] == {}
        for row in report["registry_observations"]
    )
    assert all(not row["comparison"]["registry_observation_refs"] for row in report["occurrences"])
    assert all(
        row["comparison"]["outcome"] != "reported_identifier_agreement"
        for row in report["occurrences"]
    )
    assert report["automatic_identity_links"] == 0


def test_missing_candidates_unassessed_parties_and_404s_remain_explicit() -> None:
    inputs = cohort()
    party = inputs.parties[0]
    missing = RegistryEvidence(
        RegistryObservation(UUID(int=1), "2", "not_found_at_observation", None),
        1,
        404,
        "d" * 64,
        "2026-11-13T00:00:00+00:00",
        None,
        None,
        MappingProxyType({}),
    )
    inputs = replace(
        inputs,
        registry=(missing,),
        parties=(
            party,
            replace(party, observation_id=3, tax_id=None),
            replace(party, observation_id=4, country_code="EL"),
        ),
    )
    report = json.loads(artifacts.encode(registry_report.build_report(inputs)))
    assert [row["comparison"]["outcome"] for row in report["occurrences"]] == [
        "no_candidate_in_selected_imports",
        "unassessed_identifier",
        "no_candidate_in_selected_imports",
    ]
    assert all(
        row["comparison"]["registry_observation_refs"] == [] for row in report["occurrences"]
    )
    assert report["registry_observations"][0]["fields"] == {}
    assert (
        report["registry_observations"][0]["identifier_assessment"]["identifier_status"]
        == "not_found_at_observation"
    )
    empty = registry_report.build_report(replace(inputs, parties=()))
    assert empty["occurrences"] == [] and len(empty["registry_observations"]) == 1


def test_coverage_and_temporal_provenance_change_artifact_identity() -> None:
    inputs = cohort()
    original = artifacts.encode(registry_report.build_report(inputs))
    variations = (
        replace(inputs, coverage=MappingProxyType({"expected_mentions": 2, "quarantine_count": 1})),
        replace(
            inputs,
            parties=(replace(inputs.parties[0], source_updated_at="2025-01-01"), inputs.parties[1]),
        ),
        replace(
            inputs,
            imports=(
                replace(inputs.imports[0], imported_at="2026-11-15T00:00:00+00:00"),
                *inputs.imports[1:],
            ),
        ),
        replace(
            inputs,
            registry=(
                replace(inputs.registry[0], observed_at="2026-11-14T00:00:00+00:00"),
                *inputs.registry[1:],
            ),
        ),
    )
    assert all(
        artifacts.encode(registry_report.build_report(changed)) != original
        for changed in variations
    )
