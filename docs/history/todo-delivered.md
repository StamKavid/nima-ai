# Delivered task history (archived from tasks/todo.md, 2026-11-20)

Sections with no open items, moved unchanged. Open items live in `tasks/todo.md`.

## V1-03 O3f — evidence TRUNCATE guards

- [x] Owner approved 2026-11-19; spec, plan and tasks recorded on this branch.
- [x] O3f-1: failing tests first (guard for all 15 tables; upgrade from 12 with data;
  history/checksums; audit limitation list empty; drop/disable detected).
- [x] O3f-2: migration 0013 and migration-list update (pinned counts 12->13 in five
  tests); contract flags, runbook and status documents. 66 guard tests; emptying the
  migration fails 47 of them and restoring it passes. Finding corrected: twelve tables
  were open to a CASCADE wipe; three were already blocked indirectly.
- [x] O3f-3 local: skills, format, lint, strict mypy, build, Bandit, Gitleaks and pip-audit
  clean; contracts 3/3 unchanged vs main `af41981`; 146 guard/access tests pass from the
  unpacked wheel (0013.sql identical). Full suite on PG16 with a scratch-only version
  shim: 2835 passed, 59 failed, and the failing set is identical to the baseline
  (subprocess tests that hit the PostgreSQL 17 guard). PostgreSQL 17 proof is hosted CI.
- [x] O3f-3 delivery: owner merged #151 at `d3d80c7`; exact `8da0c32` verified on main. Hosted
  run 44588545458 passed all three jobs on that head. The duplicate push run's `quality`
  timed out at 15 minutes (runner variance; also seen on #148) and was re-run once.
  Applying 0013 to the private pilot is a separate owner action; the audit refuses an
  unmigrated database (tested).
- [x] O3g CI trigger scope and quality time budget: owner merged #153 at `e2ab1a5`; exact
  `a73aadf` verified on main. Its own hosted run 44600852305 was the only run on that head
  (no duplicate push run) and passed all three jobs; `quality` took 15 min 23 s, which would
  have exceeded the old 15-minute limit. Feature branches without a PR now need
  `workflow_dispatch`. Headroom is about 4.6 minutes; revisit parallel tests if a run passes
  about 18 minutes.

## V1-03 O3 — runtime-role and evidence-protection audit

- [x] Spec approved 2026-11-19: profiles, print-only grant script, restore check.
- [x] O3a: typed access contract (seven documented profiles), 33-table classification,
  fixed reasons and pure assessment. 46 tests, 100% line/branch on both modules; ruff,
  strict mypy and Bandit clean. Guard mutations (trigger check, TRUNCATE excess)
  fail named regressions and are restored. Finding: 15 older evidence tables lack
  a TRUNCATE trigger; disclosed as a limitation, a fix would be a migration.
- [x] O3b: pure print-only grant renderer from the same contract. 76 access tests;
  printed grants parse back to exactly each ceiling and pass the audit; unsafe/
  reserved role names refused. Widened-grant mutation failed 16 tests; restored.
- [x] O3c: bounded catalogue adapter and 32 real-role/real-catalogue tests: printed
  grants pass for all seven profiles; each drift/privilege/role reason; bounds;
  read-only transaction and timeouts; mid-audit grant seen; no state change.
  Locally verified on PostgreSQL 16 with a scratch-only version shim (not committed);
  PostgreSQL 17 proof is hosted CI only. Disabled-trigger mutation fails; restored.
- [x] O3d (code/docs): CLI for `access-audit` and print-only `access-grants`, private
  no-clobber report, fixed errors/redaction, operator runbook and restore entry.
  133 access tests, 100% line/branch on all five new modules.
- [x] O3d local gates (exact tree): skills, format, lint, strict mypy, build, Bandit,
  Gitleaks, pip-audit clean; committed contracts 3/3 unchanged vs main `d09ec20`;
  133 access tests pass from the unpacked built wheel. Full suite on PG16 with a
  scratch-only version shim: 2749 passed, 59 failed, all in subprocess/crash-style
  tests that hit the PostgreSQL 17 guard; a 54-test sample on clean main fails the
  same 8, so none is caused by this change. PostgreSQL 17 proof is hosted CI only.
- [x] O3d (delivery): owner merged #149 at `fa4d772`; exact reviewed `90d395a` is
  verified on main. Hosted jobs on that head (quality, orchestration-compose,
  source-worker-egress; runs 44574859669 and 44574968743) all passed on
  PostgreSQL 17, so the local PG16-shim caveat is closed. No live rollout.
- [x] O3e spec approved 2026-11-19 (per-duty profiles; sequences only if proven
  necessary; TRUNCATE migration as a separate increment).
- [x] O3e-1 `projector`: owner merged #150 at `af41981`; exact `e91d1e6` verified on main.
  15 tests; two over-grant mutations fail and are restored. Hosted run 44581097628 passed
  all three jobs on that head (merged while two jobs were running; they finished green).
- [x] O3e-2 `collector` (local): 33 tests prove the real `collect` and `resume` complete under
  exactly the printed grants in three offline scenarios (clean, quarantined record, resume of
  an interrupted run) and that removing any privilege breaks at least one; no sequence needed.
  Two over-grants (SELECT on outbox, UPDATE of `query`) fail their own necessity case; restored.
- [x] O3e-2 delivery: owner merged #152 at `7dfc7b1`; exact `580508e` verified on main. Hosted
  runs 44593722293 and 44593665861 passed all three jobs on that head (quality 12.3 and 12.6
  minutes). Further duties are paused until they go live.
- [x] TRUNCATE guards: delivered as O3f (#151).
- Open finding for owner: 15 older evidence tables lack a TRUNCATE trigger; a fix
  would be a reviewed migration.

## V1-03 O2 — selected refresh-policy health

- [x] Verify #147 reviewed tree on main `6f706f1`; freeze bounded O2 contract.
- [x] O2a: typed pure rules; age/clock/coverage/blocked-child budget regressions.
- [x] O2b: one bounded SQL snapshot; real restricted role, frozen interleaving,
  actual read-only/timeouts, missing/corrupt/oversized evidence refusal.
- [x] O2c: actual CLI/private artifact/fixed errors, operator procedure, merged-
  baseline project/chapter assessment, restored mutation and installed wheel.
- [x] O2d: owner merged #148 at `d09ec20`; exact `9d866f0` verified on main. Local
  gates 2675 tests/93.33%, clean audit, 47 installed-wheel cases and hosted run
  44549710775 (all three jobs) passed. No live enablement. Score reassessment pending.

## V1-03 O1 — bounded workflow diagnostics

- [x] Verify #146 reviewed head reaches main `476f9be`; freeze O1 contract.
- [x] O1a: default-off/strict configuration, bounded event records and failure
  privacy; prove failures and sink-error precedence with focused tests.
- [x] O1b: instrument existing four stages, preserve results/budgets and prove
  real SQL/fixture retry/failure and process-termination behavior.
- [x] O1c: #147 owner-merged at `6f706f1`, exact `f230ea0` verified. Full local
  gates: 2628 tests/93.34%; audit, 33 installed-wheel tests, restored redaction
  guard and both hosted runs 44540966944/44540876746 passed. No live enablement.
- Later V1-03: non-owner runtime proof, full policy/child health, protected
  operator configuration, approved off-host restore and effective branch rules.

## V1-02 R3 — final workflow-recovery code checkpoint

- [x] Verify #145 exact `0bbdbf6` reaches main `3626314`; freeze explicit successor
  authority, same-scope/paused creation and finite checkpoint acceptance.
- [x] R3b: 0012/atomic API, immutable stamped approval, original-schema/data
  preservation, fresh/same-scope target and idempotent/collision checks.
- [x] R3c: actual CLI and bounded snapshot lineage; expired-child refusal followed
  by separately authorized fresh observations with old evidence/budgets unchanged.
- [x] R3d local: process death, concurrent/default-isolation/narrow-role checks and
  authorization/scope guard mutations fail and are restored.
- Installed-wheel, full gates/audit and final-head hosted proof are required
  before announcing checkpoint complete; record exact results with delivery.
- [x] Checkpoint complete at #146 review-ready delivery; owner merged `476f9be`,
  exact `ded3478` verified. Full local (2595 tests, 93.27%), audit, 32 installed-
  wheel tests, restored guard mutations and hosted run 44535222081 passed.
  No live setup, collection or schedule activation.

## V1-02 R2 — permanent policy retirement

- [x] Verify #144 reviewed tree reaches main `82ded43`; freeze retirement contract.
- [x] R2b: additive schema/API/shared lock, immutable stamped decision and old-data
  upgrade, roles, atomicity and concurrent control proof.
- [x] R2c: SQL/Python allocation/dispatch fences, snapshot reporting and SQL-only
  CLI; preserve normal R1 recovery and distinguish engine acknowledgement.
- [x] R2d: SIGKILL before/after commit; SQL fence and repeatable-read quota guard
  mutations fail regressions and are restored.
- Installed wheel, full gates/audit and exact-head hosted evidence are required
  before handoff; record observations with the delivery PR.
- [x] Owner merged #145 at `3626314`; exact `0bbdbf6` verified. Full local/wheel/
  mutation and both exact-head CI runs are recorded there. No private deployment.
- [x] Successor linking/explicit new-budget authorization delivered separately
  in #146. Retirement itself never completes windows or creates a policy/request.

## V1-02 R1 — bounded same-request refresh recovery

- [x] Verify #143 exact reviewed tree on main `435326a`; inspect existing intent
  compatibility and freeze recovery eligibility/budgets/acknowledgement contract.
- [x] R1b: pure budget policy, shared source session and atomic capped reservation.
- [x] R1c: enabled compatible policy/open-child control and actual CLI route.
- [x] R1d: SQL locks/concurrency/unchanged history, unknown RPC, process death,
  actual local runner and evidence-based completion; budget mutation restored.
- [x] Installed-wheel, complete local gates/audit and final-head hosted evidence
  recorded in #144; owner merged exact `5e90a32` at main `82ded43`.
- [x] Owner review via #144; no live recovery or source/schedule activation.
- [x] Current-profile exhausted-child/policy decisions delivered in #145/#146;
  original budgets and terminal history remain intact. Future source formats and
  late-correction sweeps retain their separate acceptance.

## V1-01 VH1 — selected-artifact validation health

- [x] Verify #142 and reviewed head on main `ef657aa`; freeze bounded health scope.
- [x] VH1b: typed records/shared decoding and complete bounded read-only SQL cohort.
- [x] VH1c: deterministic current-policy, latest-start, tie, age and clock rules.
- [x] VH1d: actual CLI, fixed events/errors and operator guidance.
- [x] VH1e SQL: actual restricted roles, interleaved-commit snapshot, old corruption,
  count/byte bounds and transaction-level write refusal. Latest-failure guard
  mutation fails its regression and is restored.
- Installed wheel, full local gates/audit and exact-head hosted proof are required
  before handoff; record exact observations with the delivery PR.
- [x] Owner merged #143; exact `e29e1cd` reaches main `435326a`. No live journal
  setup, source acquisition or activation follows from that code merge.

## V1-01 — first durable validation boundary

- [x] H1: verify #139/#140 on main `73f8aa4`, identity and bounded contract.
- [x] H2: pure identities/states, additive 0010 and real limited-role journal tests.
- [x] H3: shared preparation, preserving existing publication bytes/errors.
- [x] H4: post-publication validation and read-only inspection CLI; actual SQL,
  private files, failure/cached/fresh semantics and no source mutation.
- [x] H5 process-kill/concurrency: SIGKILL/SIGINT before/after outcome commit;
  pending resumes, committed results reuse, concurrent same-ID writes refuse.
- [x] Byte-equivalence guard mutation fails its actual regression and is restored.
- Packaged resource check, full gates/audit and final-head hosted evidence are
  required before review; record exact observed results with both PRs.
- Split delivery: provider `feature/validation-journal` to main; consumer
  `feature/readout-validation-history` initially targets the provider. Retarget
  consumer to main after verified provider merge before offering main delivery.
- [x] Owner merged #141/#142; exact `2c9cbf6` reaches main `ef657aa`.
- Other dataset boundaries/health aggregation and live journal
  deployment remain later. No source request, pilot migration or schedule.

## Checkpoint C10 — historical contract comparison

- [x] Verify #138 reaches main at `9d29845`; freeze committed catalogue and CI rules.
- [x] C10b: Git tree/blob reader, strict bounded descriptor inputs, ID catalogue
  and compatibility policy; real Git history and refusal tests.
- [x] C10c: CLI and provider-context selection; actual subprocess/CI-mode tests
  prove dirty files cannot bypass comparison and diagnostics stay fixed.
- [x] C10d: quality checkout history and baseline step; just recipe and runbook;
  preserve all existing jobs, permissions, pins, checks and thresholds.
- [x] Removal-policy mutation: actual history regression detects the lost fixed
  removal diagnostic; original source is restored. Real Git/CLI cases also prove
  bootstrap, rename, SemVer, strict JSON, limits and missing-history refusal.
- C10e: real main comparison, full local gates/audit, final-head hosted evidence
  and a reviewable PR are required before handoff; record results in the PR.
- [x] Owner merged #139 at `73f8aa4`; #140 roadmap reaches the same main.
- Durable result history, source freshness and source activation
  remain separate work; this gate does not establish dataset correctness.

## Checkpoint C9 — KIMDIS input and normalized contracts

- [x] Verify #137 and exact contract changes reach main at `9cd4c8a`; freeze scope.
- [x] C9b: neutral schema module; C8 behavior/public APIs and assertions preserved.
- [x] C9c: explicit opaque-array and present-nullable flags, unsupported/repeated
  custom flags refused, with conservative compatibility checks.
- [x] C9d: two draft ODCS documents, source-owned policy/version and cached
  validators; exact money/unknowns/evidence/metadata binding tests.
- [x] C9e: actual normalizer gates and unchanged storage version alias; source
  quarantine versus fatal producer defect; real SQL page atomicity/raw retention.
- [x] C9f mutation: disabling source/producer hooks fails actual regressions;
  source bytes are restored. Invalid compiled constraints fail before data checks.
- Installed-wheel/pilot byte preservation, full local gates/audit and final-head
  hosted evidence are required and recorded with delivery PR before handoff.
- [x] Record the measured CI-budget exception after two PR cancellations at ten
  minutes; extend only the quality-job bound to fifteen, with all gates retained.
- [x] Owner merged #138 into main at `9d29845`; no automatic deployment.
- Source activation, historical PR comparison
  and durable check history remain separate work.

## Checkpoint C8 — first ODCS analytics contract

- [x] Owner continues the bounded contract proposal; inspect official ODCS 3.2.0.
- [x] Freeze spec and sequential slices; preserve all prior pending work.
- [x] C8b: pin official schema/license and explicit package provenance; reviewed
  output contract, offline shape/semantic validation and compatibility policy.
- [x] C8c: actual publication gate; real-SQL preservation/byte-replay and injected
  failure tests with fixed private-safe errors and no new report on failure.
- [x] C8d mutation: semantic-binding and major-version guard removals fail their
  actual regressions and are restored. JSON boolean/numeric enum regression fixed.
- Packaged-wheel/pilot byte-compatibility proof, final full local gates/audit and
  exact-head hosted checks are required and recorded with the PR before handoff.
- [x] Owner merged #137 into main at `9cd4c8a`; no automatic deployment.
- Normalized/input contracts, automatic PR
  baseline checks, check-history storage and scheduled monitoring remain later.

## Checkpoint C6 — selected-run DataOps health

- [x] Verify #135 reaches main; freeze explicit selected-run/threshold contract.
- [x] Pure attention policy with exact boundary/unknown/future/empty cases.
- [x] Repeatable-read READ ONLY SQL aggregate sample, current projection backlog,
  optional linked workflow, least privilege and unchanged-source tests.
- [x] No-follow filesystem capacity sample and private canonical publication.
- [x] Actual dataops health CLI, private-safe structured events and exit states.
- Age/read-only mutations and private clone proof pass; packaged SQL and full
  local gates/audit are required and recorded with the delivery PR before handoff.
- Exact-head hosted results are recorded with the delivery PR before handoff.
- [x] Owner merged #136 at `772c321`; private health activation independently
  authorized and verified. Selected attention is not a global-health verdict.

## Checkpoint C3 — SQL metadata serving

Continue after owner-merged #129 (`6051d41`); prior exact-head CI passes in runs
44267217179 and 44267160859. Retain all pending human/model/dictionary work.

- [x] C3a: freeze SQL snapshot contract, source boundaries and review checkpoint.
- [x] C3b: public canonical metadata preparation, prior bytes unchanged.
- [x] C3c: additive 0009/immutable snapshot/source FKs/occurrence view and upgrade tests.
- [x] C3d: selected-hash promotion and SQL/Python-equivalent read queries, restricted
  roles, concurrency and real commit-boundary crash checks.
- [x] C3e: actual promote/query CLI with private fixed summaries.
- [x] C3f local: official taxonomy assessment, TRUNCATE/selected-hash mutations,
  disposable proof and packaged-wheel SQL smoke. Both guards are restored.
  Final combined `just check`: 2,213 passed/93.05%; `just audit`: clean.
- Exact-head hosted gates are recorded with both delivery PRs before C3 handoff.
  Private proof stays outside Git; no implicit live migration or model activation.
- [x] Owner review at C3 through merged #130/#131; C4 dictionary installation and human validation remain open.


## Checkpoint C2 — structured metadata

Continue after owner-merged #128 (`bd7fec4`); prior exact-head CI passes in runs
44258789845 and 44258739500. Retain human/metadata/model tasks below.

- [x] C2a: freeze bounded extraction/filtering contract and sequential slices.
- [x] C2b: pure reported dimensions/statuses/source pointers and shape tests.
- [x] C2c: public verified capture boundary; original replay bytes unchanged.
- [x] C2d: private KIMDIS/GEMI metadata exports, CLI filters and real boundary tests.
- [x] C2e local: 46 new cases; invalid-code eligibility mutation fails and is
  restored. Full `just check`: 2,182 passed/93.13%; `just audit`: clean.
  Hosted exact-head results are recorded with the delivery PR before handoff.
- [x] Owner review at C2 through merged #129 (`6051d41`). SQL metadata indexes, taxonomy certification, identity
  joins, model adoption and human task validation remain separate.


## Checkpoint C1 — auto-build authorized

Owner continued after merged #127 (`ef2b438`); corrected head `f2eb17b` passes all
three jobs in PR run 44168550280 and push run 44168539451. See the C1 source
contract and [plan](../../tasks/plan.md); retain all pending human/model/metadata work below.

- [x] C1a: freeze checkpoint and bounds; continue without routine approvals.
- [x] C1b: verify private native backup/restore before applying reviewed migration 8
  to the pilot; scope grants, promote prior selected replays and verify unchanged
  source evidence/counters/old grants/readout and HTTP guards. Proof outside Git.
- [x] C1c: pure v1 intent decoder and saved request identity/limits, additive
  compatibility status, manifest lineage and execution/dispatch boundaries. Four files.
- [x] C1d: refresh inspection/pause across processing-pin changes; gate enable,
  tick/cycle/children/send before effects. Four files, same regression module.
- [x] C1e local verification: meaningful source-lease pin mutation is rejected and
  restored; 43 new/61 focused cases pass. Full `just check`: 2,136 passed/93.07%;
  `just audit`: clean. Private maintenance/offline recheck passes. Only the reviewed
  journal/derived/grant additions occur; no source request or schedule activation.
- Hosted exact-head results are recorded with the delivery PR before C1 handoff.
- [x] Owner review at C1 through merged #128 (`bd7fec4`). No new source capture/schedule/model or human-certification
  claim; metadata and explicit replacement remain later bounded work.

## CI correction: PR #127

- [x] Identify run 44163644708 failure: Compose smoke expects migration count 7;
  quality and source-worker-egress jobs pass. Migration 0008 itself succeeds.
- [x] Reproduce the exact embedded database failure, replace the stale count with
  public schema validation and preserve every other smoke/quality control. Three
  files: CI workflow, plan and this task record; no application/live-pilot change.
- Evidence: real PostgreSQL 17 migration 8 reproduces the old assertion failure;
  corrected block passes and rejects an incorrect checksum at unchanged count.
  Image build succeeds; local Compose startup hits Docker disk exhaustion while
  pulling PostgreSQL. Owned stack/image and disposable SQL database are removed.
  Full local gates and corrected hosted checks are recorded with the PR.
- [x] Corrected hosted Docker check passes; local database checksum rejection,
  owned cleanup, 2,093 tests/93.10% and clean audit pass. All three jobs pass in
  PR run 44168550280 and push run 44168539451 on `f2eb17b`.
- [x] Owner merged #127 at `ef2b438`; continue through C1 above.

## Current extension: PostgreSQL role preservation

Owner continued after merged #124 (`cae6fe2`); all three exact-head jobs pass in
run 44127404558. Retain the prior drill and unfinished PV10/model work.

- [x] RPOL1: freeze the startup-role/session-timeout contract and bounded private
  ownership repair in the [plan](../../tasks/plan.md). No role API or migration addition.
- [x] RPOL2: reproduce actual NOLOGIN migration ownership, fix the connector and
  exercise DSN/environment/service settings, mandatory timeouts, unauthorized
  roles, legacy behaviour and real-connection cleanup on setup error/interruption.
- Acceptance: configured role owns the new schema and project objects; no fallback
  or returned connection without fixed limits; no connection leak on setup failure.
- Verify: `uv run --frozen pytest tests/test_connection.py tests/test_postgres.py`;
  old-keyword mutation fails; full `just check` and `just audit` plus hosted checks.
- [x] RPOL3: with the existing verified native backup, repair only expected private
  pilot project-object owners in one transaction. Preserve all table data/counters,
  daily-role capabilities and original bytes; validate role-bound replay, archive
  checks and identical private readout. No cluster-wide reassignment/source call.
- Files: `src/nima/storage/connection.py`, `tests/test_connection.py`,
  `docs/operations/backup-restore.md`, `tasks/plan.md`, this file (five files).
- Evidence: eleven new real-connection cases plus five migration regressions pass.
  DSN/environment/service role settings and fixed limits survive; invalid/denied
  roles fail; actual connections close on first/second setup error/interruption.
  Restoring the old options keyword makes the ownership regression fail. The
  private pilot's expected `nima` object owners are now repaired in one transaction
  under the advisory lock; all 26 table contents/counters, logical schema, original
  files and daily-role capabilities remain unchanged. Role-bound migration replay,
  archive checks and identical reader output pass. Private evidence stays outside
  Git; no source HTTP call. Full local gates pass 1,995 tests/93.04% and a clean
  advisory audit. Hosted checks accompany the PR.
- [x] Owner merged #125 at `d98a971`; all three exact-head jobs passed in run
  44146760312. Continue the replay increment above.

## Completed: bounded investigation graph — technical delivery

Scope #87 and plan #90 are owner-approved. G1–G7 are owner-merged through #97 at
`686875d`, completing checkpoints A–D. G6 #96 and G7 #97 both pass their three
exact-head hosted jobs. The next [evidence-recovery scope](../graph/company-evidence-pilot.md)
is proposed only; pilot implementation tasks await separate scope/plan approval.
Preserve the approved [graph contract](graph/investigation-pilot.md), all
earlier incomplete work, existing constraints and historical records below.
Execute sequentially without delegation.

- [x] Record contract approval and revise candidate research across technical,
  operating/support and licensing factors; no graph/database installed or benchmark run.
- [x] Draft the bounded graph implementation plan and verifiable slices below.
- [x] Owner review/approval of this implementation plan before G1 (#90).

Every code slice runs its focused tests, just check, just audit and all three
exact-head hosted jobs. No test is skipped or gate weakened for local prerequisites.
G1–G5's measured passing commands/results are in the
[graph runbook](../verification/investigation-graph.md). G6/G7 require their own
normal checks and owner checkpoint, now complete.

### G1: Reuse a connection-owned reviewed snapshot read

- [x] Extract the guarded reader without adding graph behavior (#91).
- Acceptance: existing wrapper preserves validation/error/byte behavior; a caller-
  owned read requires active RR/read-only/UTC and does not commit/close the caller;
  shared identity evidence/history/fold logic remains authoritative.
- Verify: uv run --frozen pytest tests/test_identity_review_snapshot.py tests/test_identity_review_export.py tests/test_identity_review_cli.py.
- Files: src/nima/identity/review_snapshot.py, tests/test_identity_review_snapshot.py;
  tests/test_identity_review_export.py only if a wrapper regression needs it.
- Scope: 2–3 files. Dependency: approved plan.

### G2: Validate complete graph facts in one SQL snapshot

- [x] Add the complete bounded graph source-read library (#92).
- Acceptance: one owned snapshot revalidates selected review state and exact full
  contract projection/digest; additional normalized/projection bytes reserve the
  same 8 MiB before labels; typed results omit unselected source labels, writes,
  external requests and implicit schema changes, preserving all existing limits.
- Verify: uv run --frozen pytest tests/test_graph_snapshot.py tests/test_identity_review_snapshot.py tests/test_identity_review_evidence.py.
- Files: src/nima/graph/__init__.py, src/nima/graph/snapshot.py,
  src/nima/identity/review_snapshot.py, tests/test_graph_snapshot.py,
  tests/test_identity_review_snapshot.py.
- Scope: 5 files. Dependency: G1.

### Checkpoint A: Complete consistent inputs

- [x] Shared-read regressions, real count/byte/corruption checks and normal hosted
  gates pass; owner review/merge before graph construction.

### G3: Build deterministic graph and focused party views

- [x] Deliver pure construction from the complete typed snapshot (#93).
- Acceptance: exact approved kinds/keys/metadata and sorted collision-free graph;
  active-only reviewed links, all unresolved/history members and focus outcomes;
  exact money/date/evidence semantics, 600/500 limits and no out-of-scope labels.
- Verify: uv run --frozen pytest tests/test_graph_build.py tests/test_graph_focus.py tests/test_registry_report.py.
- Files: src/nima/graph/build.py, tests/test_graph_build.py, tests/test_graph_focus.py.
- Scope: 3 files. Dependency: checkpoint A.

### G4: Publish a complete private graph artifact

- [x] Connect SQL read, pure build and existing canonical publisher (#94).
- Acceptance: SQL closes before encoding/publication; exact 32 MiB output, canonical
  hashes/reuse and old artifact immutability; independent concurrent-revoke tests
  prove one coherent snapshot and full source/review row snapshots prove no writes.
- Verify: uv run --frozen pytest tests/test_graph_export.py tests/test_graph_snapshot_races.py tests/test_graph_snapshot.py.
- Files: src/nima/graph/export.py, tests/test_graph_export.py,
  tests/test_graph_snapshot_races.py, tests/test_graph_support.py.
- Scope: 4 files. Dependency: G2–G3.
- The test support module reuses the existing 23-relation source snapshot and adds
  explicit snapshots of the three review tables; it does not weaken the old helper.

### Checkpoint B: Complete graph export library

- [x] Deterministic exact graph/focus results, actual SQL consistency/read-only
  evidence and normal hosted gates pass; owner review/merge before CLI exposure.

### G5: Expose the CLI and verify physical retry

- [x] Add graph snapshot and exercise actual publication interruption/retry (#95).
- Acceptance: strict private input/configuration and fixed 0/1/2/130 behavior,
  source-value-free errors and unchanged old routes; real before/after-publication
  SIGKILL then normal-CLI retry preserves one artifact/closed SQL/unchanged rows;
  a material active-link or dedup mutation fails before exact restoration.
- Verify: uv run --frozen pytest tests/test_graph_cli.py tests/test_graph_export_crash.py tests/test_identity_review_cli.py tests/test_cli.py.
- Files: src/nima/__main__.py, src/nima/graph/commands.py, tests/test_graph_cli.py,
  tests/test_graph_export_crash.py. Reuse existing graph/support/publisher behavior.
- Scope: 4 files. Dependency: checkpoint B.

### Checkpoint C: Private operator graph workflow

- [x] Actual command/parser/physical recovery/mutation and all hosted gates pass;
  owner review/merge before recording the measured runbook.

### G6: Document measured graph operation

- [x] Record implemented commands, setup, exact results and empirical limits (#96, owner-merged).
- Acceptance: actual help/examples/private artifacts, resource/error/recovery and
  identity/time/value/coverage limits match code; measured CI/source-state evidence
  is distinct from unrun real-user, database-adapter and production evaluations.
- Verify: actual CLI help, local links, five-axis/prose review and normal gates.
- Files: docs/verification/investigation-graph.md, README.md, CAPABILITIES.md,
  docs/architecture.md, docs/graph/investigation-pilot.md (delivery status only).
- Scope: 5 files. Dependency: checkpoint C.

### G7: Reconcile delivery and the next product gate

- [x] Record actual merges/checkpoints, capability evidence and remaining evaluation (#97, owner-merged).
- Acceptance: all earlier incomplete tasks and fixed weights remain; any delivery
  credit cites working/evaluated capability, not documentation/PR/test counts;
  real-cohort recovery, investigator tasks and separately scoped database tests remain explicit.
- Verify: cross-check exact heads, CI, attribution and owner merges only.
- Files: tasks/plan.md, tasks/todo.md, docs/progress.md.
- Scope: 3 files. Dependency: G6.

### Checkpoint D: Reviewed graph technical release

- [x] Measured delivery and exact-head checks reviewed/merged by the owner; no
  automatic database adoption, source request, public service or deployment.

## Completed: reviewed identity delivery

Scope #74 and plan #75 were approved. RI1–RI9 and owner checkpoints A–D are
merged through #84 at `50b43be`. RI10 #85 and RI11 #86 are also owner-merged
through `ef58c38`, completing checkpoint E. Exact-head quality/Compose/full worker
gates pass for both documentation candidates. Existing quality/security/audit,
coverage and all three hosted gates remain unchanged. Preserve older incomplete work.

Implementation mapping: RI1 #76, RI2 #77, RI3 #78, RI4 #79, RI5 #80, RI6 #81,
RI7 #82, RI8 #83, RI9 #84. See the [measured runbook](../verification/reviewed-decisions.md)
for exact candidates/runs, trust limits and physical recovery evidence. Next scope
is a separately specified company → procurement → buyer graph pilot with identity/
edge/time evaluation; no graph, model or workspace is implemented by this release.

### RI1: Strict private request/report inputs

- [x] Add immutable typed inputs, fixed failures and bounded file/JSON codecs.
- Acceptance: exact versions/types/fields, private ownership/no-follow/changed-file
  checks, 16 KiB request/4 KiB rationale/32 MiB report bounds; canonical request
  identity retains original text and excludes paths/server times. Invalid inputs
  fail without database access or source-bearing diagnostics.
- Verify: `uv run --frozen pytest tests/test_identity_review_inputs.py`.
- Files: `src/nima/identity/review_types.py`, `review_inputs.py` in that directory,
  `tests/test_identity_review_inputs.py`. Scope: three files. Dependencies: approval.

### RI2: Pure review transitions

- [x] Implement accept/reject/revoke state folding and compatibility/issue rules.
- Acceptance: one accepted pair, required conflict acknowledgment (including an
  outside anchor), no direct replacement/rejection of active acceptance, no
  resurrection or propagation; rejection creates no handle and revocation keeps
  other pair states intact. Original inputs remain immutable.
- Verify: `uv run --frozen pytest tests/test_identity_review_state.py tests/test_registry_policy.py`.
- Files: `src/nima/identity/review_state.py`, `review_types.py`,
  `tests/test_identity_review_state.py`. Scope: three files. Dependencies: RI1.

### Checkpoint A: Pure contracts

- [x] Input/state and unchanged comparison tests, quality/audit pass; human review.

### RI3: Explicit additive ledger migration

- [x] Add event/anchor/head schema and register migration 0007.
- Acceptance: preserve checksums 0001–0006 and populated source/workflow evidence;
  events/anchors immutable, revisions/request/anchor identities constrained and
  entity/event creation references checked at commit; no PUBLIC/worker-role grants
  or implicit migration. Required version-count tests advance without weakening them.
- Verify: `uv run --frozen pytest tests/test_identity_review_schema.py tests/test_postgres.py tests/test_workflow_requests.py`.
- Files: `src/nima/storage/migrations/0007.sql`, `src/nima/storage/postgres.py`,
  `tests/test_identity_review_schema.py`, `tests/test_postgres.py`.
- Scope: four files. Dependencies: checkpoint A.

### RI4: Revalidate frozen review evidence in SQL

- [x] Add connection-owned selected-evidence verification for writes/exports.
- Acceptance: exact occurrence/candidate/anchor joins and complete declared catalog,
  forged outcomes/labels/omissions rejected, old report coverage stays context,
  shared pure policy and combined 100-observation/8 MiB SQL bounds before labels;
  do not substitute current whole-run membership for historical report selection.
- Verify: `uv run --frozen pytest tests/test_identity_review_evidence.py tests/test_registry_cohort.py`.
- Files: `src/nima/identity/review_evidence.py`, `review_types.py`,
  `tests/test_identity_review_evidence.py`. Scope: three files. Dependencies: RI1–RI3.

### Checkpoint B: Storage and evidence boundary

- [x] Real upgrade/immutability/evidence/budget cases and normal gates pass; human review.

### RI5: First atomic acceptance library path

- [x] Deliver complete accept/new-or-existing-handle library transactions.
- Acceptance: database principal, UUID replay before/after subject lock, expected
  revision, anchor conflict validation and entity/event/head commit are atomic;
  stale/conflicting requests roll back; exact replay returns the old acknowledgment
  without changing current state. No CLI or source/outbox writes yet.
- Verify: `uv run --frozen pytest tests/test_identity_review_accept.py tests/test_identity_review_evidence.py`.
- Files: `src/nima/identity/review_store.py`, `review_types.py`,
  `tests/test_identity_review_accept.py`. Scope: three files. Dependencies: checkpoint B.

### RI6: Complete rejection and revocation library paths

- [x] Extend the working store with reject/revoke through the same transaction boundary.
- Acceptance: reject records no entity; revoke needs only stored current pair/event
  and expected revision, works without report/archive or current-policy eligibility,
  preserves other accepted pairs and never resurrects a prior decision. Reassignment
  is explicit revoke then accept; lost/interrupted intermediate state is unresolved.
- Verify: `uv run --frozen pytest tests/test_identity_review_reversal.py tests/test_identity_review_accept.py`.
- Files: `src/nima/identity/review_store.py`, `tests/test_identity_review_reversal.py`.
- Scope: two files. Dependencies: RI5.

### RI7: Prove races, principal permissions and SQL-commit recovery

- [x] Add independent-connection and actual child-kill verification of the full store.
- Acceptance: exact/different request UUIDs, competing accepts and entity collisions
  cannot create duplicate events/links; separate DB logins/grants enforce principal
  attribution and deny new read-only writes; actual before/after-COMMIT SIGKILL and
  lost-ack replay preserve one complete event and unchanged source state.
- Verify: `uv run --frozen pytest tests/test_identity_review_races.py tests/test_identity_review_permissions.py tests/test_identity_review_commit_crash.py`.
- Files: those three test files; at most `src/nima/identity/review_store.py` and
  `tests/test_identity_review_support.py` if a material regression/helper is needed.
- Scope: three to five files. Dependencies: RI5–RI6. Disposable test roles only,
  guaranteed cleanup, no production role grants or pause hooks.

### Checkpoint C: Complete verified write library

- [x] All actions, actual commit recovery, conflicts, principal/grant checks and
  unchanged sources pass with full normal gates; human review before CLI exposure.

### RI8: Private reviewed-resolution export library

- [x] Deliver the complete read-only SQL-to-canonical-private-artifact path.
- Acceptance: one consistent selected source/head/history/anchor snapshot, explicit
  coverage context and unresolved members, 1–10,000-event/100-observation/8 MiB SQL
  preflight, exact 32 MiB output, old snapshot immutability and deterministic
  verified reuse. Close SQL before publishing and keep automatic links zero.
- Verify: `uv run --frozen pytest tests/test_identity_review_snapshot.py tests/test_identity_review_export.py tests/test_registry_report.py`.
- Files: `src/nima/identity/review_snapshot.py`, `review_export.py`,
  `tests/test_identity_review_snapshot.py`, `tests/test_identity_review_export.py`;
  optional `review_types.py`. Scope: four to five files. Dependencies: checkpoint C.

### RI9: Expose CLI and prove export interruption/redaction/mutation

- [x] Add working review/resolution routes after both complete library paths pass.
- Acceptance: private request validation and existing routes, fixed 0/1/2/130 exits,
  no key/HTTP access, value-free parser/driver/publication failures, actual export
  publication SIGKILL and normal-CLI replay. A material revision/reversal mutation
  must fail a regression, then exact restoration and normal gates pass.
- Verify: `uv run --frozen pytest tests/test_identity_review_cli.py tests/test_identity_review_export_crash.py tests/test_identity_review_state.py tests/test_identity_review_races.py`;
  `just check`, `just audit`, exact-head full hosted quality/Compose/worker checks.
- Files: `src/nima/__main__.py`, `tests/test_identity_review_cli.py`,
  `tests/test_identity_review_export_crash.py`; optional one existing material
  state/race regression. Scope: three to four files. Dependencies: RI8.

### Checkpoint D: Operator workflow

- [x] Complete command, principal/reversal/snapshot semantics, actual recovery,
  restored mutation, ≥90% coverage and all three hosted checks pass; human review.

### RI10: Measured operator runbook

- [x] Document implemented setup/commands, trust/grants, outcomes and evidence limits.
- Acceptance: actual commands and exact-head results, private request/artifact
  examples and safe recovery, replay acknowledgment versus current state, selected
  context/unchecked authority and no empirical matching claims; no product-credit
  claim for merely writing docs.
- Verify: actual CLI help, local links, five-axis/prose review and unchanged gates.
- Files: `docs/verification/reviewed-decisions.md`, `README.md`, `CAPABILITIES.md`,
  `docs/architecture.md`, `docs/identity/reviewed-decisions.md`.
- Scope: five files. Dependencies: checkpoint D.

### RI11: Delivery and progress reconciliation

- [x] Record real merges/checkpoints and the next graph/evaluation gate.
- Acceptance: preserve old incomplete work and fixed scope weights; any capability
  credit requires delivered/evaluated evidence, not PR/test counts; unresolved
  live-access/authentication/consolidation/graph work remains explicit.
- Verify: cross-check commits/CI/attribution and human merges only.
- Files: `tasks/plan.md`, `tasks/todo.md`, `docs/progress.md`.
- Scope: three files. Dependencies: RI10.
- RI10 #85 / RI11 #86 are owner-merged; checkpoint E is complete.

### Checkpoint E: Reviewed release

- [x] Final measured runbook/delivery record and exact-head gates reviewed/merged
  by the owner; no automatic deployment, source request or external account action.

## Completed: offline registry comparison

Specification #65 and plan #66 were approved. RC1–RC5 and checkpoints A–C
are merged through #72 at main `c764dcb`. RC6–RC7 documentation was merged
through #73 at main `d6c1552`. See
[measured verification](../verification/registry-comparison.md) and the
[delivery plan](../../tasks/plan.md). Preserve older incomplete access/administration/product
work below. No new source access, migration, dependency, CI exception, accepted
identity link, graph or model is included in this documentation increment.

### RC1: Reuse the existing KIMDIS snapshot reader

- [x] Extract a connection-owned cohort read while retaining the current wrapper.
- Acceptance: the public assessment API/default bounds and fixture report bytes
  remain unchanged; the helper neither opens nor closes its caller's transaction;
  real reads retain snapshot/receipt/coverage and existing failure semantics,
  with an optional stricter helper input-byte budget checked before label transfer.
- Verify: `uv run --frozen pytest tests/test_identity_cohort.py tests/test_identity_report.py tests/test_identity_crash.py`,
  plus the unchanged quality/audit gates. The new cohort test file is added here.
- Dependencies: approved plan. Scope: two files.
- Files: `src/nima/identity/cohort.py`, `tests/test_identity_cohort.py`.

### RC2: Compare typed reported identifiers without accepting identities

- [x] Add immutable comparison inputs/results, fixed errors and pure policy.
- Acceptance: exact eligible AFM agreements produce the three specified outcomes;
  GR/EL, leading zeros, unknowns and every repeated/404 observation survive;
  conflicts are explicit and automatic identity links remain zero.
- Verify: `uv run --frozen pytest tests/test_registry_policy.py tests/test_identity_policy.py`;
  include Greek/lookalike/prefixed/missing/placeholder cases and both conflict kinds.
- Dependencies: RC1 for delivery order; policy remains independent of SQL/I/O.
- Scope: three files. Files: `src/nima/identity/registry_policy.py`,
  `src/nima/identity/__init__.py`, `tests/test_registry_policy.py`.

### Checkpoint A: Existing assessment and pure comparison contracts

- [x] Existing assessment is unchanged; pure candidate outcomes and exact unknowns pass.
- [x] Full quality/audit gates pass on a supported runner; review before SQL integration.

### RC3: Read one bounded, consistent KIMDIS/GEMI evidence cohort

- [x] Read explicit imports and procurement evidence through one shared transaction.
- Acceptance: preflight the combined 8 MiB input, requested mention budget and
  100 registry-observation bound before labels; reconcile selected versions/counts/
  responses/profiles and preserve allowed context/date/pointer/null values;
  absent/unsupported/incomplete data fail without writes or implicit latest selection.
- Verify: `uv run --frozen pytest tests/test_registry_cohort.py tests/test_identity_cohort.py tests/test_gemi_import.py`;
  use real concurrent PostgreSQL connections, transfer-bound assertions and
  source/outbox state comparisons. Unselected/new imports cannot enter the report.
- Dependencies: RC1, RC2. Scope: two files.
- Files: `src/nima/identity/registry_cohort.py`, `tests/test_registry_cohort.py`.

### RC4: Publish the complete deterministic comparison report

- [x] Deliver the snapshot-to-private-report library path through `compare_run`.
- Acceptance: one shared registry catalog and stable provenance references preserve
  all occurrences/observations; selected evidence/coverage reproduce canonical
  bytes regardless of selector order or repeated-version ties; exact 32 MiB bounds
  and private no-clobber publication/reuse hold with zero automatic identity links.
- Verify: `uv run --frozen pytest tests/test_registry_report.py tests/test_registry_cohort.py tests/test_identity_crash.py`;
  exercise complete synthetic SQL imports, all-404/empty-party outcomes, coverage
  changes, malformed publication paths, conflicts and exact byte limits.
- Dependencies: RC2, RC3. Scope: two files.
- Files: `src/nima/identity/registry_report.py`, `tests/test_registry_report.py`.

### Checkpoint B: Working offline SQL-to-report path

- [x] Complete private reports reconcile typed outcomes, context/provenance and bounds.
- [x] Existing assessment/source/outbox behavior and all normal gates remain green.
- [x] Human review before exposing the operator command; no live key needed.

### RC5: Expose the CLI and prove real interrupted replay/redaction

- [x] Add `identities compare` only after the complete library path passes.
- Acceptance: selectors/limits are validated and fixed summaries/exits match the
  approved 0/1/2/130 contract; actual pre/post-publication process termination
  preserves only complete reusable reports; a narrow guard mutation fails its
  regression, then exact restoration and the normal suite pass.
- Verify: `uv run --frozen pytest tests/test_registry_cli.py tests/test_registry_crash.py tests/test_registry_policy.py tests/test_registry_cohort.py`;
  use child-only boundary interception, runtime sentinels and immutable DB-state
  checks. Run `just check`, `just audit` and exact-head hosted quality/Compose/
  worker-fixture checks. No production pause/mutation hook or new skip/suppression.
- Dependencies: checkpoint B. Scope: three principal files, at most five if a
  missing material regression needs extension in the existing policy/cohort tests.
- Files: `src/nima/__main__.py`, `tests/test_registry_cli.py`,
  `tests/test_registry_crash.py`; optional existing `tests/test_registry_policy.py`
  / `tests/test_registry_cohort.py` regression extension only.

### Checkpoint C: Complete command and measured failure gates

- [x] Source assertions/unknowns, safe output, redaction and interrupted replay pass.
- [x] Mutant was detected and restored; exact-head checks/audit and ≥90% coverage pass.
- [x] No source request, identity acceptance, deployment or source-ledger mutation occurred.

### RC6: Publish the measured operator runbook

- [x] Document implemented commands, setup, exact-head evidence and remaining limits.
- Acceptance: the runbook distinguishes report agreement from identity/coverage/
  authority proof and explains private files/replay/errors; source/architecture
  capability notes match implemented behavior without live matching-quality claims.
- Verify: five-axis review, actual CLI help, local links and final hosted gates;
  reference concrete test/mutation results, not only this proposed task list.
- Dependencies: checkpoint C. Scope: five files.
- Files: `README.md`, `docs/verification/registry-comparison.md`,
  `docs/identity/registry-comparison.md`, `docs/architecture.md`, `CAPABILITIES.md`.

### RC7: Record delivery and the next product gate

- [x] Reconcile task/plan status and the capability-progress record after verification.
- Acceptance: actual merges/commits/tests are recorded; original progress weights
  remain and any estimate change is explained; reviewed reversible identity
  decisions and graph projection stay subsequent, separately reviewed work.
- Verify: cross-check final PR/CI/attribution and report scope; human merges only.
- Dependencies: RC6. Scope: three files.
- Files: `tasks/plan.md`, `tasks/todo.md`, `docs/progress.md`.

- [x] Human review/merge of RC6–RC7 through #73; all three checks pass on
  `9e5e4ac`. No automatic merge or deployment was performed.

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

## Safe database-run resume (completed)

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
- [x] Add reviewed supplier/buyer projections and an outbox consumer.
  - Acceptance: preserve joint participation without duplicating contract spend;
    consumer replay is idempotent. No automatic graph inference is implied.

## Reported contract participation (completed)

- [x] Define and test versioned facts, party occurrences and receipts.
  - Depends on: merged PR #13; verify exact amounts and populated-schema upgrade.
- [x] Implement bounded atomic projection and redacted CLI summaries.
  - Verify: replay, revisions, unknowns, joint suppliers, locked/concurrent events.
- [x] Prove rollback/retry with real worker termination; mutation-test one guard.
- [x] Complete review, checks/audit and private main-targeted PR with hosted CI.
  - Evidence: PR #14 targets main; 222 tests, 97.04% local coverage, real worker
    SIGKILL and offline 1,118-contract replay. Hosted push run 42779066374 and
    PR run 42779122179 passed at 11631d1; final-head links are recorded in the PR.

## Entity-resolution specification (approved)

- [x] Verify merged PR #14 and inspect official identifier/registry source contracts.
- [x] Draft SPEC-entity-resolution.md with candidate boundaries and acceptance criteria.
- [x] Obtain policy approval before implementation planning for this new module.
  - Review: offline candidate report first; no automatic merges or registry calls.
  - Evidence: user merged PR #15 (`33115f0`) and requested continuation.

## Offline identity assessment (completed)

- [x] Test and implement conservative identifier/candidate policy.
  - Verify: leading zeros, unknowns, country/key namespaces and review issues.
- [x] Read a bounded, complete projection cohort in one read-only snapshot.
  - Verify: real PostgreSQL receipt/limit guards, coverage and concurrent changes.
- [x] Publish reproducible private reports and expose redacted assessment CLI.
  - Verify: replay, paths, byte bounds, interruption before/after publication.
- [x] Complete mutation/review, checks/audit, cached replay and private PR/hosted CI.
  - Evidence: PR #16; 256 tests, 97.51% coverage; push run 42820672229 passed at
    f36d443. Final-head hosted links and review boundaries are recorded in the PR.

## GEMI source contract (approved)

- [x] Verify merged PR #16 and inspect official Swagger/authentication/source fields.
- [x] Document bounded profile lookup, registry evidence, KAD versions and integration limits.
- [x] Review the new credentialed-source contract before implementation planning.
  - Scope: explicit IDs, archive-first snapshots; no automatic identity decisions.
  - Evidence: user merged PR #17 (`1f45c70`) and requested continuation.

## GEMI profile collector (completed)

- [x] Normalize exact profile assertions, nullable metadata and versioned activities.
  - Verify: synthetic parser failures, source ID matching, raw hashes and field pointers.
- [x] Collect bounded explicit IDs with private raw evidence and truthful manifests.
  - Verify: credentials, retries/limits, 404/quarantine and archived failures.
- [x] Expose CLI; prove real interruption and redaction before source access.
- [x] Complete mutation/review, checks/audit and private PR with hosted CI.
  - Evidence: PR #18; 324 tests, 97.85% coverage; initial hosted checks passed at
    befd536. Final-head checks and the streaming-budget correction are linked in the PR.
  - Live compatibility requires personal credentials and explicit pilot IDs later.

## Offline GEMI evidence persistence

- [x] Obtain explicit user approval of docs/sources/gemi-persistence.md.
- [x] Validate one completed archive read-only and rederive profile assertions.
  - Verify: pure archive tests for reconciliation, evidence tampering and budgets.
  - Evidence: 393 tests, 97.96% coverage; docs/verification/gemi-archive.md.
- [x] Persist one immutable bounded run atomically through additive migration 0004.
  - Verify: real PostgreSQL history, replay, concurrency and populated v3 upgrade.
- [x] Expose redacted offline import CLI without HTTP or an API key.
  - Verify: success/configuration/failure/interruption and no archive mutation.
- [x] Prove actual worker termination before/after commit and mutate an integrity guard.
- [x] Complete review/checks/audit and private main-targeted PR with hosted CI.
  - Evidence: #20 and #21 merged into main (`b24c14a`); 411 tests, 98.05% coverage.
    Main CI run 42897504261 passed. See docs/verification/gemi-persistence.md.

## Local Prefect workflow

- [x] Obtain scope approval and explicit self-hosted Prefect selection.
- [x] Test/implement request identity, dispatch journal and persistent budgets.
- [x] Prepare one stable managed run; reuse resume and run-scoped projection safely.
- [x] Add pinned Prefect flow/tasks, private local dispatch and redacted CLI.
- [x] Verify actual server/runner recovery and mutate an integrity guard.
- [x] Pin Compose/CI, complete review/checks/audit and publish private review PRs.
  - Local evidence: 435 tests, 93.67% coverage, clean audit, actual Prefect/SQL
    crash tests and mutation caught. Image build passed; local Compose startup
    hit disk capacity; hosted Compose smoke passed at 9924c24 in run 43093598298.
    PRs #22–#26 were merged into main by the user at e80e23f. Its tree matches
    tested 749b9ee (hosted quality and Compose run 43094208540 passed).
    Post-merge main CI run 43095249289 was still queued at verification.
    See docs/verification/kimdis-orchestration.md. No production deployment.

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


## Bounded daily KIMDIS refresh

- [x] Approve bounded refresh spec and record ordered implementation tasks.
- [x] Validate pure policy/calendar selection with DST and outage tests.
- [x] Persist immutable policy/cycle/request identity in migration 0006.
- [x] Reconcile evidence-complete progress and bounded freshness inspection.
- [x] Integrate coordinator/schedules and serialized enable/pause with real Prefect.
- [x] Expose CLI and verify defaults, crashes, races, upgrade and changed evidence.
- [x] Complete local checks/audit/review and prepare private review PRs.
  - Evidence: 469 acceptance tests, clean audit/security, real SQL/Prefect crash
    recovery and mutation caught. See docs/verification/kimdis-refresh.md.
- [x] Pass final-head hosted quality/Compose checks before marking PRs ready.
  - PRs #27–#29 were merged into main at 242e9bb. Hosted final quality/Compose
    run 43163011288 passed with 469 tests. No live policy has been activated.


## Private manual Publicity evidence intake

Design: docs/sources/gemi-publicity-fallback.md, approved by the user on 2026-11-12,
including personal-IP protection. Implementation plan: tasks/plan.md, **approved**.
This extends source ingestion; all older incomplete tasks above remain tracked.

- [x] Record design approval and prepare the first offline delivery plan.
- [x] Obtain review of the implementation plan and these task acceptance criteria.
  - User approved by answering “Yes” on 2026-11-12.

### P1: Validate the manual capture manifest (complete)

- Acceptance: strictly decode a versioned manifest within 64 KiB/ten records;
  validate IDs, HTTPS metadata URLs, relative paths, media and protected-context
  claims. Preserve supplied values without treating them as source verification.
- Verify: `uv run --frozen pytest tests/test_publicity_evidence_policy.py`;
  include duplicate keys, unknown fields, invalid dates, oversized metadata,
  credential-bearing URLs and traversal. Pure validation performs no I/O/network.
- Dependencies: plan approval.
- Files: `src/nima/evidence/__init__.py`, `src/nima/evidence/publicity.py`,
  `tests/test_publicity_evidence_policy.py` (three files).

### P2: Publish one private immutable intake bundle (complete)

- Acceptance: copy only bounded regular files through no-follow descriptors;
  preserve/hash exact bytes and publish a completion manifest after durable blobs.
  Enforce private permissions, distinct archive marker and Git exclusion.
- Verify: `uv run --frozen pytest tests/test_publicity_evidence_intake.py`;
  original-byte comparison, size/signature mismatches, unsafe roots, read-time
  mutation, conflicting request UUIDs and publication failure leave honest state.
- Dependencies: P1.
- Files: `src/nima/evidence/artifacts.py`, `src/nima/evidence/intake.py`,
  `tests/test_publicity_evidence_intake.py` (three files).

### Checkpoint A: Evidence boundary

- [x] Review strict metadata, bounded file reads and atomic completion after P1–P2.
- [x] Confirm no content rendering, source fetch or API-format substitution.

### P3: Verify bundles independently and reconcile replay (complete)

- Acceptance: read-only verification rehashes every referenced object and validates
  manifest/channel/version/counts/bounds. Matching replay retains first observation;
  conflicting or corrupt evidence never succeeds or overwrites an accepted bundle.
- Verify: `uv run --frozen pytest tests/test_publicity_evidence_verify.py`;
  include missing/truncated/corrupt objects, symlink replacement, changed manifests,
  foreign API archives, concurrent reuse/conflicts and unchanged archive bytes.
- Dependencies: P2.
- Files: `src/nima/evidence/verify.py`, `src/nima/evidence/intake.py`,
  `tests/test_publicity_evidence_verify.py` (three files).

### P4: Expose the offline intake and verification commands (complete)

- Acceptance: implement the exact `evidence intake publicity` and `evidence verify`
  interfaces in tasks/plan.md. Output only UUID/version/counts/fixed reason codes;
  clearly label integrity success and unverified source/identity/capture claims.
- Verify: `uv run --frozen pytest tests/test_publicity_evidence_cli.py`;
  end-to-end synthetic input, help, exit codes, replay, redacted errors and socket/
  DNS guards prove the command performs no source fetch or database connection.
- Dependencies: P3.
- Files: `src/nima/evidence/cli.py`, `src/nima/__main__.py`,
  `tests/test_publicity_evidence_cli.py` (three files).

### Checkpoint B: Usable offline fallback

- [x] Review synthetic intake → verification without network access after P3–P4.
- [x] Verify no accepted company identity, registry-field extraction or SQL import.

### P5: Prove interruption and filesystem failure behaviour (complete)

- Acceptance: actual worker termination before publication leaves no accepted
  partial bundle; termination after publication is durably verifiable. Retrying
  the same input/UUID is safe; corrupt or conflicting replay is rejected.
- Verify: `uv run --frozen pytest tests/test_publicity_evidence_crash.py
  tests/test_publicity_evidence_verify.py`; real subprocess termination, competing
  writers and path swaps. Mutate one hash/replay guard, observe a failing test,
  then restore original implementation byte-for-byte.
- Dependencies: P4.
- Files: `tests/test_publicity_evidence_crash.py`,
  `tests/test_publicity_evidence_verify.py` and an affected evidence module if
  failure tests expose a defect (at most three files).

### P6: Review and publish a private implementation PR (complete)

- [x] Run focused failure checks, mutation, five-axis review and write runbook.
- [x] Pass final full quality/audit checks and publish private reviewable PRs.
  - Local runtime/test revision `f309961`: 576 tests, 93.03% coverage; clean audit.
    Delivery is split into design (#32), core (#33), then the dependent CLI PR.
- [x] Verify final-head hosted quality/Compose checks before marking ready.
  - #32, #33 and #34 were merged to main by the user. Main `ed52c38` has the
    identical file tree to tested `99a4144`. Post-merge run 43218895749 passed
    both quality and orchestration-compose. All three merged remote heads were
    removed by the cleanup workflow; local history remains available.

- Acceptance: a protected-capture runbook, strict input example and measured
  verification report describe what works and what remains unverified; private
  PR has StamKavid attribution and final-head hosted checks. Human merge only.
- Verify: five-axis review; `just check`, `just audit`, final-head hosted quality
  and Compose checks. Do not claim a live pilot, deployed IP protection or an
  implemented browser adapter from offline tests.
- Dependencies: P5.
- Files: `docs/verification/publicity-evidence.md`,
  `docs/sources/gemi-publicity-fallback.md`, `tasks/plan.md`, `tasks/todo.md`,
  `README.md` (at most five files).

### Deferred milestones

Remote-browser deployment and controlled-endpoint egress tests; permitted live UI
capture; HTML/session-data handling; registry assertion extraction; explicit SQL
import and comparison support; shared source budgets and Prefect scheduling.
These are not accepted as complete by this offline intake delivery.

## Source-worker egress verification specification

- [x] Verify all manual-evidence merges, main's tested tree and post-merge CI.
- [x] Draft the fixture-only network boundary and observable acceptance cases.
  - Contract: docs/sources/source-worker-egress.md. This is not deployed privacy
    infrastructure or permission to automate a government source.
- [x] Review the new contract before implementation planning.
  - User approved by saying “I approve” on 2026-11-12.

## Source-worker egress implementation

Plan: tasks/plan.md, **approved**. The approved contract is fixture-only; no
external account, source request or deployment. Existing incomplete work remains
tracked above. The following test commands describe future implementation checks.

- [x] Select immutable stack/OS pins and record bounded capability feasibility probes.
- [x] Review this implementation plan and task acceptance criteria before coding.
  - User approved execution by saying “Continue” on 2026-11-12.

### E1: Lock fixture Python dependencies

- [x] Locked without unrelated version changes; frozen export/audit verified.

- Acceptance: add dev-only Playwright 1.65.1 and cryptography 50.0.2; retain runtime
  declarations and unrelated resolved versions. Regenerate the existing hash-locked
  development-image export without downloading browsers into that image.
- Verify: frozen uv sync/export, `just container-lock-check`, `just audit`, existing
  quality/type checks; explain any unavoidable shared transitive resolution change.
- Dependencies: plan approval.
- Files: pyproject.toml, uv.lock, infra/requirements-orchestration.txt (three).

### E2: Freeze image, package and seccomp provenance

- [x] Built verified snapshot toolbox; package manifest and scoped capabilities checked.

- Acceptance: record the selected amd64 image digests, verified OS snapshot/feed,
  direct package versions/checksums and profile source/hash/licence. Build the
  helper from the exact signed feed; no unsigned/unversioned fallback.
- Verify: reproduce metadata/hash/signature checks and helper installed-package
  manifest. Helper works with read-only runtime root and no network.
- Dependencies: E1.
- Files: infra/source-worker/pins.json, infra/source-worker/seccomp.json,
  infra/source-worker/LICENSE.seccomp, infra/source-worker/Dockerfile.helper (four).

### E3: Prove the sandboxed browser prerequisite

- [x] Real pinned Chromium sandbox/version and helper probes passed in hosted run
  43267775558 at `98fa958`; all three CI jobs passed. The plan records the explicit
  one-rule derived seccomp profile and parent-denial/child-success checks.

- Acceptance: a pinned worker image runs UID 10001 with no capabilities, private
  IPC/state and the real Chromium sandbox. Preflight fails visibly on insufficient
  disk, unsupported user namespaces, mismatched binaries or missing prerequisites.
- Verify: unit parsing/redaction tests; a real network-none browser/data-page probe,
  exact version/sandbox observations and scoped helper-versus-worker capability
  checks on a sufficient runner. Never use no-sandbox or SYS_ADMIN as recovery.
- Dependencies: E2.
- Files: infra/source-worker/Dockerfile.worker, src/nima/egress/__init__.py,
  src/nima/egress/preflight.py, tests/test_source_worker_preflight.py,
  .github/workflows/ci.yml (five; adds the dedicated prerequisite job).

### Checkpoint A: Supported pinned runtime

- [x] Actual pinned-image browser launch/sandbox and helper capabilities verified.
- [x] Unsupported resource/kernel cases fail; no deployed privacy claim appears.

### E4: Define fixture policy and receipt semantics

- [x] Offline semantics, strict independent decoding and private atomic publication
  verified: 32 focused tests; hosted run 43272416378 at `1f72c8f` passed 634 tests
  with 91.86% coverage and all three jobs green. This does not claim that the
  later network cases have executed. The user merged #35 and #36 on 2026-11-13.

- Acceptance: immutable bounded policy/case models accept only fixed fixture
  identities and reject arbitrary live URLs or bypass options. Receipt validation
  requires complete case/control evidence and preserves all production/privacy
  verification flags as false; source formats and SQL remain separate.
- Verify: `uv run --frozen pytest tests/test_source_worker_policy.py
  tests/test_source_worker_receipts.py`; missing/conflicting evidence, bounds,
  redaction and private atomic report publication without network.
- Dependencies: E3.
- Files: src/nima/egress/policy.py, src/nima/egress/receipt.py,
  tests/test_source_worker_policy.py, tests/test_source_worker_receipts.py (four).

### E5: Build controlled fixtures and independent observation

- [x] Ephemeral certificate/credential setup and UID/private-control preflight.
- [x] Synthetic service listeners and private counters.
- [x] Closed Docker wiring and independent observer controls; the complete
  fixture stack passed at `c937584` in hosted run 43397091843.
- Delivery: #37 certificate setup → #38 services → #39 fixture wiring; each is reviewed
  separately; #40 delivered #39 to main after its dependency-branch merge.
  Exact delivery head `cfcb677` passed both hosted runs with 650 tests/90.54%. E6 gateway
  authentication/TLS, E7 kernel enforcement and the full matrix remain pending.

- Acceptance: generate ephemeral CA/server material and sentinel credentials on
  private volumes, expose only a public CA to the worker, and provide HTTPS and
  TCP/UDP/DNS canaries with private control counters. Observer UID 10002 is distinct
  from workload UID 10001 and never a live collection identity.
- Verify: `uv run --frozen pytest tests/test_source_worker_bootstrap.py
  tests/test_source_worker_fixtures.py tests/test_source_worker_observer.py`; real
  observer positive controls, private-control access rejection and TLS material
  absent from Git/logs. Create only closed, project-owned networks/resources.
- Dependencies: E4.
- Files: src/nima/egress/fixtures.py, src/nima/egress/bootstrap.py,
  src/nima/egress/observer.py, tests/test_source_worker_fixtures.py,
  infra/compose.source-worker-test.yml (five).

### E6: Prove gateway CONNECT, TLS and authentication

- [x] Fixed static bootstrap, enforced RBAC/challenge and private config tests.
- [x] Bounded HTTPX/browser probes and strict independent counter decoding.
- [x] Pinned Envoy validation and real Docker HTTPX/Chromium protocol checks.
  Evidence: `4d749ae`, hosted run 43403470378, two Docker tests/21.04 seconds.
  Final delivery-head quality checks are recorded in the implementation PRs.
- Implementation: `protocol.py` contains executable fixture-only client probes;
  its unit tests cover trust/sandbox options, bounds and error redaction. Observer
  changes read only allowlisted numeric admin counters. These extra files keep
  protocol work out of bootstrap and the temporary test controller.

- Acceptance: static-authority Envoy routing and enforced RBAC accept only the
  fixture; Basic authentication challenges correctly, credentials stay on the
  proxy hop and invalid TLS is rejected. Prove Chromium NSS trust/challenge
  compatibility here before building its later transport matrix.
- Verify: unit gateway-policy tests plus explicit Docker integration; validate
  config with pinned Envoy and complete real HTTPX and sandboxed Chromium HTTPS
  tunnels. Test missing credentials, raw-IP/host/port denial, invalid certificates
  and no secret-bearing config/log output. Counters are observable privately.
- Dependencies: E5.
- Files: src/nima/egress/gateway.py, tests/test_source_worker_gateway.py,
  tests/source_worker_integration.py, infra/compose.source-worker-test.yml,
  src/nima/egress/bootstrap.py (five).

### Checkpoint B: Real gateway/fixture protocol

- [x] HTTPX/browser HTTPS, proxy challenges and NSS trust pass with real controls.
- [x] Private control sockets/config and fixture credential files are inaccessible
  to the workload; no open relay. The worker receives only its required proxy
  username/password through explicit runtime configuration.

### E7: Enforce the worker namespace packet policy

- [x] Fixed policy, named counters and strict stable kernel readback.
- [x] NET_ADMIN-only setup exits before workloads; normal inspection is read-only.
- [x] Real direct/host/metadata/DNS/UDP delivery denial with working controls.
- [x] Outer observer UID and parent network administration remain unavailable to
  the workload and its user-namespace child; effective IPv6-disabled mode checked.
- Evidence: `d8e0a3c`, run 43422295581, three Docker tests/49.27 seconds,
  746 tests/90.72% coverage, all three jobs green. Final-head CI stays required.
- Delivery slices: #43 policy/decoder; setup/readback; packet/privilege probes.
  All target main. Rules, helper and probes have separate modules/tests so the
  privileged path remains small. The observer checks local alias binding before
  metadata HTTP. See the plan for nft readback normalization and the two narrow,
  explained subprocess annotations. No live collection or deployment enabled.

- Acceptance: NET_ADMIN exists only in a trusted helper sharing the anchor's
  namespace. It installs default-drop output, exact gateway/UID rules and local
  fixture aliases, then exits before starting cap-free workload processes. IPv6
  is explicitly disabled; a child user namespace cannot change the parent policy.
- Verify: policy unit tests and real Docker probes for direct/host/metadata/DNS/UDP
  delivery denial with observer successes, effective UID/capability/sysctl evidence
  and stable rule counters. No first-party host firewall or routing changes.
- Dependencies: E6.
- Files: src/nima/egress/network.py, tests/test_source_worker_network.py,
  tests/source_worker_integration.py, infra/compose.source-worker-test.yml (four).

### E8: Execute HTTPX cases through a bounded host runner

- [x] Implement 18 fixed HTTP-stage probes with bounded verified-TLS attempts.
- [x] Run the HTTP matrix through the bounded host controller in CI.
  - `e866c97`, run 43514084957: 884 tests, 91.37% coverage, all three jobs green;
    four real Docker tests/149.92 seconds include the runner's complete HTTP stage.
- [x] Extract the host controller with run-wide bounds and ownership failure tests.
- [x] Publish private reconciled HTTP-stage reports with incomplete matrix explicit.
  - Delivery: #47 process capture; #48 owned controller; #49 private stage format;
    #50 runner/runbook. Merge into main in order. Final-head checks stay required.

- Acceptance: fixed-case HTTPX probes cover proxy bypass, redirects, TLS, credentials,
  host/metadata and gateway failure. A host controller generates/owns its resources,
  enforces budgets and publishes reconciled private receipts; it offers no live mode.
- Verify: `uv run --frozen pytest tests/test_source_worker_http.py`; real
  integration cases with controls, NO_PROXY/trust_env=False attempts, UID-change
  denial, invalid configuration and no direct fallback. No live endpoints are used.
- Dependencies: E7.
- Files: src/nima/egress/probe_http.py, src/nima/egress/runner.py,
  tests/test_source_worker_http.py, tests/source_worker_integration.py (four).

### E9: Exercise Chromium subresources and alternate transports

- [x] Implement ten fixed sandboxed Chromium cases with strict private results.
- [x] Observe process/kernel state, forwarding, privileges and actual network attachments.
- [x] Combine all 28 cases and publish the strict full receipt only after cleanup.
- [x] Verify final-head hosted browser and combined runtime matrix.
  - #51 probes, #52 observed runtime/topology and #53 full matrix are merged at
    `c02ef94`. QUIC/STUN now pass; the browser gateway-outage timeout correction
    is verified in #54 at `c6e9c39`: runs 43613463647/43613476257 pass all three
    jobs, 967 tests/91.55% coverage and six real Docker tests/334.31 seconds.
    The correction is merged through #54 at `9562213`. The owner explicitly confirmed public
    hosting on 2026-11-14; private evidence handling is unchanged.
    See docs/verification/source-worker-browser.md.
  - The runtime slice adds runtime.py, its focused tests and a cap-free gateway
    inspection service so receipt fields come from observations, not declarations.

- Acceptance: full Chromium uses the private NSS trust database and explicit
  sandbox; page/scripts/images/XHR/fetch use the gateway. DNS, UDP/QUIC/STUN and
  proxy-configuration changes cannot escape. Worker never mounts observer controls.
- Verify: unit result/redaction tests and real browser cases; observer counters,
  denied-delivery evidence, invalid-cert rejection and explicit IPv6 disabled-mode
  observations. No ignored certificate errors or unfiltered traces.
- Dependencies: E8.
- Files: src/nima/egress/probe_browser.py, tests/test_source_worker_browser.py,
  tests/source_worker_integration.py, src/nima/egress/runner.py (four).

### Checkpoint C: Complete named acceptance matrix

- [x] All required HTTPX/browser cases and controls reconcile within budgets.
- [x] Receipt distinguishes observed fixture isolation from undeployed IP protection.

### E10: Prove failure, redaction and mutation behaviour

- [x] Run missing-capability and worker deadline failures on actual fixtures;
  require nonzero outcomes, no accepted receipt and scoped resource cleanup.
- [x] Terminate an actual controller/worker process while work is active;
  prove no success receipt, then reclaim only independently verified run-owned
  resources. A killed controller cannot perform its own finally block.
- [x] Mutate one narrow packet guard inside the disposable worker namespace;
  independently observe forbidden delivery and require the negative case to fail.
  Restore the exact owned change in finally, verify the original policy/namespace,
  destroy the fixtures and rerun the normal complete matrix.
  - #57 is merged at `1c9ac26`; candidate `32244f7` passes all three jobs in
    run 43615164185: seven real Docker tests/522.18 seconds and 967 quality
    tests/91.47% coverage. The mutant causes actual forbidden delivery, both
    validators reject it, and restored blocking/full-matrix replay pass.
- [x] Verify runtime-generated credential sentinels stay out of diagnostics;
  preserve the full case/runtime validator and all isolation/TLS/sandbox controls.
  - #59–#61 are merged through `920472e`. Candidate `f3a063e` passed all
    three jobs in run 43622181210: 967 quality tests/91.55% coverage and
    12 real Docker tests/853.96 seconds. See the failure-experiment runbook.

- Acceptance: stopped gateway, missing capabilities, absent cases, interrupted/
  timed-out controller or invalid ownership never create a successful receipt or
  broaden cleanup. Runtime-generated sentinel secrets remain out of diagnostics.
- Verify: real outage/interruption/cleanup controls and an actual packet-guard
  mutation, on disposable closed fixtures only. The negative-case regression must
  fail, then restore original guard bytes and rerun the normal matrix.
- Dependencies: E9.
- Files: tests/source_worker_integration.py, tests/test_source_worker_receipts.py,
  src/nima/egress/runner.py (three).

### E11: Integrate the complete CI gate

- [x] Add the complete recipe and private canonical full-receipt artifact validator.
- [x] Wire CI and matching proposed required contexts; preserve existing gates.
- [x] Verify the final real-Docker recipe and downloaded artifact.
  - #62/#63 are merged through `9a4eddf`; final candidate `4fe920d` passes
    all three jobs in run 43625798326: 987 tests/91.58% coverage and 12 real
    Docker tests/616.42 seconds. Downloaded artifact 14126851164 matches its
    ZIP digest and contains one canonical 10,109-byte full 28-case JSON receipt,
    with deployment/privacy flags false and no extra files.

- Acceptance: `just source-worker-check` and a mandatory additive CI job run the
  complete explicit integration file and publish only redacted receipts. Existing
  quality/Compose gates remain. Include the new context in the proposed protection
  payload while retaining the documented block on server-side enforcement.
- Verify: `just source-worker-check`, `just check`, `just audit` and exact-head
  hosted checks. Check the proposed ruleset and workflow context names agree;
  no live repository-administration or billing change.
- Dependencies: E10.
- Files: .github/workflows/ci.yml, justfile, .github/rulesets/main-dev.json,
  docs/repository-settings.md (four).

### E12: Review and publish the measured delivery

- [x] Document actual setup, complete command, measured gates and recovery limits.
- [x] Review correctness, readability, architecture, security and performance.
- [x] Verify exact-head hosted gates and human delivery merge.
  - #64 is merged at `127b3b8`. Candidate `39fd05b` passed all three jobs in
    run 43627192150: 987 quality tests/91.58% coverage and 12 real Docker
    tests/624.58 seconds. One full 28-case receipt passed final verification and
    was uploaded as artifact 14126678873. Deployment/privacy flags stay false.

- Acceptance: runbook and evidence state actual results/prerequisites and limits.
  Small dependent PRs use StamKavid attribution; no dependent merge to an
  obsolete base, automatic merge, source request, purchase or deployment.
- Verify: five-axis review, final exact-head checks and public-IP/privacy flags
  remain false in fixture receipts. Human review/merge is the final delivery gate.
- Dependencies: E11.
- Files: README.md, docs/verification/source-worker-egress.md, tasks/todo.md,
  tasks/plan.md, docs/sources/source-worker-egress.md (five).

Progress-only updates to this plan/spec remain separate from behaviour changes.
The implementation progress above records passing prerequisite, offline and
closed-fixture gates, including the full network matrix, real failure/mutation
experiments, final recipe/downloaded artifact and E12's measured delivery merge.
Deployed IP protection remains unverified; registry comparison needs its separate
specification review before planning or implementation.
