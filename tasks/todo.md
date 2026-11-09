# Tasks

## Bounded KIMDIS evidence collector

- [x] Validate and normalize a complete page in one JSON decode.
  - Depends on: merged PR #5.
  - Acceptance: strict pagination; valid rows survive quarantined neighbors; exact evidence pointers.
  - Verify: `uv run --frozen pytest tests/test_kimdis_pages.py tests/test_kimdis_contracts.py`.
- [x] Preserve bodies and run artifacts in a private content-addressed archive.
  - Depends on: source contracts.
  - Acceptance: atomic writes; immutable reused bodies; corrupt/unrelated paths rejected.
  - Verify: `uv run --frozen pytest tests/test_archive.py`.
- [x] Collect bounded pages with visible retries and reconciliation.
  - Depends on: page contracts and archive.
  - Acceptance: bounded requests, rate/backoff, archived completed bodies, no false completeness.
  - Verify: `uv run --frozen pytest tests/test_collection.py tests/test_collection_limits.py`.
- [x] Expose CLI, verify a bounded live collection, and open dependent draft PRs.
  - Depends on: collector.
  - Acceptance: actionable JSON summary, honest exit status, no data in Git, green local/hosted checks.
  - Verify: CLI tests, `make check`, `make audit`, opt-in live probe, private PR metadata.
  - Evidence: 134 tests, 97.94% coverage; 1,118 live records over 23 pages;
    PRs #7–#9 and integration #10 merged by the user; #10 brought the complete
    collector into main. New PRs target main directly; no automatic merge/deploy.

## PostgreSQL page persistence (completed)

- [x] Extend and review the accepted persistence contract in SPEC-source-ingestion.md.
  - Acceptance: source versions and observations are distinct; transaction, replay,
    archive, checkpoint, and migration invariants are explicit.
- [x] Persist one archived page in a real PostgreSQL transaction.
  - Acceptance: immutable content versions, A→B→A observations, quarantine and
    pending outbox events; checkpoint commits atomically; replay is idempotent.
  - Verify: real PostgreSQL tests, SQL constraints, exact source hashes/money.
- [x] Verify killed-worker rollback and replay at page commit boundaries.
  - Acceptance: killed pre-commit leaves no page effects; killed post-commit
    replays without duplicate observations or outbox work. HTTP resume stays hidden.
  - Verify: subprocess SIGKILL tests with independent database connections.
- [x] Complete checks and publish one unmerged PR directly to main.
  - Verify: make check, make audit, hosted quality, private visibility/attribution.
  - Evidence: PR #11 targets main; 151 tests, 98.23% coverage, real PostgreSQL
    SIGKILL/replay tests; hosted push run 42685054456 passed at ea14a23.
    Final-head checks are recorded in the PR before marking it ready.

## Durable HTTP collection and inspection (completed)

- [x] Add checksum-verified migration 0002 and prove populated v1 upgrade.
- [x] Journal HTTP attempts and atomically persist accepted pages through the collector.
- [x] Expose opt-in database ingestion, explicit migration, and read-only run inspection.
- [x] Verify real process interruption, SQL failures, redaction and coverage reconstruction.
- [x] Complete checks/audit and open one unmerged main-targeted PR.
  - Evidence: PR #12 targets main; 172 tests, 97.42% coverage; real SIGKILL
    inspection tests and offline 1,118-record replay. Hosted push run 42690122843
    passed at 7a861f0; final-head check links are recorded in the PR.

## Safe database-run resume (current)

- [x] Restore immutable run settings and verify archived page bodies.
- [x] Exclude active workers and fence stale writers during takeover.
- [x] Replay pending responses, revalidate source prefixes, and continue without duplicates.
- [x] Prove multi-page worker kill/restart and drift/corruption failure behavior.
- [x] Expose resume CLI, complete checks/audit and publish an unmerged main-targeted PR.
  - Evidence: PR #13 targets main; 187 tests, 96.64% local coverage, real
    SIGKILL/restart and lease-loss tests, offline 1,118-record recovery. Push run
    42697311110 passed at e42b2f6; final-head hosted links are recorded in the PR.

## Following ingestion slices

- [x] Add safe HTTP run resume and restart reconciliation after durable inspection.
  - Depends on: reviewed page persistence.
  - Verify: full multi-page worker termination/restart, source-page drift handling,
    durable attempt history, and final completeness reconstruction.
- [ ] Add reviewed supplier/buyer projections and an outbox consumer.
  - Acceptance: preserve joint participation without duplicating contract spend;
    consumer replay is idempotent. No automatic graph inference is implied.

## Engineering foundation

- [x] Install all 25 skills with shared references and MIT license.
  - Acceptance: native project-local discovery layout; pinned upstream revision.
  - Verify: `make skills-check` and inspection of `.agents/skills.lock.json`.
- [x] Add locked tooling and integrity-check behavioral tests.
  - Acceptance: clean snapshot passes; drift, missing files, and path escapes fail.
  - Verify: red/green test evidence and `make test`.
- [x] Complete local CI-equivalent checks and bootstrap self-review.
  - Acceptance: lint, strict types, tests, build, source security, and advisory audit pass.
  - Verify: `make check`, `make audit`, and `docs/verification/bootstrap.md`.
- [x] Verify private visibility of the user-created `StamKavid/nima-ai` and push.
  - Acceptance: remote privacy confirmed; intended branch and history pushed.
  - Verify: authenticated repository metadata and remote commit SHA.
- [x] Run hosted CI on the bootstrap.
  - Acceptance: quality job succeeds after correcting the spec's code-example formatting.
  - Verify: Actions run `42516872940` passed with actor `StamKavid`.
- [ ] Configure main-branch controls through an account with administration access.
  - Acceptance: required `quality` check, PR/review controls, and force-push restrictions verified.
  - Verify: repository rules metadata; integration's attempt returned 403.
- [x] Save the first application spec for user review.
  - Acceptance: objective, commands, structure, testing, boundaries, and success criteria.
  - Verify: spec review; implementation planning follows approval.

## Later capabilities

Source ingestion → identity resolution → temporal graph → risk analytics →
investigator workspace. These are roadmap items, not implementation tasks.

## Current Nima increment

- [x] Rename package metadata/imports and document the accepted product mission.
  - Acceptance: package builds as `nima-ai`; import namespace is `nima`.
  - Verify: locked dependency sync, tests, and build.
- [x] Normalize a KIMDIS contract with evidence and exact monetary values.
  - Acceptance: behavior in `tasks/plan.md` is covered; unknowns stay unknown.
  - Verify: failing tests before implementation, then `make check`.
- [x] Document graph, model, detector, and investigation milestones.
  - Acceptance: each capability names required data, purpose, and evaluation gate.
  - Verify: source review and five-axis change review.
- [x] Push the feature branch and open a draft PR after confirming repository privacy.
  - Acceptance: no public publication; PR has validation and limitations.
  - Verify: draft PR #5; hosted push and PR checks passed for `c64a5e2`.
- [x] Verify corrected historical and future attribution resolves to `StamKavid`.
  - Acceptance: approved metadata-only rewrite preserves every bootstrap file tree.
  - Verify: GitHub author/committer metadata and guarded remote update.
