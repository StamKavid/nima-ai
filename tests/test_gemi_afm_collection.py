"""L3: one GEMI search per AFM through the shared transport; archive first, nothing chosen.

The transport rules (retry, 401, 429, body limits, budgets) are exercised for both request kinds in
``test_gemi_collection``. These tests cover what is specific to the search: the request, the
hand-calculated example of the spec, input checks and the run record.
"""

import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from nima.ingestion.gemi import GemiSearchSummary, SearchRules, collect_afm
from nima.sources.gemi_search import parse_search, queryable_afm
from nima.storage.gemi_archive import ImportFailure, verify_run
from tests.test_collection import Clock
from tests.test_gemi_search import body, company

KEY = "synthetic-test-credential"
A, B, C, D, E = "100000001", "100000002", "100000003", "100000004", "100000005"
JSON = {"content-type": "application/json"}
RULES = SearchRules(
    queryable=queryable_afm,
    parse=lambda raw, afm, status: parse_search(raw, queried_afm=afm, http_status=status),
)


def example(request: httpx.Request) -> httpx.Response:
    """The five synthetic answers of the spec: single, multiple, 404, mismatch, truncated."""
    afm = request.url.params["afm"]
    if afm == A:
        return httpx.Response(200, content=body([company("1", A)]), headers=JSON)
    if afm == B:
        return httpx.Response(
            200, content=body([company("2", B), company("3", B, isBranch=True)]), headers=JSON
        )
    if afm == D:
        return httpx.Response(200, content=body([company("5", "999999999")]), headers=JSON)
    if afm == E:
        content = body([company("6", E), company("7", E)], total=3)
        return httpx.Response(200, content=content, headers=JSON)
    return httpx.Response(404, content=b"missing")


def collect(
    afms: tuple[str, ...], root: Path, handler: object = example, **options: object
) -> GemiSearchSummary:
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:  # type: ignore[arg-type]
        return collect_afm(afms, root, rules=RULES, api_key=KEY, client=client, **options)  # type: ignore[arg-type]


def test_the_five_afm_example_is_collected_archive_first_with_nothing_chosen(
    tmp_path: Path,
) -> None:
    seen: list[httpx.Request] = []
    clock = Clock()

    def handle(request: httpx.Request) -> httpx.Response:
        pending = json.loads(next((tmp_path / "raw" / "runs").glob("*/manifest.json")).read_text())
        assert pending["attempts"][-1]["state"] == "started"
        seen.append(request)
        return example(request)

    result = collect((A, B, C, D, E), tmp_path / "raw", handle, clock=clock)
    assert result.status == "complete" and result.collection_complete
    assert result.normalization_complete
    assert (result.requested, result.attempts, result.found, result.not_found) == (5, 5, 4, 1)
    assert (result.quarantined, result.companies) == (0, 6)
    assert result.outcome_counts == {
        "hit_single": 1,
        "hit_multiple": 1,
        "not_found_at_observation": 1,
        "afm_mismatch": 1,
        "truncated": 1,
    }
    assert clock.waits == [7.5] * 4
    first = seen[0]
    assert first.method == "GET" and first.headers["api_key"] == KEY
    assert first.url.path == "/api/opendata/v1/companies" and first.url.host.endswith("gr")
    assert dict(first.url.params) == {"afm": A, "resultsSize": "20"}
    assert first.headers["accept-encoding"] == "identity"
    run = tmp_path / "raw" / "runs" / result.run_id
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["connector_version"] == "gemi-afm-search-v1"
    assert manifest["normalizer_version"] == "gemi-company-v1"
    assert manifest["inputs"] == manifest["afms"] == [A, B, C, D, E]
    assert manifest["outcomes"] == {
        A: "hit_single",
        B: "hit_multiple",
        C: "not_found_at_observation",
        D: "afm_mismatch",
        E: "truncated",
    }
    assert [a["afm"] for a in manifest["attempts"]] == [A, B, C, D, E]
    assert all("registry_number" not in a for a in manifest["attempts"])
    assert KEY not in json.dumps(manifest) and manifest["license"] == "ODC-BY-1.0"
    assert len(list((tmp_path / "raw" / "objects").glob("*/*.body"))) == 5
    rows = [json.loads(line) for line in (run / "normalized.jsonl").read_text().splitlines()]
    assert [(r["afm"], r["afm_matches"]) for r in rows] == [
        (A, True),
        (B, True),
        (B, True),
        (D, False),
        (E, True),
        (E, True),
    ]
    assert [r["truncated"] for r in rows] == [False] * 4 + [True] * 2
    assert rows[1]["profile"]["fields"]["registry_number"]["value"] == 2
    assert rows[3]["profile"]["fields"]["reported_afm"]["value"] == "999999999"


def test_a_run_is_identical_for_any_input_order_and_duplicates_are_sent_once(
    tmp_path: Path,
) -> None:
    sent: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.params["afm"])
        return example(request)

    one = collect((A, B, C), tmp_path / "one", handle, clock=Clock())
    two = collect((C, B, A, B, A), tmp_path / "two", handle, clock=Clock())
    assert sent == [A, B, C, C, B, A] and one.requested == two.requested == 3
    manifests = [
        json.loads((tmp_path / name / "runs" / r.run_id / "manifest.json").read_text())
        for name, r in (("one", one), ("two", two))
    ]
    assert manifests[0]["outcomes"] == manifests[1]["outcomes"]
    assert manifests[1]["inputs"] == [C, B, A, B, A]


def test_a_search_answer_that_is_not_the_documented_shape_is_quarantined_with_raw_kept(
    tmp_path: Path,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params["afm"] == A:
            return httpx.Response(200, content=b'{"searchMetadata": 1}', headers=JSON)
        return httpx.Response(200, content=body([company()]), headers={"content-type": "text/html"})

    result = collect((A, B), tmp_path / "raw", handle, clock=Clock())
    assert result.status == "quarantined" and result.quarantined == 2 and result.found == 0
    assert result.collection_complete and not result.normalization_complete
    run = tmp_path / "raw" / "runs" / result.run_id
    rows = [json.loads(line) for line in (run / "quarantine.jsonl").read_text().splitlines()]
    assert [r["field"] for r in rows] == ["/searchMetadata", "content_type"]
    assert {r["afm"] for r in rows} == {A, B}
    assert len(list((tmp_path / "raw" / "objects").glob("*/*.body"))) == 2
    assert result.outcome_counts == {"quarantined": 2}


@pytest.mark.parametrize(
    ("key", "afms"),
    [
        ("", (A,)),
        ("api-docs-key", (A,)),
        (KEY, ()),
        (KEY, ("12345678",)),
        (KEY, ("1234567890",)),
        (KEY, ("000000000",)),
        (KEY, ("１２３４５６７８９",)),
        (KEY, ("12345678a",)),
        (KEY, (A + "\n",)),
        (KEY, tuple(f"1{i:08d}" for i in range(26))),
    ],
)
def test_invalid_inputs_precede_archive_or_http(
    tmp_path: Path, key: str, afms: tuple[str, ...]
) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("HTTP"))) as client,
        pytest.raises(ValueError),
    ):
        collect_afm(afms, tmp_path / "raw", rules=RULES, api_key=key, client=client)
    assert not (tmp_path / "raw").exists()


def test_twenty_five_afms_are_the_most_one_run_accepts(tmp_path: Path) -> None:
    afms = tuple(f"1{i:08d}" for i in range(25))
    result = collect(afms, tmp_path / "raw", lambda _: httpx.Response(404), clock=Clock())
    assert result.requested == 25 and result.not_found == 25


def test_the_command_needs_a_key_before_any_client_and_prints_counts_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from nima.__main__ import main

    args = ["ingest", "gemi-afm", "--afm", A, "--afm", B, "--archive-dir", str(tmp_path / "raw")]
    real_client = httpx.Client
    monkeypatch.delenv("NIMA_GEMI_API_KEY", raising=False)
    monkeypatch.setattr("nima.__main__.httpx.Client", lambda: pytest.fail("client first"))
    assert main(args) == 2 and not (tmp_path / "raw").exists()
    capsys.readouterr()
    monkeypatch.setenv("NIMA_GEMI_API_KEY", KEY)
    assert main(["ingest", "gemi-afm", "--afm", "bad", "--archive-dir", str(tmp_path / "x")]) == 2
    assert not (tmp_path / "x").exists()
    capsys.readouterr()
    monkeypatch.setattr("nima.ingestion.gemi.SystemClock", Clock)
    monkeypatch.setattr(
        "nima.__main__.httpx.Client",
        lambda: real_client(transport=httpx.MockTransport(example)),
    )
    assert main(args) == 0
    output = capsys.readouterr()
    summary = json.loads(output.out)
    assert summary["found"] == 2 and summary["companies"] == 3
    assert KEY not in output.out + output.err
    assert A not in output.out and B not in output.out and "Άλφα" not in output.out


def test_a_search_run_is_not_importable_as_a_profile_run(tmp_path: Path) -> None:
    result = collect((A,), tmp_path / "raw", clock=Clock())
    with pytest.raises(ImportFailure):
        verify_run(tmp_path / "raw", UUID(result.run_id))
