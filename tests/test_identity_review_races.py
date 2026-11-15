"""Independent SQL connections race complete transactions, never simulated commits."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, local
from uuid import UUID

import psycopg
import pytest

from nima.identity import review_evidence, review_store
from nima.identity.artifacts import encode
from nima.identity.review_inputs import decode_request
from nima.identity.review_state import fold_events
from nima.identity.review_types import (
    ReviewAcknowledgment,
    ReviewError,
    ReviewEvidence,
    ReviewReport,
    ReviewRequest,
    ReviewSubject,
)
from nima.storage.postgres import Connection
from tests.test_identity_review_accept import ledger, request
from tests.test_identity_review_evidence import report, seed_report
from tests.test_identity_review_support import source_snapshot


def race(
    dsn: str,
    requests: tuple[ReviewRequest, ReviewRequest],
    reports: tuple[ReviewReport, ReviewReport],
) -> list[ReviewAcknowledgment | str]:
    def write(index: int) -> ReviewAcknowledgment | str:
        try:
            return review_store.review(dsn, requests[index], report=reports[index])
        except ReviewError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=2) as workers:
        jobs = [workers.submit(write, index) for index in (0, 1)]
        return [job.result(timeout=40) for job in jobs]


def simultaneous_initial_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    original, barrier, thread = review_store._replay, Barrier(2), local()

    def replay(connection: Connection, selected: ReviewRequest) -> ReviewAcknowledgment | None:
        result = original(connection, selected)
        if not getattr(thread, "started", False):
            thread.started = True
            assert result is None
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(review_store, "_replay", replay)


def assert_consistent(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        heads = connection.execute(
            "SELECT observation_id,projection_version,role,ordinal,revision,latest_event_id "
            "FROM nima.identity_review_heads"
        ).fetchall()
        for head in heads:
            event = connection.execute(
                "SELECT event_id,request_payload FROM nima.identity_review_events "
                "WHERE event_id=%s",
                (head[5],),
            ).fetchone()
            assert event is not None
            selected = decode_request(event[0], encode(event[1])).subject
            events = review_store._events(connection, selected)
            folded = fold_events(selected, events)
            assert head[4:] == (folded.revision, events[-1].event_id)
            assert sum(pair.state == "accepted" for pair in folded.pairs) <= 1
        assert connection.execute(
            "SELECT count(*) FROM nima.identity_entities e WHERE NOT EXISTS "
            "(SELECT 1 FROM nima.identity_review_events r WHERE r.event_id=e.creating_event_id)"
        ).fetchone() == (0,)


def test_identical_concurrent_request_replays_after_waiting_for_head_lock(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    chosen = request(parsed)
    before = source_snapshot(pg_dsn)
    with monkeypatch.context() as patch:
        simultaneous_initial_reads(patch)
        outcomes = race(pg_dsn, (chosen, chosen), (parsed, parsed))
    assert all(isinstance(item, ReviewAcknowledgment) for item in outcomes)
    assert sorted(item.replayed for item in outcomes if isinstance(item, ReviewAcknowledgment)) == [
        False,
        True,
    ]
    assert ledger(pg_dsn) == (1, 1, 1)
    assert source_snapshot(pg_dsn) == before
    assert_consistent(pg_dsn)


def test_competing_acceptances_with_same_revision_commit_one_complete_result(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = seed_report(pg_dsn, tmp_path)
    with monkeypatch.context() as patch:
        simultaneous_initial_reads(patch)
        outcomes = race(pg_dsn, (request(parsed), request(parsed)), (parsed, parsed))
    assert sum(isinstance(item, ReviewAcknowledgment) for item in outcomes) == 1
    assert outcomes.count("review_conflict") == 1
    assert ledger(pg_dsn) == (1, 1, 1)
    assert_consistent(pg_dsn)


def test_global_uuid_collision_on_different_subject_rolls_back_losing_entity_and_head(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one, two = seed_report(pg_dsn, tmp_path / "one"), seed_report(pg_dsn, tmp_path / "two")
    first = request(one)
    second = replace(request(two), request_id=first.request_id)
    with monkeypatch.context() as patch:
        simultaneous_initial_reads(patch)
        outcomes = race(pg_dsn, (first, second), (one, two))
    assert sum(isinstance(item, ReviewAcknowledgment) for item in outcomes) == 1
    assert outcomes.count("review_conflict") == 1 and ledger(pg_dsn) == (1, 1, 1)
    assert_consistent(pg_dsn)


@pytest.mark.parametrize("collision", ["entity_id", "anchor"])
def test_handle_creation_collision_rolls_back_then_can_select_winner_explicitly(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision: str,
) -> None:
    one, two = seed_report(pg_dsn, tmp_path / "one"), seed_report(pg_dsn, tmp_path / "two")
    if collision == "anchor":
        two = report(replace(two.cohort, imports=one.cohort.imports, registry=one.cohort.registry))
    first = request(one)
    second = request(two, entity=first.entity_id) if collision == "entity_id" else request(two)
    original, barrier = review_evidence.validate_evidence, Barrier(2)

    def validated(
        connection: Connection,
        selected: ReviewReport,
        *,
        subjects: Sequence[ReviewSubject] | None = None,
        entity_ids: Sequence[UUID] = (),
    ) -> ReviewEvidence:
        checked = original(
            connection,
            selected,
            subjects=subjects,
            entity_ids=entity_ids,
        )
        barrier.wait(timeout=10)
        return checked

    with monkeypatch.context() as patch:
        patch.setattr(review_evidence, "validate_evidence", validated)
        outcomes = race(pg_dsn, (first, second), (one, two))
    assert sum(isinstance(item, ReviewAcknowledgment) for item in outcomes) == 1
    assert outcomes.count("review_conflict") == 1 and ledger(pg_dsn) == (1, 1, 1)
    winner = next(item for item in outcomes if isinstance(item, ReviewAcknowledgment))
    loser = first if outcomes[0] == "review_conflict" else second
    selected = one if outcomes[0] == "review_conflict" else two
    recovered = review_store.review(
        pg_dsn, replace(loser, entity_id=winner.entity_id), report=selected
    )
    assert not recovered.replayed and ledger(pg_dsn) == (2, 1, 2)
    assert_consistent(pg_dsn)
