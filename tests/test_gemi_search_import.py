"""L5a: a verified GEMI search run is imported atomically into immutable SQL evidence.

Synthetic runs on real PostgreSQL. The import re-verifies the archive every time, writes only
what the verifier recomputed, and never touches the profile tables (`gemi_imports`,
`gemi_observations`).
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from psycopg import sql

from nima.__main__ import main
from nima.storage.gemi import import_search_run
from nima.storage.gemi_archive import ImportFailure
from nima.storage.postgres import migrate
from tests.test_gemi_afm_collection import JSON, RULES, A, B, C, D, E, example
from tests.test_gemi_afm_verify import search_run
from tests.test_gemi_import_archive import archive_run, edit, manifest_path, snapshot
from tests.test_gemi_search import body, company

TABLES = ("gemi_search_imports", "gemi_search_requests", "gemi_search_outcomes", "gemi_search_hits")


def counts(dsn: str) -> tuple[object, ...]:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("""SELECT
            (SELECT count(*) FROM nima.gemi_search_imports),
            (SELECT count(*) FROM nima.gemi_search_requests),
            (SELECT count(*) FROM nima.gemi_search_outcomes),
            (SELECT count(*) FROM nima.gemi_search_hits),
            (SELECT count(*) FROM nima.gemi_profile_versions),
            (SELECT count(*) FROM nima.gemi_imports),
            (SELECT count(*) FROM nima.gemi_observations),
            (SELECT count(*) FROM nima.outbox)""").fetchone()
    assert row is not None
    return row


FIVE = (1, 5, 5, 6, 6, 0, 0, 0)


def imported(dsn: str, root: Path, run: UUID, rules: object = RULES) -> object:
    return import_search_run(dsn, root, run, rules)  # type: ignore[arg-type]


def test_the_five_afm_run_is_imported_once_and_a_replay_changes_nothing(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root)
    before = snapshot(root)
    first = imported(pg_dsn, root, run)
    assert not first.reused and first.afms == 5 and first.requests == 5 and first.hits == 6  # type: ignore[attr-defined]
    assert counts(pg_dsn) == FIVE
    assert imported(pg_dsn, root, run).reused  # type: ignore[attr-defined]
    assert counts(pg_dsn) == FIVE and snapshot(root) == before
    with psycopg.connect(pg_dsn) as connection:
        assert connection.execute("SELECT manifest FROM nima.gemi_search_imports").fetchone() == (
            manifest_path(root, run).read_bytes(),
        )
        outcomes: dict[str, str] = dict(
            connection.execute("SELECT afm, outcome FROM nima.gemi_search_outcomes").fetchall()
        )
        assert outcomes == {
            A: "hit_single",
            B: "hit_multiple",
            C: "not_found_at_observation",
            D: "afm_mismatch",
            E: "truncated",
        }
        hits = connection.execute(
            "SELECT afm, registry_number, afm_matches FROM nima.gemi_search_hits "
            "ORDER BY afm, hit_index"
        ).fetchall()
        assert hits == [
            (A, "1", True),
            (B, "2", True),
            (B, "3", True),
            (D, "5", False),
            (E, "6", True),
            (E, "7", True),
        ]
        flags = connection.execute(
            "SELECT afm, truncated FROM nima.gemi_search_outcomes WHERE truncated"
        ).fetchall()
        assert flags == [(E, True)]
        # The hit's profile version points at the search response, with its exact location.
        pointers = connection.execute(
            "SELECT v.normalized->'fields'->'name_el'->>'json_pointer' "
            "FROM nima.gemi_search_hits h JOIN nima.gemi_profile_versions v "
            "ON v.source_id=h.source_id AND v.normalizer_version=h.normalizer_version "
            "AND v.raw_sha256=h.raw_sha256 WHERE h.afm=%s ORDER BY h.hit_index",
            (B,),
        ).fetchall()
        assert pointers == [("/searchResults/0/coNameEl",), ("/searchResults/1/coNameEl",)]


def test_a_retried_run_keeps_every_attempt_as_a_request(pg_dsn: str, tmp_path: Path) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, content=b"slow", headers={"retry-after": "0"})
        return example(request)

    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root, handle, (A,))
    imported(pg_dsn, root, run)
    with psycopg.connect(pg_dsn) as connection:
        rows = connection.execute(
            "SELECT attempt, status FROM nima.gemi_search_requests ORDER BY attempt"
        ).fetchall()
        final = connection.execute("SELECT attempt FROM nima.gemi_search_outcomes").fetchone()
    assert rows == [(1, 429), (2, 200)] and final == (2,)


def test_concurrent_identical_imports_converge(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: imported(pg_dsn, root, run), range(2)))
    assert sorted(r.reused for r in results) == [False, True]  # type: ignore[attr-defined]
    assert counts(pg_dsn) == FIVE


def test_a_quarantined_answer_is_an_outcome_without_hits(pg_dsn: str, tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params["afm"] == A:
            return httpx.Response(200, content=b'{"searchMetadata": 1}', headers=JSON)
        return httpx.Response(
            200, content=body([company("2", B)]), headers={"content-type": "text/html"}
        )

    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root, handle, (A, B))
    summary = imported(pg_dsn, root, run)
    assert (summary.hits, summary.unconfirmed_quarantines) == (0, 1)  # type: ignore[attr-defined]
    with psycopg.connect(pg_dsn) as connection:
        rows = connection.execute(
            "SELECT afm, outcome, hit_count, unconfirmed_quarantine "
            "FROM nima.gemi_search_outcomes ORDER BY afm"
        ).fetchall()
        recorded = connection.execute(
            "SELECT unconfirmed_quarantine_count FROM nima.gemi_search_imports"
        ).fetchone()
    assert rows == [(A, "quarantined", 0, False), (B, "quarantined", 0, True)]
    assert recorded == (1,)


def test_changed_run_manifest_conflicts_without_replacing_history(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root)
    imported(pg_dsn, root, run)
    original = manifest_path(root, run).read_bytes()
    manifest_path(root, run).write_bytes(json.dumps(json.loads(original)).encode())
    with pytest.raises(ImportFailure, match="^import_conflict$"):
        imported(pg_dsn, root, run)
    assert counts(pg_dsn) == FIVE


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        ("summary.companies", 9, "manifest_invalid"),
        ("summary.status", "failed", "run_incomplete"),
        ("connector_version", "gemi-profile-v1", "manifest_version"),
    ],
)
def test_a_run_that_does_not_verify_writes_nothing(
    pg_dsn: str, tmp_path: Path, path: str, value: object, reason: str
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root)
    edit(root, run, path, value)
    with pytest.raises(ImportFailure) as caught:
        imported(pg_dsn, root, run)
    assert caught.value.reason == reason
    assert counts(pg_dsn) == (0,) * 8


def test_a_profile_run_is_not_a_search_run_and_the_profile_tables_stay_untouched(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    profile = archive_run(root)
    with pytest.raises(ImportFailure, match="^manifest_version$"):
        imported(pg_dsn, root, profile)
    assert counts(pg_dsn) == (0,) * 8


def test_an_unmigrated_database_is_refused_before_any_write(tmp_path: Path, pg_dsn: str) -> None:
    root = tmp_path / "raw"
    run = search_run(root)
    with pytest.raises(ImportFailure, match="^database_schema$"):
        imported(pg_dsn, root, run)


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("statement", ["DELETE FROM nima.{}", "UPDATE nima.{} SET run_id=run_id"])
def test_search_evidence_is_immutable(
    pg_dsn: str, tmp_path: Path, table: str, statement: str
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    imported(pg_dsn, root, search_run(root))
    with (
        psycopg.connect(pg_dsn) as connection,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
    ):
        connection.execute(sql.SQL(statement).format(sql.Identifier(table)))


@pytest.mark.parametrize("table", TABLES)
def test_search_evidence_cannot_be_truncated(pg_dsn: str, tmp_path: Path, table: str) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    imported(pg_dsn, root, search_run(root))
    with (
        psycopg.connect(pg_dsn) as connection,
        pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
    ):
        connection.execute(sql.SQL("TRUNCATE nima.{} CASCADE").format(sql.Identifier(table)))


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
    ("table", "trigger", "assignment"),
    [
        (
            "gemi_search_outcomes",
            "gemi_search_outcomes_immutable",
            "truncated = NOT truncated WHERE outcome = 'afm_mismatch'",
        ),
        ("gemi_search_hits", "gemi_search_hits_immutable", "afm_matches = NOT afm_matches"),
        ("gemi_search_requests", "gemi_search_requests_immutable", "byte_length = byte_length + 1"),
        (
            "gemi_profile_versions",
            "gemi_versions_immutable",
            "normalized = jsonb_set(normalized, '{fields,reported_afm,value}', '\"x\"')",
        ),
    ],
)
def test_stored_conflicts_are_rejected_when_the_same_run_is_imported_again(
    pg_dsn: str, tmp_path: Path, table: str, trigger: str, assignment: str
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root)
    imported(pg_dsn, root, run)
    corrupt(pg_dsn, table, trigger, assignment)
    with pytest.raises(ImportFailure, match="^import_conflict$"):
        imported(pg_dsn, root, run)


def test_a_conflicting_profile_version_rolls_the_whole_import_back(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    first = search_run(root)
    imported(pg_dsn, root, first)
    corrupt(
        pg_dsn,
        "gemi_profile_versions",
        "gemi_versions_immutable",
        "normalized = jsonb_set(normalized, '{fields,reported_afm,value}', '\"x\"')",
    )
    # A new run repeating one answer byte for byte meets that answer's corrupted stored version.
    second = search_run(root, afms=(A,))
    before = counts(pg_dsn)
    with pytest.raises(ImportFailure, match="^import_conflict$"):
        imported(pg_dsn, root, second)
    assert counts(pg_dsn) == before


def test_two_hits_with_one_registry_number_in_an_answer_are_refused(
    pg_dsn: str, tmp_path: Path
) -> None:
    # The same company twice has one profile-version key but two evidence pointers, so the stored
    # version cannot equal both: the import conflicts and rolls back instead of picking one.
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body([company("2", A), company("2", A)]), headers=JSON)

    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root, handle, (A,))
    with pytest.raises(ImportFailure, match="^import_conflict$"):
        imported(pg_dsn, root, run)
    assert counts(pg_dsn) == (0,) * 8


@pytest.mark.parametrize(
    ("outcome", "status", "hit_count", "truncated"),
    [
        ("hit_single", 200, 2, False),
        ("hit_single", 200, 0, False),
        ("hit_multiple", 200, 1, False),
        ("truncated", 200, 1, False),
        ("not_found_at_observation", 200, 0, False),
        ("not_found_at_observation", 404, 1, False),
        ("quarantined", 200, 1, False),
        ("hit_single", 404, 1, False),
        ("afm_mismatch", 200, 0, False),
        ("bogus", 200, 1, False),
        ("hit_multiple", 200, 2, True),
    ],
)
def test_an_outcome_row_cannot_contradict_its_own_counts(
    pg_dsn: str, outcome: str, status: int, hit_count: int, truncated: bool
) -> None:
    migrate(pg_dsn)
    run, digest = uuid4(), "a" * 64
    with psycopg.connect(pg_dsn) as connection:
        connection.execute("INSERT INTO nima.raw_objects VALUES (%s, 10)", (digest,))
        connection.execute(
            "INSERT INTO nima.gemi_search_imports (run_id, import_version, archive_root, manifest, "
            "manifest_sha256, connector_version, normalizer_version, source_url, license, "
            "publisher, "
            "afm_count, request_count, hit_count, unconfirmed_quarantine_count) "
            "VALUES (%s, 'gemi-search-import-v1', '/x', 'm', %s, 'gemi-afm-search-v1', "
            "'gemi-company-v1', 'u', 'l', 'p', 1, 1, 0, 0)",
            (run, digest),
        )
        connection.execute(
            "INSERT INTO nima.gemi_search_requests (run_id, afm, attempt, started_at, finished_at, "
            "status, raw_sha256, byte_length, observed_at) "
            "VALUES (%s, %s, 1, now(), now(), %s, %s, 10, now())",
            (run, A, status, digest),
        )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO nima.gemi_search_outcomes (run_id, afm, attempt, outcome, status, "
                "raw_sha256, observed_at, truncated, unconfirmed_quarantine, hit_count) "
                "SELECT run_id, afm, attempt, %s, status, raw_sha256, observed_at, %s, false, %s "
                "FROM nima.gemi_search_requests WHERE run_id=%s",
                (outcome, truncated, hit_count, run),
            )
        # The same row is accepted when its own counts agree: the CHECK, not the keys, refused it.
        good = {200: ("hit_single", 1), 404: ("not_found_at_observation", 0)}[status]
        connection.execute(
            "INSERT INTO nima.gemi_search_outcomes (run_id, afm, attempt, outcome, status, "
            "raw_sha256, observed_at, truncated, unconfirmed_quarantine, hit_count) "
            "SELECT run_id, afm, attempt, %s, status, raw_sha256, observed_at, false, false, %s "
            "FROM nima.gemi_search_requests WHERE run_id=%s",
            (good[0], good[1], run),
        )
        connection.rollback()


def test_the_command_prints_counts_only_and_a_replay_reports_reuse(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    monkeypatch.delenv("NIMA_GEMI_API_KEY", raising=False)
    monkeypatch.setattr("httpx.Client", lambda **_: pytest.fail("Unexpected HTTP"))
    args = ["gemi", "import-afm", str(run), "--archive-dir", str(root)]
    for reused in (False, True):
        assert main(args) == 0
        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["status"] == "imported" and result["reused"] is reused
        assert (result["afms"], result["requests"], result["hits"]) == (5, 5, 6)
        assert result["import_version"] == "gemi-search-import-v1"
        assert A not in out and B not in out and "Άλφα" not in out
    edit(root, run, "summary.failure", "private-person-and-secret")
    assert main(args) == 1
    failure = capsys.readouterr().out
    assert json.loads(failure)["failure"] == "run_incomplete"
    assert "private-person-and-secret" not in failure


def test_the_command_without_a_database_fails_before_touching_the_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    root = tmp_path / "absent"
    assert main(["gemi", "import-afm", str(UUID(int=1)), "--archive-dir", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
    assert not root.exists()


def test_a_database_failure_is_reported_with_a_fixed_reason(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(pg_dsn)
    root = tmp_path / "raw"
    run = search_run(root)

    def broken(*_: object) -> None:
        raise psycopg.OperationalError("private driver details")

    monkeypatch.setattr("nima.storage.gemi._commit_search", broken)
    with pytest.raises(ImportFailure, match="^database$"):
        imported(pg_dsn, root, run)
    assert counts(pg_dsn) == (0,) * 8


def _seed(connection: psycopg.Connection[tuple[object, ...]]) -> tuple[UUID, str]:
    """A valid import with one request, one outcome and one hit, written without the importer."""
    run, digest = uuid4(), "b" * 64
    connection.execute("INSERT INTO nima.raw_objects VALUES (%s, 10)", (digest,))
    connection.execute(
        "INSERT INTO nima.gemi_search_imports (run_id, import_version, archive_root, manifest, "
        "manifest_sha256, connector_version, normalizer_version, source_url, license, "
        "publisher, afm_count, request_count, hit_count, unconfirmed_quarantine_count) "
        "VALUES (%s, 'gemi-search-import-v1', '/x', 'm', %s, 'gemi-afm-search-v1', "
        "'gemi-company-v1', 'u', 'l', 'p', 1, 1, 1, 0)",
        (run, digest),
    )
    connection.execute(
        "INSERT INTO nima.gemi_search_requests (run_id, afm, attempt, started_at, finished_at, "
        "status, raw_sha256, byte_length, observed_at) "
        "VALUES (%s, %s, 1, now(), now(), 200, %s, 10, now())",
        (run, A, digest),
    )
    connection.execute(
        "INSERT INTO nima.gemi_search_outcomes (run_id, afm, attempt, outcome, status, raw_sha256, "
        "observed_at, truncated, unconfirmed_quarantine, hit_count) "
        "SELECT run_id, afm, attempt, 'hit_multiple', status, raw_sha256, observed_at, false, "
        "false, 2 FROM nima.gemi_search_requests WHERE run_id=%s",
        (run,),
    )
    for number in ("7", "8"):
        connection.execute(
            "INSERT INTO nima.gemi_profile_versions VALUES (%s, 'gemi-company-v1', %s, %s)",
            (
                f"gemi:{number}",
                digest,
                json.dumps(
                    {
                        "source_id": f"gemi:{number}",
                        "normalizer_version": "gemi-company-v1",
                        "response_sha256": digest,
                    }
                ),
            ),
        )
    connection.execute(
        "INSERT INTO nima.gemi_search_hits VALUES (%s, %s, 0, '7', true, %s, 'gemi:7', "
        "'gemi-company-v1')",
        (run, A, digest),
    )
    return run, digest


HIT = "INSERT INTO nima.gemi_search_hits VALUES (%s, %s, %s, %s, true, %s, %s, 'gemi-company-v1')"
REQUEST = (
    "INSERT INTO nima.gemi_search_requests (run_id, afm, attempt, started_at, finished_at, "
    "status, failure, raw_sha256, byte_length, observed_at) VALUES "
    "(%s, %s, 2, now(), now() + interval '1 second', %s, %s, %s, %s, %s)"
)


@pytest.mark.parametrize(
    ("statement", "values", "error"),
    [
        # A second hit repeating the first one's registry number, a wrong source id, bad positions.
        (HIT, (1, "7", "gemi:7"), psycopg.errors.UniqueViolation),
        (HIT, (1, "8", "gemi:7"), psycopg.errors.CheckViolation),
        (HIT, (20, "8", "gemi:8"), psycopg.errors.CheckViolation),
        (HIT, (1, "08", "gemi:08"), psycopg.errors.CheckViolation),
        (HIT, (1, "0", "gemi:0"), psycopg.errors.CheckViolation),
    ],
)
def test_a_hit_row_cannot_repeat_a_company_or_name_another_source(
    pg_dsn: str, statement: str, values: tuple[object, ...], error: type[Exception]
) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        run, digest = _seed(connection)
        index, number, source = values
        with pytest.raises(error), connection.transaction():
            connection.execute(statement, (run, A, index, number, digest, source))
        # The same row with its own number is accepted: the rule, not the keys, refused it.
        connection.execute(statement, (run, A, 1, "8", digest, "gemi:8"))
        connection.rollback()


@pytest.mark.parametrize(
    ("afm", "status", "failure", "sha", "length", "observed", "ok"),
    [
        ("12345678", 200, None, True, 10, "now()", False),
        ("000000000", 200, None, True, 10, "now()", False),
        ("12345678a", 200, None, True, 10, "now()", False),
        (A, 200, None, False, 10, "now()", False),  # a body without its hash
        (A, 200, None, True, None, "now()", False),  # a hash without its length
        (A, None, "transport", False, None, None, True),  # a failure needs no body
        (A, 200, "transport", True, 10, "now()", False),  # a failure cannot carry a body
        (A, 200, None, True, 10, "now() + interval '1 hour'", False),  # observed after it ended
        (A, 200, None, True, 10, "now()", True),
    ],
)
def test_a_request_row_keeps_its_afm_body_and_failure_consistent(
    pg_dsn: str,
    afm: str,
    status: int | None,
    failure: str | None,
    sha: bool,
    length: int | None,
    observed: str | None,
    ok: bool,
) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        run, digest = _seed(connection)
        statement = REQUEST.replace("%s, %s, 2", "%s, %s, 2").replace(
            "now() + interval '1 second', %s, %s, %s, %s, %s)",
            "now() + interval '1 second', %s, %s, %s, %s, "
            + (observed if observed is not None else "NULL")
            + ")",
        )
        values = (run, afm, status, failure, digest if sha else None, length)
        if ok:
            connection.execute(statement, values)
        else:
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(statement, values)
        connection.rollback()


@pytest.mark.parametrize(
    "override",
    [
        {"import_version": "gemi-search-import-v0"},
        {"connector_version": "gemi-profile-v1"},
        {"request_count": 0},
        {"request_count": 76},
        {"afm_count": 2},  # more AFMs than requests
        {"afm_count": 26, "request_count": 30},
        {"afm_count": 0},
        {"unconfirmed_quarantine_count": 2},  # more than the AFMs searched
        {"hit_count": 501},
    ],
)
def test_an_import_row_keeps_its_versions_and_counts_in_range(
    pg_dsn: str, override: dict[str, object]
) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        _, digest = _seed(connection)
        row: dict[str, object] = {
            "import_version": "gemi-search-import-v1",
            "archive_root": "/y",
            "manifest": b"m",
            "manifest_sha256": digest,
            "connector_version": "gemi-afm-search-v1",
            "normalizer_version": "gemi-company-v1",
            "source_url": "u",
            "license": "l",
            "publisher": "p",
            "afm_count": 1,
            "request_count": 1,
            "hit_count": 0,
            "unconfirmed_quarantine_count": 0,
        }
        statement = (
            f"INSERT INTO nima.gemi_search_imports (run_id, {', '.join(row)}) "
            f"VALUES (%s{', %s' * len(row)})"
        )
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(statement, (uuid4(), *{**row, **override}.values()))
        connection.execute(statement, (uuid4(), *row.values()))
        connection.rollback()


def test_every_search_table_carries_its_immutability_and_truncate_guards(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with psycopg.connect(pg_dsn) as connection:
        names = {
            r[0]
            for r in connection.execute(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
            ).fetchall()
        }
    for table in TABLES:
        assert f"{table}_immutable" in names and f"{table}_no_truncate" in names
