"""L4: a GEMI search run verifies from its archived original bytes alone, read-only.

Synthetic runs only. The verifier recomputes every outcome from the stored response bodies and
trusts neither the derived files nor the run's own summary.
"""

import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from nima.__main__ import main
from nima.storage.gemi_archive import ImportFailure, verify_run, verify_search_run
from tests.test_collection import Clock
from tests.test_gemi_afm_collection import JSON, RULES, A, B, C, D, E, collect, example
from tests.test_gemi_import_archive import archive_run, edit, manifest_path, snapshot
from tests.test_gemi_search import body, company

EXPECTED = {
    A: "hit_single",
    B: "hit_multiple",
    C: "not_found_at_observation",
    D: "afm_mismatch",
    E: "truncated",
}


def search_run(
    root: Path, handler: object = example, afms: tuple[str, ...] = (A, B, C, D, E)
) -> UUID:
    return UUID(collect(afms, root, handler, clock=Clock()).run_id)


def test_the_five_afm_run_verifies_from_original_bytes_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "raw"
    run = search_run(root)
    # Derived files are not authorities: removing them must not matter.
    (root / "runs" / run.hex / "normalized.jsonl").write_text("not an authority")
    before = snapshot(root)
    monkeypatch.setattr("httpx.Client.send", lambda *a, **k: pytest.fail("Unexpected HTTP"))
    monkeypatch.delenv("NIMA_GEMI_API_KEY", raising=False)
    result = verify_search_run(root, run, RULES)
    assert snapshot(root) == before
    assert result.run_id == run and dict(result.outcomes) == EXPECTED
    assert (result.requested, result.attempts, result.companies) == (5, 5, 6)
    assert result.eligible_hits == 5 and result.unconfirmed_quarantines == 0
    assert dict(result.outcome_counts) == {o: 1 for o in EXPECTED.values()}
    assert len(result.manifest_sha256) == 64


def test_a_retried_answer_verifies_and_both_attempts_are_counted(tmp_path: Path) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, content=b"slow", headers={"retry-after": "0"})
        return example(request)

    root = tmp_path / "raw"
    run = search_run(root, handle, (A,))
    result = verify_search_run(root, run, RULES)
    assert result.attempts == 2 and dict(result.outcomes) == {A: "hit_single"}


def test_a_quarantined_answer_verifies_and_a_header_only_quarantine_is_flagged(
    tmp_path: Path,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.params["afm"] == A:
            return httpx.Response(200, content=b'{"searchMetadata": 1}', headers=JSON)
        return httpx.Response(
            200, content=body([company("2", B)]), headers={"content-type": "text/html"}
        )

    root = tmp_path / "raw"
    run = search_run(root, handle, (A, B))
    result = verify_search_run(root, run, RULES)
    assert dict(result.outcomes) == {A: "quarantined", B: "quarantined"}
    # The first is recomputed from the bytes; the second rests on a response header that is not
    # archived, so it is reported as unconfirmed rather than silently trusted.
    assert result.unconfirmed_quarantines == 1 and result.companies == 0


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        ("outcomes." + A, "hit_multiple", "manifest_invalid"),
        ("outcomes." + C, "hit_single", "manifest_invalid"),
        ("summary.companies", 7, "manifest_invalid"),
        ("summary.found", 3, "manifest_invalid"),
        ("summary.outcome_counts", {"hit_single": 5}, "manifest_invalid"),
        ("summary.attempts", 6, "manifest_invalid"),
        ("summary.status", "failed", "run_incomplete"),
        ("summary.collection_complete", False, "run_incomplete"),
        ("summary.failure", "transport", "run_incomplete"),
        ("summary.run_id", "0" * 32, "run_incomplete"),
        ("connector_version", "gemi-profile-v1", "manifest_version"),
        ("format_version", 2, "manifest_version"),
        ("license", "other", "manifest_version"),
        ("afms", [A, B], "manifest_invalid"),
        ("afms", [B, A, C, D, E], "manifest_invalid"),
        ("inputs", [A], "manifest_invalid"),
        ("attempts.0.afm", B, "manifest_invalid"),
        ("attempts.0.sha256", "../invalid", "manifest_invalid"),
        ("attempts.0.bytes", 0, "archive_integrity"),
        ("attempts.0.status", 500, "manifest_invalid"),
        ("attempts.0.observed_at", "2000-01-01T00:00:00+00:00", "manifest_invalid"),
        ("limits.requests_per_minute", 20, "manifest_invalid"),
        ("attempts", {}, "manifest_invalid"),
        ("summary", [], "manifest_invalid"),
    ],
)
def test_an_inconsistent_manifest_is_rejected_with_a_fixed_reason(
    tmp_path: Path, path: str, value: object, reason: str
) -> None:
    root = tmp_path / "raw"
    run = search_run(root)
    edit(root, run, path, value)
    with pytest.raises(ImportFailure) as caught:
        verify_search_run(root, run, RULES)
    assert caught.value.reason == reason


def test_a_changed_body_a_missing_body_and_a_swapped_answer_are_caught(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run = search_run(root, afms=(A, C))
    bodies = sorted((root / "objects").glob("*/*.body"))
    original = {p: p.read_bytes() for p in bodies}
    first = bodies[0]
    first.write_bytes(original[first] + b" ")
    with pytest.raises(ImportFailure, match="^archive_integrity$"):
        verify_search_run(root, run, RULES)
    first.unlink()
    with pytest.raises(ImportFailure, match="^archive_invalid$"):
        verify_search_run(root, run, RULES)
    first.write_bytes(original[first])
    assert verify_search_run(root, run, RULES).requested == 2
    # An outcome edited in the manifest no longer matches the one recomputed from the bytes.
    manifest = json.loads(manifest_path(root, run).read_text())
    manifest["outcomes"][A] = "not_found_at_observation"
    manifest_path(root, run).write_text(json.dumps(manifest))
    with pytest.raises(ImportFailure, match="^manifest_invalid$"):
        verify_search_run(root, run, RULES)


def test_a_profile_run_and_a_search_run_are_not_interchangeable(tmp_path: Path) -> None:
    profile_root, search_root = tmp_path / "profile", tmp_path / "search"
    profile = archive_run(profile_root)
    search = search_run(search_root)
    with pytest.raises(ImportFailure, match="^manifest_version$"):
        verify_search_run(profile_root, profile, RULES)
    with pytest.raises(ImportFailure):
        verify_run(search_root, search)


@pytest.mark.parametrize("kind", ["marker", "run", "manifest_link", "body_link", "root_link"])
def test_unsafe_or_missing_archive_parts_are_refused(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "raw"
    run = search_run(root)
    target = root
    if kind == "marker":
        (root / ".nima-archive").write_text("x")
    elif kind == "run":
        run = UUID(int=1)
    elif kind in {"manifest_link", "body_link"}:
        file = (
            manifest_path(root, run)
            if kind == "manifest_link"
            else next((root / "objects").glob("*/*.body"))
        )
        copy = tmp_path / "copy"
        file.rename(copy)
        file.symlink_to(copy)
    else:
        link = tmp_path / "linked"
        link.symlink_to(root, target_is_directory=True)
        target = link
    with pytest.raises(ImportFailure) as caught:
        verify_search_run(target, run, RULES)
    assert caught.value.reason in {"archive_invalid"}


def test_the_command_prints_counts_only_and_needs_no_key_database_or_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "raw"
    run = search_run(root)
    monkeypatch.delenv("NIMA_GEMI_API_KEY", raising=False)
    monkeypatch.delenv("NIMA_DATABASE_URL", raising=False)
    monkeypatch.setattr("httpx.Client", lambda **_: pytest.fail("Unexpected HTTP"))
    args = ["gemi", "verify-afm", str(run), "--archive-dir", str(root)]
    assert main(args) == 0
    out = capsys.readouterr().out
    summary = json.loads(out)
    assert summary["status"] == "verified" and summary["requested"] == 5
    assert summary["companies"] == 6 and summary["eligible_hits"] == 5
    assert summary["outcome_counts"]["hit_multiple"] == 1
    assert A not in out and B not in out and "Άλφα" not in out and "outcomes" not in summary
    edit(root, run, "summary.failure", "private-person-and-secret")
    assert main(args) == 1
    failure = capsys.readouterr().out
    assert json.loads(failure)["failure"] == "run_incomplete"
    assert "private-person-and-secret" not in failure
    assert main(["gemi", "verify-afm", str(UUID(int=1)), "--archive-dir", str(tmp_path / "x")]) == 1
    assert json.loads(capsys.readouterr().out)["failure"] == "archive_invalid"
    assert not (tmp_path / "x").exists()


def test_a_quarantine_cannot_rest_on_a_404_answer(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run = search_run(root, afms=(C,))
    # Make every count agree with a quarantine, so only the answer's own status can refuse it.
    for path, value in (
        ("outcomes." + C, "quarantined"),
        ("summary.not_found", 0),
        ("summary.quarantined", 1),
        ("summary.outcome_counts", {"quarantined": 1}),
        ("summary.status", "quarantined"),
        ("summary.normalization_complete", False),
    ):
        edit(root, run, path, value)
    with pytest.raises(ImportFailure, match="^manifest_invalid$"):
        verify_search_run(root, run, RULES)


def test_a_terminal_status_cannot_be_followed_by_a_later_attempt(tmp_path: Path) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, content=b"slow", headers={"retry-after": "0"})
        return example(request)

    root = tmp_path / "raw"
    run = search_run(root, handle, (A,))
    edit(root, run, "attempts.0.status", 403)  # the collector stops at 403; it never retries
    with pytest.raises(ImportFailure, match="^manifest_invalid$"):
        verify_search_run(root, run, RULES)


def test_a_receipt_beyond_the_expected_attempts_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    run = search_run(root, afms=(A,))
    manifest = json.loads(manifest_path(root, run).read_text())
    manifest["attempts"].append(manifest["attempts"][-1])
    manifest_path(root, run).write_text(json.dumps(manifest))
    with pytest.raises(ImportFailure, match="^manifest_invalid$"):
        verify_search_run(root, run, RULES)


def test_a_transport_failure_before_the_answer_is_accounted_for(tmp_path: Path) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("private transport details")
        return example(request)

    root = tmp_path / "raw"
    run = search_run(root, handle, (A,))
    result = verify_search_run(root, run, RULES)
    assert result.attempts == 2 and dict(result.outcomes) == {A: "hit_single"}


def test_attempts_that_never_reach_a_final_answer_are_not_a_complete_run(tmp_path: Path) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, content=b"slow", headers={"retry-after": "0"})
        return example(request)

    root = tmp_path / "raw"
    run = search_run(root, handle, (A,))
    edit(root, run, "limits.max_attempts", 2)
    edit(root, run, "attempts.1.status", 429)
    with pytest.raises(ImportFailure, match="^run_incomplete$"):
        verify_search_run(root, run, RULES)


@pytest.mark.parametrize(
    ("path", "value"),
    [("summary.normalization_complete", False), ("summary.status", "quarantined")],
)
def test_the_normalization_flag_must_agree_with_the_run_status(
    tmp_path: Path, path: str, value: object
) -> None:
    root = tmp_path / "raw"
    run = search_run(root, afms=(A,))
    edit(root, run, path, value)  # a complete run has the flag set; a quarantined one does not
    with pytest.raises(ImportFailure, match="^run_incomplete$"):
        verify_search_run(root, run, RULES)
