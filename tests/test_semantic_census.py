"""The semantic census measures date shapes and tax-ID classes in stored records, read-only.

It exists so the V1-05 time model is written from measured formats instead of a guess. It reports
counts and shapes (each digit replaced by ``9``, each letter by ``A``), never a date, name, tax
number, amount or title.
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
from scripts.semantic_census import census, main, open_read_only
from tests.synthetic_sources import LedgerAdapter, ledger_page
from tests.test_collection import QUERY, Clock, body


def collect_pages(dsn: str, root: Path, pages: list[bytes]) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=pages[int(request.url.params["page"])])
    )
    with httpx.Client(transport=transport) as client:
        collect(QUERY, Limits(), Archive(root), client=client, clock=Clock(), database_dsn=dsn)


def member(vat: str | None, country: str | None) -> dict[str, object]:
    row: dict[str, object] = {"name": "Synthetic supplier", "vatNumber": vat}
    if country is not None:
        row["country"] = {"key": country}
    return row


def record(
    page: int,
    total: int,
    submitted: str | None,
    updated: str | None,
    suppliers: list[dict[str, object]] | None,
    title: str = "Synthetic",
) -> bytes:
    row: dict[str, object] = {"title": title}
    if submitted is not None:
        row["submissionDate"] = submitted
    if updated is not None:
        row["lastUpdateDate"] = updated
    if suppliers is not None:
        row["contractingDataDetails"] = {"contractingMembersDataList": suppliers}
    return body(page, total, **row)


def six(title: str = "Synthetic") -> list[bytes]:
    return [
        record(
            0,
            6,
            "2026-03-10",
            "2026-03-11T08:15:00",
            [member("123456789", "GR"), member("000000000", "GR"), member("987654321", "GR")],
            title,
        ),
        record(
            1,
            6,
            "10/03/2026",
            None,
            [member("111111111", "EL"), member("012345678", "GR"), member("\t 123456780\n ", "GR")],
            title,
        ),
        record(
            2,
            6,
            "",
            "2026-03-10T08:15:00+02:00",
            [
                member("12345", "GR"),
                member("12345678", "GR"),
                member("1234567890", None),
                member("12345678A", "GR"),
            ],
            title,
        ),
        record(
            3,
            6,
            "2026-03-10T08:15:00+02:00",
            None,
            [member("", "GR"), member("١٢٣٤٥٦٧٨٩", "GR")],
            title,
        ),
        record(4, 6, "2026-03-12", "2026-03-12T09:00:00", None, title),
        record(5, 6, "2026-03-13", None, [], title),
    ]


EMPTY_CLASSES = {
    "missing_or_null": 0,
    "non_ascii": 0,
    "all_zero": 0,
    "repeated_digit": 0,
    "sequential_run": 0,
    "leading_zero": 0,
    "other_nine_digits": 0,
    "nine_chars_not_all_digits": 0,
    "shorter_than_nine": 0,
    "longer_than_nine": 0,
}


def test_an_empty_database_reports_zeros_and_no_rows(pg_dsn: str) -> None:
    migrate(pg_dsn)
    empty_field = {"missing_or_null": 0, "text": 0, "distinct_shapes": 0, "shapes": []}
    assert census(pg_dsn) == {
        "kimdis_records": 0,
        "record_versions": 0,
        "date_fields": {"source_submitted_at": empty_field, "source_updated_at": empty_field},
        "supplier_lists": {"missing_or_null": 0, "empty": 0, "non_empty": 0},
        "supplier_tax_ids": {"occurrences": 0, "needs_whitespace_trim": 0, **EMPTY_CLASSES},
        "supplier_countries": [],
    }


def test_it_reports_date_shapes_tax_id_classes_and_countries(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", six())
    assert census(pg_dsn) == {
        "kimdis_records": 6,
        "record_versions": 6,
        "date_fields": {
            "source_submitted_at": {
                "missing_or_null": 1,
                "text": 5,
                "distinct_shapes": 3,
                "shapes": [
                    {"shape": "9999-99-99", "versions": 3},
                    {"shape": "99/99/9999", "versions": 1},
                    {"shape": "9999-99-99A99:99:99+99:99", "versions": 1},
                ],
            },
            "source_updated_at": {
                "missing_or_null": 3,
                "text": 3,
                "distinct_shapes": 2,
                "shapes": [
                    {"shape": "9999-99-99A99:99:99", "versions": 2},
                    {"shape": "9999-99-99A99:99:99+99:99", "versions": 1},
                ],
            },
        },
        "supplier_lists": {"missing_or_null": 1, "empty": 1, "non_empty": 4},
        "supplier_tax_ids": {
            "occurrences": 12,
            "needs_whitespace_trim": 1,
            **{name: 1 for name in EMPTY_CLASSES},
            "sequential_run": 2,
            "shorter_than_nine": 2,
        },
        "supplier_countries": [
            {"country": "GR", "occurrences": 10},
            {"country": "EL", "occurrences": 1},
            {"country": None, "occurrences": 1},
        ],
    }


def test_the_row_limit_applies_to_shapes_and_countries(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", six())
    result = census(pg_dsn, top=1)
    fields = cast(dict[str, dict[str, object]], result["date_fields"])
    assert fields["source_submitted_at"]["shapes"] == [{"shape": "9999-99-99", "versions": 3}]
    assert fields["source_submitted_at"]["distinct_shapes"] == 3
    assert result["supplier_countries"] == [{"country": "GR", "occurrences": 10}]


def test_a_record_with_several_stored_versions_is_counted_once_as_a_record(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "first", six())
    collect_pages(pg_dsn, tmp_path / "second", six("Changed"))
    result = census(pg_dsn)
    assert result["kimdis_records"] == 6 and result["record_versions"] == 12


def test_records_of_other_sources_are_not_counted(pg_dsn: str, tmp_path: Path) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", six())
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
    result = census(pg_dsn)
    assert result["kimdis_records"] == 6 and result["record_versions"] == 6


def test_the_session_is_read_only(pg_dsn: str) -> None:
    migrate(pg_dsn)
    with (
        open_read_only(pg_dsn) as connection,
        pytest.raises(psycopg.errors.ReadOnlySqlTransaction),
    ):
        connection.execute("DELETE FROM nima.record_versions")


def test_the_command_prints_no_input_value(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", six())
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    assert main(["--top", "5"]) == 0
    printed = capsys.readouterr().out
    assert json.loads(printed)["kimdis_records"] == 6
    for value in ("2026", "12345", "11111", "Synthetic", "TEST-", "Synthetic supplier", "١"):
        assert value not in printed


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
    monkeypatch.delitem(sys.modules, "scripts.semantic_census", raising=False)
    monkeypatch.setattr(sys, "argv", ["semantic_census"])
    with pytest.raises(SystemExit) as finished:
        runpy.run_module("scripts.semantic_census", run_name="__main__")
    assert finished.value.code == 2
    assert json.loads(capsys.readouterr().out)["failure"] == "configuration"


def test_a_long_date_text_is_reduced_to_a_capped_shape_of_letters(
    pg_dsn: str, tmp_path: Path
) -> None:
    migrate(pg_dsn)
    collect_pages(pg_dsn, tmp_path / "raw", [record(0, 1, "x" * 60 + "9", None, None)])
    submitted = cast(dict[str, dict[str, object]], census(pg_dsn)["date_fields"])[
        "source_submitted_at"
    ]
    assert submitted["shapes"] == [{"shape": "A" * 40, "versions": 1}]
