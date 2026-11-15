"""Comparison CLI configuration, fixed failures and real offline publication."""

import json
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from nima.__main__ import main
from nima.identity import AssessmentError, ComparisonError
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.postgres import MigrationError


def arguments(output: Path) -> list[str]:
    return [
        "identities",
        "compare",
        str(UUID(int=1)),
        "--gemi-import",
        str(UUID(int=2)),
        "--projection-version",
        PROJECTION_VERSION,
        "--output-dir",
        str(output),
    ]


def test_comparison_route_passes_explicit_configuration_and_safe_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-dsn")

    def compare(
        dsn: str, run: UUID, imports: list[UUID], version: str, output: Path, *, max_mentions: int
    ) -> dict[str, object]:
        assert (dsn, run, imports, version, output, max_mentions) == (
            "private-dsn",
            UUID(int=1),
            [UUID(int=2)],
            PROJECTION_VERSION,
            tmp_path,
            17,
        )
        return {"status": "complete", "report_sha256": "a" * 64, "automatic_identity_links": 0}

    monkeypatch.setattr("nima.__main__.compare_run", compare, raising=False)
    assert main([*arguments(tmp_path), "--max-mentions", "17"]) == 0
    output = capsys.readouterr()
    assert output.err == "" and json.loads(output.out)["automatic_identity_links"] == 0
    assert "private-dsn" not in output.out


@pytest.mark.parametrize("fault", ["run", "import", "integer", "unknown", "missing"])
def test_parser_failures_do_not_echo_values_or_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    args = arguments(tmp_path / "private-sentinel")
    if fault == "run":
        args[2] = "private-sentinel"
    elif fault == "import":
        args[4] = "private-sentinel"
    elif fault == "integer":
        args += ["--max-mentions", "private-sentinel"]
    elif fault == "unknown":
        args += ["--private-sentinel"]
    else:
        args.pop(3)
    assert main(args) == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": "configuration"}
    assert output.err == "" and "private-sentinel" not in output.out


@pytest.mark.parametrize(
    "error,code,reason",
    [
        (ComparisonError("registry_incomplete"), 1, "registry_incomplete"),
        (ComparisonError("comparison_limit"), 1, "comparison_limit"),
        (AssessmentError("projection_incomplete"), 1, "projection_incomplete"),
        (AssessmentError("output_conflict"), 1, "output_conflict"),
        (MigrationError("private-sentinel"), 1, "database_schema"),
        (psycopg.OperationalError("private-sentinel"), 1, "database"),
        (OSError("private-sentinel"), 1, "output_io"),
        (ValueError("private-sentinel"), 2, "configuration"),
        (KeyboardInterrupt("private-sentinel"), 130, "interrupted"),
    ],
)
def test_failure_mapping_is_fixed_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: BaseException,
    code: int,
    reason: str,
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")

    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise error

    monkeypatch.setattr("nima.__main__.compare_run", fail)
    assert main(arguments(tmp_path / "private-sentinel")) == code
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "failed", "failure": reason}
    assert output.err == "" and "private-sentinel" not in output.out


@pytest.mark.parametrize("fault", ["duplicate", "count", "zero", "over", "version", "database"])
def test_invalid_configuration_never_reaches_database_or_creates_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    monkeypatch.setenv("NIMA_DATABASE_URL", "private-sentinel")
    args = arguments(tmp_path / "absent")
    if fault == "duplicate":
        args += ["--gemi-import", str(UUID(int=2))]
    elif fault == "count":
        for i in range(3, 13):
            args += ["--gemi-import", str(UUID(int=i))]
    elif fault in {"zero", "over"}:
        args += ["--max-mentions", "0" if fault == "zero" else "10001"]
    elif fault == "version":
        args[6] = "private-sentinel"
    else:
        monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        "nima.identity.registry_cohort.check_schema",
        lambda *a: pytest.fail("invalid configuration reached database"),
    )
    assert main(args) == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["failure"] == "configuration" and output.err == ""
    assert "private-sentinel" not in output.out and not (tmp_path / "absent").exists()


def test_comparison_help_lists_explicit_selectors_and_bounds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["identities", "compare", "--help"])
    assert stopped.value.code == 0
    output = capsys.readouterr()
    assert all(
        flag in output.out for flag in ("--gemi-import", "--max-mentions", "--projection-version")
    )
    assert output.err == ""


def test_real_offline_cli_replays_with_no_http_or_api_key_access(
    pg_dsn: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import os

    from tests.test_gemi_import import counts as registry_counts
    from tests.test_gemi_import_archive import snapshot
    from tests.test_identity_report import seed
    from tests.test_kimdis_pages import record
    from tests.test_page_store import counts
    from tests.test_registry_cohort import registry_import

    run = seed(
        pg_dsn,
        tmp_path,
        {
            **record(),
            "contractingDataDetails": {
                "contractingMembersDataList": [
                    {"name": "private-sentinel", "vatNumber": "001234567", "country": {"key": "GR"}}
                ]
            },
        },
    )
    selected = registry_import(pg_dsn, tmp_path)
    monkeypatch.setenv("NIMA_DATABASE_URL", pg_dsn)
    monkeypatch.setattr("httpx.Client", lambda **kw: pytest.fail("comparison opened HTTP client"))
    original = os.environ.get

    def get(key: str, default: str | None = None) -> str | None:
        assert key != "NIMA_GEMI_API_KEY"
        return original(key, default)

    monkeypatch.setattr(os.environ, "get", get)
    output = tmp_path / "reports"
    args = arguments(output)
    args[2], args[4] = str(run), str(selected)
    before = counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")
    summaries = []
    for _ in range(2):
        assert main(args) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        for value in ("private-sentinel", "001234567", str(output), pg_dsn, "Άλφα"):
            assert value not in captured.out
        summaries.append(json.loads(captured.out))
    assert summaries[0] == summaries[1] and summaries[0]["automatic_identity_links"] == 0
    assert summaries[0]["mention_count"] == 2
    assert len(list(output.glob("*.json"))) == 1
    report = json.loads(next(output.glob("*.json")).read_bytes())
    assert report["occurrences"][1]["comparison"]["outcome"] == "reported_identifier_agreement"
    assert (counts(pg_dsn), registry_counts(pg_dsn), snapshot(tmp_path / "gemi")) == before
    args[4] = str(UUID(int=99))
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "registry_import_unavailable"
