"""The census counts how our own KIMDIS records cite Diavgeia decisions, read-only.

It answers two questions before any Diavgeia request is made: how many KIMDIS records carry a
``diavgeiaADA`` citation, and how many records share each cited decision (a widely shared one is an
umbrella, not a one-to-one link). It reads stored data only and reports counts and public ADA
identifiers, never names, tax numbers or amounts.
"""

import json
import runpy
import sys
from pathlib import Path
from typing import cast

import httpx
import psycopg
import pytest

from nima.ingestion.archive import Archive
from nima.ingestion.collector import collect
from nima.ingestion.config import Limits
from nima.storage.postgres import migrate
from scripts.diavgeia_link_census import census, main, open_read_only
from tests.synthetic_sources import LedgerAdapter, ledger_page
from tests.test_collection import QUERY, Clock, body


def collect_pages(dsn: str, root: Path, pages: list[bytes]) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=pages[int(request.url.params["page"])])
    )
    with httpx.Client(transport=transport) as client:
        collect(QUERY, Limits(), Archive(root), client=client, clock=Clock(), database_dsn=dsn)


def cited(page: int, total: int, ada: str | None, title: str = "Synthetic") -> bytes:
    row: dict[str, object] = {"title": title}
    if ada is not None:
        row["diavgeiaADA"] = ada
    return body(page, total, **row)


FIVE = [
    cited(0, 5, "ADA-A"),
    cited(1, 5, "ADA-A"),
    cited(2, 5, "ADA-B"),
    cited(3, 5, None),
    cited(4, 5, None),
]


def test_an_empty_database_reports_zeros_and_no_rows(pg_dsn: str) -> None:
    migrate(pg_dsn)
    assert census(pg_dsn) == {
        "kimdis_records": 0,
        "cite_a_diavgeia_ada": 0,
        "distinct_cited_decisions": 0,
        "decisions_cited_by_more_than_one_record": 0,
        "max_records_citing_one_decision": 0,
        "most_shared": [],
    }


def test_it_counts_records_that_cite_and_how_widely_each_decision_is_shared(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", FIVE)
    assert census(pg_dsn) == {
        "kimdis_records": 5,
        "cite_a_diavgeia_ada": 3,
        "distinct_cited_decisions": 2,
        "decisions_cited_by_more_than_one_record": 1,
        "max_records_citing_one_decision": 2,
        "most_shared": [
            {"decision": "diavgeia:ADA-A", "kimdis_records": 2},
            {"decision": "diavgeia:ADA-B", "kimdis_records": 1},
        ],
    }


def test_a_record_with_several_stored_versions_is_counted_once(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "first", FIVE)
    changed = [
        cited(n, 5, "ADA-A" if n < 2 else ("ADA-B" if n == 2 else None), "Changed")
        for n in range(5)
    ]
    collect_pages(pg_dsn, tmp_path / "second", changed)
    with psycopg.connect(pg_dsn) as c:
        versions = c.execute(
            "SELECT count(*) FROM nima.record_versions WHERE source_id LIKE 'kimdis:%'"
        ).fetchone()
    assert versions == (10,)
    result = census(pg_dsn)
    assert result["kimdis_records"] == 5 and result["cite_a_diavgeia_ada"] == 3
    assert cast(list[object], result["most_shared"])[0] == {
        "decision": "diavgeia:ADA-A",
        "kimdis_records": 2,
    }


def test_records_of_other_sources_are_not_counted(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", FIVE)
    page = ledger_page(0, 1, 1, [("L-0001", "1,00", "x")])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=page))
    with httpx.Client(transport=transport) as client:
        collect(
            None,
            Limits(),
            Archive(tmp_path / "ledger"),
            client=client,
            clock=Clock(),
            database_dsn=pg_dsn,
            adapter=LedgerAdapter(),
        )
    assert census(pg_dsn)["kimdis_records"] == 5


def test_the_most_shared_list_is_limited_and_ordered_by_count_then_identifier(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    pages = [
        cited(n, 6, ada)
        for n, ada in enumerate(["ADA-C", "ADA-B", "ADA-B", "ADA-A", "ADA-A", "ADA-D"])
    ]
    collect_pages(pg_dsn, tmp_path / "raw", pages)
    top = census(pg_dsn, top=3)["most_shared"]
    assert top == [
        {"decision": "diavgeia:ADA-A", "kimdis_records": 2},
        {"decision": "diavgeia:ADA-B", "kimdis_records": 2},
        {"decision": "diavgeia:ADA-C", "kimdis_records": 1},
    ]


def test_the_session_is_read_only(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with (
        open_read_only(pg_dsn) as connection,
        pytest.raises(psycopg.errors.ReadOnlySqlTransaction),
    ):
        connection.execute("DELETE FROM nima.record_versions")


def test_the_command_prints_only_counts_and_public_identifiers(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", FIVE)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    assert main(["--top", "1"]) == 0
    printed = capsys.readouterr().out
    report = json.loads(printed)
    assert report["kimdis_records"] == 5 and len(report["most_shared"]) == 1
    assert "Synthetic" not in printed and "TEST-" not in printed


@pytest.mark.parametrize("top", ["0", "101", "x"])
def test_an_unreasonable_row_limit_is_refused(top: str) -> None:
    with pytest.raises(SystemExit) as refused:
        main(["--top", top])
    assert refused.value.code == 2


def test_a_missing_database_url_fails_without_echoing_anything(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    assert main([]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "failure": "configuration"}


def test_an_unreachable_database_fails_with_a_fixed_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "NIMA_DATABASE_URL", "host=127.0.0.1 port=1 user=nobody dbname=none connect_timeout=2"
    )
    assert main([]) == 1
    out = capsys.readouterr().out
    assert json.loads(out) == {"status": "failed", "failure": "database"}
    assert "nobody" not in out


def test_running_the_module_exits_with_the_command_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    monkeypatch.delitem(sys.modules, "scripts.diavgeia_link_census", raising=False)
    monkeypatch.setattr(sys, "argv", ["diavgeia_link_census"])
    with pytest.raises(SystemExit) as finished:
        runpy.run_module("scripts.diavgeia_link_census", run_name="__main__")
    assert finished.value.code == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"
