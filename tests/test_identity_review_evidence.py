"""Frozen reports must reconcile with SQL, including hidden catalog/anchor conflicts."""

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Never, cast
from uuid import UUID, uuid4

import psycopg
import pytest

from nima.identity import review_evidence
from nima.identity.artifacts import encode
from nima.identity.registry_cohort import ComparisonCohort, RegistryEvidence, read_comparison_cohort
from nima.identity.registry_report import build_report
from nima.identity.review_inputs import _party, decode_report
from nima.identity.review_state import propose
from nima.identity.review_types import (
    ReviewAnchor,
    ReviewCandidate,
    ReviewError,
    ReviewReport,
    ReviewRequest,
    ReviewSubject,
)
from nima.projections.worker import PROJECTION_VERSION, drain
from nima.sources.gemi import Assertion
from nima.storage.postgres import Connection
from tests.test_collection import QUERY
from tests.test_gemi_contracts import profile
from tests.test_identity_report import seed
from tests.test_identity_review_inputs import report_body
from tests.test_identity_review_schema import event, head
from tests.test_kimdis_pages import page_body, record
from tests.test_page_store import counts as procurement_counts
from tests.test_page_store import store
from tests.test_registry_cohort import registry_import


def report(cohort: ComparisonCohort) -> ReviewReport:
    return decode_report(encode(build_report(cohort)))


def subject(parsed: ReviewReport, index: int = 0) -> ReviewSubject:
    data = parsed.cohort
    party = data.parties[index]
    return ReviewSubject(
        data.run_id,
        party.observation_id,
        data.projection_version,
        party.source_id,
        party.normalizer_version,
        party.content_sha256,
        party.role,
        party.ordinal,
    )


def seed_report(dsn: str, path: Path) -> ReviewReport:
    run = seed(
        dsn,
        path,
        {
            **record(),
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": " Άλφα ΑΕ ", "vatNumber": "001234567", "country": {"key": "GR"}}
                ]
            },
        },
    )
    selected = registry_import(dsn, path)
    return report(read_comparison_cohort(dsn, run, (selected,), PROJECTION_VERSION))


def test_invalid_in_memory_report_and_selectors_fail_before_sql() -> None:
    parsed = decode_report(report_body())

    class NoDatabase:
        @property
        def info(self) -> Never:
            pytest.fail("Invalid selectors must not reach the connection")

        def execute(self, *args: object, **kwargs: object) -> Never:
            pytest.fail("Invalid selectors must not reach SQL")

    connection = cast(Connection, NoDatabase())
    for changed, selected, entities in (
        (replace(parsed, sha256="a" * 64), None, ()),
        (parsed, (subject(parsed), subject(parsed)), ()),
        (parsed, (replace(subject(parsed), run_id=uuid4()),), ()),
        (parsed, (replace(subject(parsed), observation_id=True),), ()),
        (parsed, (), ()),
        (parsed, None, (uuid4(),) * 101),
        (parsed, None, (UUID(int=1), UUID(int=1))),
    ):
        with pytest.raises(ReviewError, match="^review_(evidence|limit)$"):
            review_evidence.validate_evidence(
                connection, changed, subjects=selected, entity_ids=entities
            )


def test_oversized_typed_report_fails_with_fixed_limit_before_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = decode_report(report_body())
    monkeypatch.setattr("nima.identity.artifacts.MAX_REPORT_BYTES", 1)
    with pytest.raises(ReviewError, match="^review_limit$"):
        review_evidence.validate_evidence(cast(Connection, None), parsed)


def test_sql_validation_uses_caller_transaction_and_never_requests_http(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    before = procurement_counts(pg_dsn)

    def forbidden(*args: object, **kwargs: object) -> Never:
        pytest.fail("Validator must not create a client/connection or reopen current-run coverage")

    monkeypatch.setattr("httpx.Client", forbidden)
    monkeypatch.setattr("nima.identity.registry_cohort._connect", forbidden)
    monkeypatch.setattr("nima.identity.cohort.read_cohort_in_transaction", forbidden)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        checked = review_evidence.validate_evidence(connection, parsed)
        assert checked.cohort == parsed.cohort
        assert not checked.anchors and 0 < checked.input_bytes <= 8 * 1024 * 1024
        assert connection.execute("SELECT 1").fetchone() == (1,)
        with pytest.raises(TypeError):
            cast(dict[UUID, RegistryEvidence], checked.anchors)[uuid4()] = checked.cohort.registry[
                0
            ]
    assert procurement_counts(pg_dsn) == before


@pytest.mark.parametrize("fault", ["name", "tax_id", "pointer", "date", "hash", "observed_at"])
def test_internally_consistent_forged_occurrence_is_rejected_by_sql(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    changed: dict[str, object] = {
        "name": "private-sentinel",
        "tax_id": "123456789",
        "json_pointer": "/content/99",
        "source_submitted_at": "2001-01-01",
        "raw_sha256": "a" * 64,
        "observed_at": "2001-01-01T00:00:00+00:00",
    }
    key = {"pointer": "json_pointer", "date": "source_submitted_at", "hash": "raw_sha256"}.get(
        fault, fault
    )
    altered = _party({**asdict(parsed.cohort.parties[0]), key: changed[key]}, parsed.cohort.run_id)
    forged = report(replace(parsed.cohort, parties=(altered, *parsed.cohort.parties[1:])))
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        with pytest.raises(ReviewError, match="^review_evidence$") as error:
            review_evidence.validate_evidence(connection, forged)
        assert "private-sentinel" not in str(error.value)


def test_forged_catalog_omission_and_labels_are_not_authorized_by_new_hash(
    pg_dsn: str, tmp_path: Path
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    missing = next(row for row in parsed.cohort.registry if row.claim.outcome != "found")
    catalog = tuple(row for row in parsed.cohort.registry if row is not missing)
    imports = tuple(replace(row, not_found_count=0) for row in parsed.cohort.imports)
    forged = report(replace(parsed.cohort, registry=catalog, imports=imports))
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        with pytest.raises(ReviewError, match="^review_evidence$"):
            review_evidence.validate_evidence(connection, forged)


@pytest.mark.parametrize("fault", ["registry_name", "afm", "registry_hash", "import_license"])
def test_internally_consistent_forged_registry_and_import_claims_fail_sql(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    registry = list(parsed.cohort.registry)
    found = registry[0]
    imports = parsed.cohort.imports
    if fault in {"registry_name", "afm"}:
        key = "name_el" if fault == "registry_name" else "reported_afm"
        value = "private-sentinel" if fault == "registry_name" else "123456789"
        fields = {**found.fields, key: Assertion(value, found.fields[key].json_pointer)}
        registry[0] = replace(
            found,
            fields=MappingProxyType(fields),
            claim=replace(found.claim, reported_afm=value) if fault == "afm" else found.claim,
        )
    elif fault == "registry_hash":
        registry[0] = replace(found, raw_sha256="a" * 64)
    else:
        imports = (replace(imports[0], license="private-sentinel"),)
    forged = report(replace(parsed.cohort, registry=tuple(registry), imports=imports))
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        with pytest.raises(ReviewError, match="^review_evidence$"):
            review_evidence.validate_evidence(connection, forged)


def test_later_collection_does_not_replace_frozen_occurrence_selection(
    pg_dsn: str, tmp_path: Path
) -> None:
    database = store(pg_dsn, tmp_path)
    run = uuid4()
    database.start_run(run, QUERY)
    metadata = {"size": 1, "totalElements": 2, "totalPages": 2}
    database.commit_page(
        run, page_body(record(), **metadata, last=False), observed_at=datetime.now(UTC)
    )
    drain(pg_dsn)
    selected = registry_import(pg_dsn, tmp_path)
    parsed = report(read_comparison_cohort(pg_dsn, run, (selected,), PROJECTION_VERSION))
    # The same run acquires a later, deliberately unprojected observation.
    database.commit_page(
        run, page_body(record("later"), **metadata, number=1), observed_at=datetime.now(UTC)
    )
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        checked = review_evidence.validate_evidence(connection, parsed, subjects=(subject(parsed),))
        assert checked.cohort.parties == (parsed.cohort.parties[0],)
        assert checked.cohort.coverage == parsed.cohort.coverage


def test_sql_byte_budget_is_checked_before_label_rows_are_transferred(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    monkeypatch.setattr(review_evidence, "MAX_INPUT_BYTES", 1)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        with pytest.raises(ReviewError, match="^review_limit$"):
            review_evidence.validate_evidence(connection, parsed)


@pytest.mark.parametrize("overlap", [False, True])
def test_sql_anchor_union_preserves_afm_change_and_counts_overlap_once(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overlap: bool
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    selected = parsed.cohort.imports[0].import_id
    anchored = (
        selected if overlap else registry_import(pg_dsn, tmp_path / "old", profile(afm="111222333"))
    )
    entity, creating = uuid4(), uuid4()
    with psycopg.connect(pg_dsn) as connection:
        observation = head(connection, parsed.cohort.run_id)
        connection.execute(
            "INSERT INTO nima.identity_entities "
            "(entity_id,anchor_import_id,registry_number,creating_event_id) "
            "VALUES (%s,%s,'1',%s)",
            (entity, anchored, creating),
        )
        event(
            connection, observation, anchored, request=creating, entity=entity, operation="accept"
        )
        connection.execute(
            "UPDATE nima.identity_review_heads SET revision=1,latest_event_id=%s", (creating,)
        )
    # Two catalog rows plus one distinct outside anchor; outside 404 is not selected.
    monkeypatch.setattr(review_evidence, "MAX_REGISTRY_OBSERVATIONS", 2 if overlap else 3)
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        checked = review_evidence.validate_evidence(connection, parsed, entity_ids=(entity,))
        assert checked.anchors[entity].claim.import_id == anchored
        assert checked.cohort == parsed.cohort
        request = ReviewRequest(
            uuid4(),
            "accept",
            subject(parsed, 1),
            ReviewCandidate(selected, "1"),
            0,
            "Έλεγχος",
            parsed.sha256,
            entity,
        )
        anchor = ReviewAnchor(entity, checked.anchors[entity].claim)
        if overlap:
            assert propose(request, (), cohort=checked.cohort, anchor=anchor).issues == ()
        else:
            with pytest.raises(ReviewError, match="^review_conflict$"):
                propose(request, (), cohort=checked.cohort, anchor=anchor)
            issue = "reported_afm_changed_for_registry_number"
            assert propose(
                replace(request, acknowledged_issues=(issue,)),
                (),
                cohort=checked.cohort,
                anchor=anchor,
            ).issues == (issue,)
            monkeypatch.setattr(review_evidence, "MAX_REGISTRY_OBSERVATIONS", 2)
            with pytest.raises(ReviewError, match="^review_limit$"):
                review_evidence.validate_evidence(connection, parsed, entity_ids=(entity,))


@pytest.mark.parametrize("fault", ["no_transaction", "timezone", "isolation", "missing_entity"])
def test_transaction_context_and_missing_entity_fail_closed(
    pg_dsn: str, tmp_path: Path, fault: str
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    with psycopg.connect(pg_dsn, autocommit=fault == "no_transaction") as connection:
        if fault != "no_transaction":
            if fault == "isolation":
                connection.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            connection.execute(
                "SET LOCAL TIME ZONE 'Europe/Athens'"
                if fault == "timezone"
                else "SET LOCAL TIME ZONE 'UTC'"
            )
        with pytest.raises(
            ReviewError,
            match="^review_evidence$" if fault == "missing_entity" else "^review_state$",
        ):
            review_evidence.validate_evidence(
                connection, parsed, entity_ids=(uuid4(),) if fault == "missing_entity" else ()
            )
