# Tasks

## GEMI AFM lookup (spec drafted 2026-11-20)

- [x] L1: spec reviewed and decisions D1-D6 recorded as recommended by the owner on 2026-11-20.
- [x] L2: owner merged #172 at `f574266` (pure parser, all outcomes, string `arGemi`; `normalize_profile` split into `decode_body` and
  `normalize_company`); reachable from `origin/main`. Hosted run 44909801231 on `e6dd5ef` passed all three jobs. 53 tests, 100% line and
  branch for `gemi_search.py`, 18 rule breaks all caught.
- [ ] L3: collector `ingest gemi-afm` on the shared GEMI transport, archive-first; crash, retry and budget tests.
- [ ] L4: read-only archive verification for search runs.
- [ ] L5: import of hits and `queried_not_found_at_observation` (migration; ask the owner first).
- [ ] L6: live pilot on the owner's machine (three existing AFMs, one 404, equivalence and latency); amend the spec.

## V1-05 S2 — time model, measured first

- [x] Spec approved 2026-11-20 (`docs/specs/SPEC-semantic-model.md`), decisions D1-D5 as recommended.
- [x] S2a: tests first, then `scripts/semantic_census.py`: owner merged #168 at `d8f5d49`, with the line-ending fix #169
  (`741b6f3`); both reachable from `origin/main`. Hosted run 44797837256 on `741b6f3` passed all three jobs
  (`quality`, `orchestration-compose`, `source-worker-egress`). 14 tests on PostgreSQL 17 (Linux), 100% line and branch for the
  module, 24 query mutations all caught. Both PRs were merged while their own `quality` jobs were still pending and the
  intermediate main runs were cancelled; the green run above covers their combined head. The census has not been run on real data.
- [x] Census on real data, first sample (2026-11-20): the earlier pilot database lived in an unreachable ChatGPT
  sandbox, so a local PostgreSQL was rebuilt from one small bounded KIMDIS capture (4 records, one day, one buyer),
  under the owner's dated waiver of the home-IP rule for that one capture. Result recorded in
  `docs/semantics/date-format-measurements.md`: one submission shape `9999-99-99A99:99:99.999`, update date missing,
  leading-zero tax IDs common.
- [x] Wider capture for variety (2026-11-20, run by the owner): about 90 days of the same public buyer, 199 more records,
  complete, 0 quarantined; census over 203 records recorded in `docs/semantics/date-format-measurements.md`.
  Findings: submission date has two observed shapes (fraction of two or three digits, no zone); update date is
  date-only and mostly absent; no placeholder tax IDs; leading zeros common; 3 irregular-length IDs.
- [ ] Optional: more buyers for variety (the owner names them and approves the capture).
- [x] S2b: `src/nima/semantics/timemodel.py` from the measured shapes: owner merged #174 at `4e6ea80`; reachable from `origin/main`.
  Zone-less ISO submission date-time with a fraction of one to six digits (one to three chosen by the owner, six seen on 4 of 1,317
  records and added), date-only update date, `parsed`/`absent`/`unparseable`, no zone conversion. 69 tests, 100% line and branch, 21
  rule breaks caught. Measured shape table recorded in `docs/semantics/date-format-measurements.md` (#173, `09ab852`). Decision D4: no new
  placeholder rule needed (none in 1,374 tax IDs); irregular-length IDs (about 1.2%) stay ineligible and disclosed.

## V1-05 S3 and S4 — shared selection, then U2

- [x] S3: owner merged #175 at `e6dd5ef`; reachable from `origin/main`. Hosted run 44909801231 passed all three jobs (`quality`,
  `orchestration-compose`, `source-worker-egress`); the earlier intermediate main runs were cancelled by the quick succession of merges.
  `selection.select_latest` and `parties` extracted from `participation`; the nine pins taken first from unmodified main pass unchanged
  (U1 result bytes, definition hash and reference SQL hash did not move); 47 new tests, 18 rule breaks caught. The provider import guard
  was narrowed to exactly the two new pure sibling modules and extended to them (merged by the owner, so accepted).
- [ ] S4: owner merges the U2 PR (`captured_record_count_by_cpv_period.v1`: pure provider plus reference SQL, 57 tests with PostgreSQL
  parity, 100% line and branch, 56 rule breaks across Python and SQL caught, three equivalent SQL constructs removed); verify on
  `origin/main` and read the hosted run before marking delivered.
- [ ] Preserve the original archives of future captures (mount an output folder and copy the archive out): the archives of runs 2 to 5 of
  the local sample were lost with their temporary containers, so metadata snapshots and real-data U2 cannot be rebuilt from them.
- [ ] S5 U3 buyer record concentration, S6 lifecycle references plus U4 change between captures, S7 catalogue and promotion to `reviewed`.

## V1-04 — source boundaries for a second feed

- [x] Spec approved 2026-11-19 (`docs/specs/SPEC-source-boundaries.md`): test both second-adapter kinds,
  shrink-only baseline for existing cycles, per-adapter versions.
- [x] S1 freeze: owner merged #154 at `d3b0e90`; exact `d2febce` verified on main. Hosted run
  44606219260 was the only run on that head and passed all three jobs (`quality` 12 min 46 s).
  `scripts/dependency_graph.py`, committed `tests/dependency_baseline.json`, 21 tests, 100%
  line/branch; real-repo mutations (a forbidden import and a new cycle) fail and are restored.
  Baseline: six engine-to-source imports (three KIMDIS, three GEMI), one five-package cycle
  group, two module cycles.
- [x] S2 protocol: owner merged #155 at `bb99485`; exact `cf62969` verified on main. Hosted run
  44609972812 was the only run on that head and passed all three jobs (`quality` 12 min 55 s).
  Neutral `nima/sources/base.py` and a `KimdisAdapter` wrapping the unchanged parser; 12 parser
  conformance cases and 4 database equivalence cases.
- [x] S3 engine on the protocol: owner merged #156 at `53b53ad`; exact `0548870` verified on
  main (tree identical). Hosted run 44629025079 was the only run on that head and passed all
  three jobs (`quality` 10 min 4 s). Local suite 2932 passed, 59 failed (the unchanged PG16
  environment baseline). Two replay tests now simulate history by injecting a historical
  adapter instead of patching module globals; their assertions are unchanged. Characterization pins recorded from the unmodified
  engine (four scenarios; all database rows, the archive sidecar files and the replay artifact,
  stable across independent databases) and committed before the change. The page store, run
  store, collector, resume and replay now take an adapter (default KIMDIS through a registry);
  the pins pass unchanged on the moved engine, and a stand-in source runs through the real store,
  collector and replay. The KIMDIS edges are gone from the dependency baseline (three GEMI edges
  remain; cycles unchanged). Mutations (sidecar key order, wrong record hash, engine re-importing
  KIMDIS) fail and are restored. An initial pin set missed the wrong-hash mutation because every
  page had one record, so a multi-record scenario was added and its pin recorded from the old
  engine in a separate worktree. Known limits: the HTTP transport is still KIMDIS-specific, replay still labels its archive
  layout `kimdis`, and the three GEMI imports stay in the baseline.
- [x] S4 two synthetic adapters of different shape; conformance on all three: owner merged
  #157 at `0945918`; exact `645f75f` verified on main (tree identical). Hosted run 44692930584
  was the only run on that head and passed all three jobs (`quality` 16 min 27 s, the longest so
  far; parallel tests become the next option if a run nears 18 minutes). Local suite 3017
  passed, 59 failed (the unchanged PG16 environment baseline). Test-only `ledger` (semicolon text, decimal-comma money,
  `L-0001` ids, line-number evidence) and `events` (nested JSON, cursor paging, integer minor
  units with per-currency exponents, composite ids); neither is registered, so no product code
  or engine file changed. Parser conformance now runs 11 shared tests on all three adapters, and
  a new engine suite runs the real collect, resume, replay, quarantine and identity-coverage
  paths on all three plus a shared-database isolation test. Nine mutations (engine evidence
  pointer, identity check, replay and resume dropping the adapter, store ignoring the adapter's
  version, and five adapter bugs) fail the new tests and are restored. Found, not fixed (needs an
  engine change): a ledger run's archive manifest records the KIMDIS endpoint, source URL and
  CC BY 4.0 licence because the collector hardcodes them; this is an S5 prerequisite.
  **Correction (2026-11-20):** "resume passes for the synthetic sources" held only because every
  synthetic run used a KIMDIS-shaped `Query`; `load_options` rebuilds a KIMDIS `Query`, so a
  real non-KIMDIS run could not be resumed, and every request still goes to the KIMDIS
  endpoint. Fixed by N1 (#158: request, provenance) and N2 (#159: run options, resume).
- [x] Spec `docs/specs/SPEC-source-neutral-collection.md` approved 2026-11-20: two PRs, no migration, five
  deferred items with triggers.
- [x] N1 source-neutral request and provenance: owner merged #158 at `535a16e`; exact `d4aec07`
  verified on main (tree identical). Hosted run 44702178868 was the only run on that head and
  passed all three jobs (`quality` 13 min 18 s). Local suite 3084 passed, 59 failed (the
  unchanged PG16 environment baseline). Tasks, each test-first:
  - [x] N1.1 pins recorded from unmodified `main` `0945918`: KIMDIS wire request (method, URL,
    headers, body, three pages) and manifest minus volatile fields; stable across three runs;
    each fails when the `Accept` header or the licence string is changed, then restored.
  - [x] N1.2 protocol: `SourceProvenance`, `SourceRequest`, `provenance`, `request_for`, and the
    pre-network guard `checked_provenance` / `checked_request` (https, no credentials, query
    string or fragment, URL equals the declared endpoint, GET carries no body, clean single-line
    text). Tests written first and failing at import; 100% line and branch on `sources/base.py`.
  - [x] N1.3 engine: `Session.request` takes a `SourceRequest`; the collector checks the adapter
    before any run, archive file or request exists, builds every request through the guard and
    writes the manifest from `provenance`; `ENDPOINT` and `SOURCE` moved into the KIMDIS module.
    The N1.1 pins pass unchanged, so KIMDIS wire requests and manifests are byte-identical.
  - [x] N1.4 engine suite on all three sources (local): every request goes to the source's own
    endpoint in its own shape (KIMDIS POST with a body, `ledger` GET with none and `text/csv`,
    `events` POST with its own page parameter); each manifest records its own provenance; a
    mis-wired adapter is refused before any run, file or request, and one that goes wrong only on
    a later page is refused before that request. Twenty mutations across transport, collector and
    guard fail the tests and are restored. One survived and one was misleading, both fixed: the
    credentials check was only tested with a user and a password together, and the password check
    was dead logic (any userinfo already makes the username non-null), so it was removed.
  - [x] N1.5 full gates, draft PR and hosted exact-head proof.
- [x] N2 adapter-owned run options and resume through the registry: owner merged #159 at
  `384a446`; exact `db389a2` verified on main (tree identical). Hosted run 44709623301 was the
  only run on that head and passed all three jobs (`quality` 11 min 42 s). Local suite 3136
  passed, 59 failed (the unchanged PG16 environment baseline). Tasks, each test-first:
  - [x] N2.1 tests first, failing: generic `load_run_options` (payload, connector version,
    limits, root); KIMDIS `Query` parsing in the KIMDIS module with the old error messages;
    `registry.adapter_from_run`; `collect` takes its query from the adapter and refuses a
    disagreeing one; resume of a run whose stored query is not KIMDIS-shaped; an unregistered
    source stops before any request. The S4 engine tests stop handing every source a KIMDIS
    `Query`.
  - [x] N2.2 implementation: `QueryPayload`, widen `start_run`/`begin`/`takeover` to
    `PayloadSource`, generic `load_run_options` in storage (no `Query`), KIMDIS parsing and
    `from_payload` in the KIMDIS module, registry lookup by connector version, `collect` and
    `resume` use them; the orchestration pipeline keeps its own KIMDIS helper.
  - [x] N2.3 mutations: twenty across `collect`, `resume`, the registry, the KIMDIS
    rebuild, `QueryPayload`, `load_run_options` and the pipeline; three survived and were closed
    with tests (a shallow copy of the saved payload, and the pipeline's comparison of a prepared
    run with its request, which had no test before N2 for query, limits or archive root). One
    `text()` helper became unreachable and was removed. Full gates, draft PR and hosted proof
    follow.
- [x] V1-06 step 1, Diavgeia acceptance dossier (`docs/sources/diavgeia-acceptance.md`): owner
  merged #160 at `8285b24`; exact `f71435d` verified on main (tree identical). Hosted run
  44723790870 passed all three jobs (`quality` 9 min 35 s). Read from the official API
  documentation and terms of use on 2026-11-20 (originals archived outside Git with hashes),
  nothing from memory, no search or data endpoint called. Findings: CC BY 4.0 plus Law 3448/2006
  with mandatory attribution; no stated rate limit; decisions carry personal data; Diavgeia
  documents no link back to KIMDIS, but KIMDIS records carry `diavgeiaADA` (already parsed here), so
  the explicit key sits on the KIMDIS side, and Diavgeia types chain by ADA. Owner decision 1
  (accept for a bounded pilot): **yes**, 2026-11-20. Decisions 2 to 5 recorded as decided on the
  owner's explicit instruction, 2026-11-20: attribution wording, personal-data rule, "measure first"
  (the census), and the default request rate with a pilot-only egress entry added in the adapter
  change. No Diavgeia request and no adapter code until the census has been run and reviewed.
- [x] Prior art on linking these sources (docs only, follow-up to the dossier; owner merged #161 at
  `4c6d41f`, exact `5f74cc4` verified on main, hosted run 44742139156 green, `quality` 13 min 10 s):
  Diavgis (Open
  Contracting registry) links Diavgeia, KIMDIS and TED, and says records of one procurement share
  an `ocid`, but names no keys. Its policy page blocks automated clients, so the owner pasted its
  text and its methodology page (no hash). The methodology says none of its links is confirmed by
  explicit proof today (0% of chains) and that references shared by many acts are not chain links.
  Next: run the two read-only counts in the dossier's "Measure first" on the pilot database. The
  arXiv corpus is Diavgeia-only and the iMEdD article is commentary. Unread leads are listed.
- [x] Diavgeia link census (`scripts/diavgeia_link_census.py`): a read-only command that counts how
  many of our own KIMDIS records cite a Diavgeia decision (`diavgeiaADA`) and how many records share
  each cited decision, reporting counts and public ADA identifiers only. 13 tests, 100% line and
  branch, nine mutations caught. To be run by the owner on the pilot database before any Diavgeia
  request; the result decides whether the explicit-key pilot is worth running.
- [ ] S5 real small public dataset (gated: owner names it, reuse terms checked, host allowed).
  Candidate: fetch exactly the ADAs a small KIMDIS cohort cites in `diavgeiaADA` (one by one, with
  their version logs); fallback Δ.2.2 κατακύρωση for one organisation and one window of at most
  180 days. First measure how many KIMDIS records carry `diavgeiaADA`.

## Checkpoint C5 — source acceptance and readiness

- [x] Verify #132/#133 reachability; #134 is merged at `ad62fb3` and the exact
  reviewed command files are now verified reachable from main.
- [x] Record source connection states, end-to-end pipeline and proposed 61/100
  planning rubric (report approximately 60%); preserve the old scope baseline.
- [x] Capture/hash-verify AADE references/terms privately, inspect actual columns
  and source reuse conditions; preserve version/representation uncertainty.
- [x] Specify KAD runtime acceptance without pretending a parser is installed.
- Required local gates/audit and exact-head hosted results are recorded with the
  delivery PR before handoff; source inspection alone does not pass those gates.
- [x] Owner reviewed C5 through merged #135 (`0fb8734`); #134 main promotion is merged.
- [ ] Runtime KAD use: resolve reuse scope, full extraction/reconciliation proof
  and source-format contract before implementation/adoption.
- [ ] Next independent implementation: bounded DataOps health/freshness report
  and structured failure logs; source activation remains separately gated.

## Checkpoint C4 — reviewed deployment and CPV references

Continue after owner-merged #131 (`7bdf5da`); C3 hosted run 44290911542 passes all
three jobs. Preserve human validation, KAD crosswalk and model tasks below.

- [x] Freeze C4 deployment/reference boundaries and sequential work.
- [x] C4a: native verified backup/restore before reviewed pilot migration 9; narrow
  grants, prior metadata promotion, original readout/source preservation and cleanup.
- [x] C4b: inspect and pin actual official CPV bytes, reuse attribution and format;
  implement a bounded typed reader with malformed/security/coverage tests.
- [x] C4c: separately versioned reference matches/private publication/CLI; no source
  assertions or historical versions overwritten and no inferred company sector.
- [x] C4d local: real-release check, meaningful duplicate/version guard mutations,
  2,285 tests/93.27%, clean audit and private CLI/SQL proof. Hosted exact-head
  results are recorded with both delivery PRs before handoff.
- [ ] Owner review; dictionary features are not live by documentation alone.


## Current extension: SQL replay promotion

Owner merged #126 at `ecb5a85`; all three exact-head jobs pass in run 44154596290.
Continue the approved DataOps plan; preserve all other pending tasks.

- [x] P1: freeze explicit selected-hash, original-time and separate processing
  schema contract in the source-ingestion spec and [plan](plan.md).
- [x] P2: additive 0008 migration, immutable batches/results/view, old checksum
  preservation, ownership/constraint and upgrade regressions. Five files.
- [x] P3: shared public replay preparation plus bounded atomic SQL promotion,
  shared source lease/recheck, limited promoter and deterministic retry/conflict
  handling.
  Verify real SQL/files, actual SIGKILL before/after commit and concurrent retries.
  Files: replay, run storage, promotion module and its two test modules (five).
- [x] P4: `archive promote` command with explicit selected hash, fixed private-safe
  summaries and real CLI tests. Files: archive CLI and CLI promotion test module.
- [x] P5: hash-guard mutation, private migrated clone proof and required full
  `just check`/`just audit`; record only actual observed results and limitations.
- Evidence: 42 focused cases pass, including actual SIGKILL and concurrent retries
  with both read-committed and repeatable-read role defaults. A failing regression
  led to explicit READ COMMITTED write isolation. Selected-hash mutation fails and
  is restored. Private clone promotion/limited roles/original readout pass; source
  pilot database, originals and three HTTP guards remain unchanged. Native CHECK
  reparse equivalence is retained privately. No source request. Final local gate:
  2,093 passed/93.10%, clean audit and verified final wheel contents.
- [x] Owner merged #127 at `ef2b438`; corrected exact-head hosted checks pass
  in run 44168550280. Continue pilot maintenance at C1.
- [ ] Follow-up: request/refresh version-policy handling, structured metadata,
  isolated models and pending human validation; no implicit metric activation.

## Current extension: offline normalization replay

Owner merged #125 at `d98a971`; run 44146760312 passes all three jobs. Same approved
DataOps plan; preserve pending human review, metadata and model work below.

- [x] AR1: freeze the bounded replay contract in the source-ingestion spec and
  [plan](plan.md). Explicit installed target, retained historic lineage, no SQL
  promotion/source calls, deterministic private dataset and fixed limits.
- [x] AR2: deliver `archive replay` end to end using public SQL/schema, recovery,
  normalizer and publisher APIs. Preserve capture times, pointers, quarantine and
  partial/empty scope; fail before publication on invalid metadata/evidence/target.
- Acceptance: historical normalization identity does not block a valid installed
  target; limited reader succeeds, originals/all SQL state stay unchanged, repeat
  and relocated replay match, no unavailable version is advertised as supported.
- Verify: focused real PostgreSQL/files/CLI tests, mutation, private offline pilot,
  full `just check`, `just audit`, then exact-head hosted jobs and owner review.
- Files AR2: `src/nima/dataops/replay.py`, `src/nima/dataops/archive.py`,
  `tests/test_archive_replay.py`, `tests/test_archive_replay_cli.py` (four files).
- [x] AR3: record observed local/private results: 56 new replay cases and 43
  verifier regressions pass; valid-JSON hash-guard mutation is rejected/restored.
  Existing private replay matches SQL normalized versions with unchanged 26-table
  data/counters/schema, originals, source guards and reader-report bytes; no HTTP
  request. Full `just check` passes 2,051 cases/93.06%, and `just audit` is clean.
  Private evidence and replay datasets remain outside Git.
- [x] Owner merged #126 at `ecb5a85`; exact-head run 44154596290 passes all
  three jobs. Continue explicit SQL promotion above.
- [ ] Follow-up: SQL promotion with distinct processing lineage and durable
  request/refresh version-policy handling; metadata remains after that boundary.

## Current extension: isolated restore drill

Owner requested continuation after merging #123 at `3e35bc4`; all three exact-head
jobs pass in run 44098176598. Preserve PV10 human checks and the metadata roadmap.
See the [runbook](../docs/operations/backup-restore.md) and [plan](plan.md).

- [x] RD1: freeze the bounded operator procedure, acceptance, private credential/
  evidence handling and exact owned-destination boundaries.
- [x] RD2: perform a native PostgreSQL 17 custom dump with a shared source snapshot;
  pair it with originals and an anchored manifest; restore to a fresh SCRAM local
  cluster with recreated scoped roles and an empty destination database.
- Acceptance: all application tables, sequence state and schema definitions agree;
  reader/schema checks, archive checks and identical relocated readout pass;
  missing/corrupt evidence and a bad dump fail; source data is unchanged and only
  the owned destination is stopped. No source request or schedule activation.
- Verify: native tool exits/private logs, catalog/full-row comparisons, real
  limited-reader CLI replay and deliberate failures. Record limitations rather
  than labelling the same-workspace checkpoint an off-host backup.
- Evidence: the [native drill](../docs/verification/restore-drill.md) passes on a
  fresh PostgreSQL 17.11 cluster. All 26 table contents, counters and schema checks
  agree; a native CHECK reparse and ten boundary cases prove one formatting-only
  difference. Effective daily role policies agree, actual role ownership is checked,
  wrong-password/write/immutable-row controls work and relocated readout bytes match.
  Missing/corrupt bodies and an incomplete native dump fail without publication or
  a partial failure-test schema. The source remains unchanged; only the owned
  destination is stopped. Private data/configuration/proof remain outside Git.
- [x] Resolve the source ownership follow-up in RPOL above: the private
  bootstrap's requested migration role was overridden by connector timeout options. Source
  schema was unchanged during the drill; the later RPOL connector/explicit private
  ownership repair resolves that pilot gap. Existing deployments still require
  their own bounded maintenance; no general shared-deployment role policy is claimed.
- [x] RD3: record the redacted observed result and full `just check`/`just audit`
  evidence. Full local gates pass 1,984 tests/93.03% and a clean advisory audit.
- [x] Owner merged #124 at `cae6fe2`; all three exact-head jobs pass in
  run 44127404558. Role handling continues in the current extension above.
- Files: `docs/operations/backup-restore.md`, `docs/verification/restore-drill.md`,
  `tasks/plan.md`, this file, `CAPABILITIES.md` (five documentation files).
- [ ] Next: archived normalizer replay/version handling, then structured metadata
  semantics and an isolated Greek model evaluation; no runtime model adoption.

## Current extension: bounded archive-integrity check

Owner-authorized on 2026-11-17 after #122 merged and delegated technical validation.
This continues source-ingestion/DataOps; PV10 human evidence/task checks remain open.
See the [contract](../docs/specs/SPEC-source-ingestion.md#dataops-increment-committed-page-archive-verification)
and [plan](plan.md). No new source requests or sector inference.

### AV1: Freeze the verifier contract

- [x] Record bounded committed-page scope, metadata/byte integrity, empty/partial
  outcomes, private read-only behavior, sector distinctions and existing limits.
- Acceptance: one explicit run/root, no source/repair/write path, separate
  restore/replay follow-ups; pending pilot tasks retained.
- Verify: review against existing SQL/page/archive and CLI contracts.
- Files: `docs/specs/SPEC-source-ingestion.md`, `tasks/plan.md`, this file (three files).

### AV2: Deliver the offline command

- [x] Implement `archive verify --run-id UUID --archive-dir /absolute/private/root`
  through public snapshot/recovery interfaces and minimal root routing.
- Acceptance: reader freezes bounded metadata in one closed SQL snapshot; all
  selected originals match hashes/lengths; empty/partial/relocated/error cases are
  explicit; no SQL/archive changes or source calls; fixed private-safe CLI results.
- Verify: `uv run --frozen pytest tests/test_archive_verify.py`; real PostgreSQL,
  private-file/limit/concurrency cases and hash mutation; `just check`, `just audit`
  and all three hosted jobs. Exercise existing pilot privately with no source I/O.
- Files: `src/nima/dataops/__init__.py`, `archive.py`, `src/nima/__main__.py`,
  `tests/test_archive_verify.py` (four files). Dependency: AV1.
- Evidence: 43 focused cases pass, including read-only transaction/closed connection,
  unchanged 26-table/file state, relocation, empty/partial/shared-body cases,
  metadata/page/byte limits, concurrent page commit and actual module execution.
  An initial hard-link rejection assumption was corrected to preserve existing
  supported shared-body archives; valid bytes are still hash/length checked.
  Removing the shared recovery hash guard makes the same-length corrupt-body
  regression fail; the original helper is restored with no committed change.
  Full local `just check` passes 1,984 cases/93.03%; `just audit` is clean.
  Existing private pilot and relocated-copy checks both pass with all 26 tables
  and original files unchanged and no source requests. Values/hashes stay private.
  Hosted exact-head checks accompany the PR and do not rerun that private pilot.
- [x] Owner reviewed/merged #123 at `3e35bc4`; all three exact-head jobs pass
  in run 44098176598. Continue with the isolated restore drill above.
- [ ] Refine/test SQL-plus-archive restore, then normalizer-version replay in
  separate increments; this command alone does not establish either capability.

## Current: product-first company and market intelligence

- [x] Record owner-approved direction in
  [ADR-0005](../docs/decisions/0005-market-intelligence-foundation.md): trusted data,
  shared semantics and analytics before persona workflows/AI.
- [x] Pause new RP3–RP9 feature work; retain code, tests, pins and required checks.
- [x] Verify #106/#107 are owner-merged and their three exact-head jobs pass
  (runs 43820296909 and 43822156321). This completes offline R-A only.
- [x] Owner approved the revised [capability map](../CAPABILITIES.md) through
  merged #108 at `9ff2eff` and the subsequent instruction to continue.
- [x] Draft the first [semantic-layer](../docs/specs/SPEC-semantic-layer.md) and
  [market-analytics](../docs/specs/SPEC-market-analytics.md) scopes: one metric definition and
  one private cited supplier–buyer readout, with hand-calculated acceptance data.
- [x] Owner merged provider/consumer scope #109 at `70e06d6` and requested
  continuation after the conceptual quality/pipeline review. All three exact-head
  jobs passed in run 43838968903; advance into implementation planning.
- [x] Draft the [pipeline validation contract](../docs/pipeline-quality-validation.md),
  proposed implementation plan and bounded tasks below.
- [x] Owner approved the implementation plan and merged #110 at `c964f4f`;
  exact-head CI passed in run 43857399789. Build PV1–PV3 to checkpoint V-A.
- [ ] Preserve reliability follow-ups as separate scoped work: effective branch
  rules (admin), refresh recovery/version handling, SQL/archive restore and roles.

The owner reviewed/merged PV1–PV3, completing V-A. Their stacked merges left PV2/PV3
on feature bases; #114 promotes the identical combined tree to main and passed all
three hosted jobs in run 43904754199. The owner merged #114–#116 into main at
`7b6397e` and requested continuation on 2026-11-17. PV4 and PV5 passed all three
exact-head jobs in runs 43912312467 and 43922239422, completing V-B. The owner
merged #117/#118 at `3dca868` and requested continuation on 2026-11-17. All three
exact-head jobs passed in runs 44038279239 and 44040022546, completing V-C.
The owner merged #119/#120 at `3cd4f77` and requested continuation on 2026-11-17.
All three exact-head PV9 jobs pass in run 44053781048, completing V-D review;
retain packaged SQL/Prefect and the isolated experiment. The owner merged #121
at `7c46d31` (three exact-head jobs passed in run 44081199621) and explicitly
requested pilot configuration/next steps. PV10 now has privately configured roles,
an authorized bounded real capture, readout/replay and automated source checks.
Human review and task observation remain pending. New PRs target main explicitly.
The initial proof is a cited captured-contract record count, not a persona UI,
financial concentration measure, live scrape or AI service. Old tasks below remain
incomplete where previously incomplete; they are not silently closed or discarded.

## Approved: readout and pipeline validation

Execute sequentially. Each task requires red→green focused tests, `just check`,
`just audit` and its exact-head hosted checks before proposing merge. Preserve the
existing 26-table schema, old behavior and all CI jobs. Focused PV1–PV3 commands
are executable on these review branches; the CLI/recovery batch is described below.

### PV1: Shared definition and known-answer SQL

- [x] Implement the frozen metric definition, pure eligibility/revision policy and
  one packaged reference SQL calculation, with the synthetic acceptance fixture.
- Acceptance: B1=3/B2=1/unassigned=1 and exact contributing IDs; independent
  hand-labelled checks cover cancellation, ties, duplicate ordinals, GR/EL,
  missing/invalid keys, earlier cutoff and A→B→A; provider imports no adapters.
- Verify: `uv run --frozen pytest tests/test_semantics.py`; permutation tests,
  disposable PostgreSQL calculation and wheel resource access; normal gates.
- Files: `src/nima/semantics/__init__.py`, `participation.py`, `participation.sql`;
  `tests/test_semantics.py`, `tests/fixtures/participation.json` (synthetic only).
- Scope: 5 files. Dependency: approved plan. No new metric certification claim.
- Evidence: #111 has 42 focused cases, 1,763 passing full-suite cases/92.81%,
  clean audit and an isolated wheel SQL-resource check. The supplier-before-revision
  mutation fails its known-answer test. All three hosted jobs passed in run
  43860790888 on `12c20f9`. Definition status remains draft until review.

### PV2: Bounded SELECT-only snapshot

- [x] Add the public DB entry point and one adapter freezing the validated SQL
  cohort/result in a read-only repeatable-read UTC transaction.
- Acceptance: legacy connection behavior preserved; schema/role/column grants,
  all page/projection grains and byte/count bounds checked; all 26 tables unchanged;
  immutable tuples remain stable across a concurrent new capture.
- Verify: `uv run --frozen pytest tests/test_analytics_snapshot.py tests/test_postgres.py`;
  actual limited/owner/inherited privilege cases and missing receipt/fact cases;
  no SQL connection remains open on return; normal gates.
- Files: `src/nima/storage/connection.py`, `postgres.py`;
  `src/nima/analytics/__init__.py`, `snapshot.py`; `tests/test_analytics_snapshot.py`.
- Scope: 5 files. Dependency: PV1. No migrations or broad private-import cleanup.
- Evidence: #112 has 31 new cases (36 with PostgreSQL regressions), including
  unchanged contents of all 26 tables, limited/inherited/public/column privilege
  cases, concurrent commits and exact-money checks. Local full gates pass
  1,794 cases/92.85%, with clean audit. Removing the column-write guard fails its
  regression. All three exact-head hosted jobs passed in push run 43864276361
  on `81938db` in #112.

### PV3: Closed private request

- [x] Decode the exact request fields, cutoff/key and explicit archive bindings.
- Acceptance: ≤16 KiB, 1–10 runs, duplicate/unknown keys and unsafe private-file
  cases rejected; canonical semantic request excludes archive locations; no side
  effects, source values or secrets in fixed error reasons.
- Verify: `uv run --frozen pytest tests/test_analytics_request.py`; actual files,
  size/type/UTC/key/binding boundaries and forbidden-side-effect checks; normal gates.
- Files: `src/nima/analytics/request.py`, `tests/test_analytics_request.py`.
- Scope: 2 files. Dependency: PV1; execute after PV2 in this batch.
- Evidence: 51 focused cases pass (94.30% request-module coverage), including
  otherwise-valid duplicate keys, canonical UTC/UUID/path rules, exact byte bounds,
  surrogate paths, symlinks/hardlinks/FIFO/changed files and forbidden-side-effect
  guards. Removing duplicate-key detection fails both valid-shape regressions.
  A real PostgreSQL integration drives synthetic originals through managed
  ingestion, projection, private request intake and the limited-role snapshot:
  four pages, eleven observations, ten versions and the expected total of five.
  Full local/hosted evidence accompanies this review branch; no source is contacted.

### Checkpoint V-A: Definition and input boundary reviewed

- [x] PV1–PV3 pass required local/hosted gates; owner reviews the exact metric
  answer, independent oracle, public DB seam and input/privilege bounds.

### PV4: Reconcile selected originals

- [x] Recover all selected pages and re-derive normalized records/projections
  against the frozen SQL tuples before any result can be published.
- Acceptance: include empty pages, superseded and nonmatching records; enforce
  32-page/object, 8 MiB/object and 64 MiB total ceilings; missing, changed or
  inconsistent originals/facts fail without repair/network/SQL writes.
- Verify: `uv run --frozen pytest tests/test_analytics_reconcile.py tests/test_graph_pilot_archive.py`;
  corrupt blob, mismatch, ordinal, empty-page and SQL-closed cases; normal gates.
- Files: `src/nima/analytics/reconcile.py`, `snapshot.py`;
  `tests/test_analytics_reconcile.py`, `test_analytics_snapshot.py`; `tasks/plan.md`.
- Scope: 5 files including delivery metadata. Dependency: V-A. Public offline
  snapshot revalidation reuses the existing fact/ordinal policy; no graph helper
  change, private cross-import or second schema validator was needed.
- Evidence: #115 passes local `just check` (1,875 cases/92.84%) and `just audit`.
  Verified all four known-answer pages, eleven observations and ten versions;
  original bytes defeat internally consistent forged SQL. Empty/nonmatching and
  after-cutoff pages, numeric-index typing, relocation and budgets are tested.
  Removing the record-hash check fails its mutation test. Exact-head hosted proof
  accompanies #115; it does not establish live source truth or full replay.

### PV5: Deterministic cited result

- [x] Compose the reconciled metric/check manifest and privately publish it using
  existing canonical no-clobber primitives.
- Acceptance: exact counts/record sets/cancellation/unknown diagnostics, all five
  outcomes, all selected evidence and definition/snapshot hashes; identical inputs
  and relocated identical archives yield identical ≤1 MiB bytes; failures publish none.
- Verify: `uv run --frozen pytest tests/test_market_analytics.py`; actual private
  outputs, unchanged-input retries and conflict/limit cases; normal gates.
- Files: `src/nima/analytics/result.py`, `export.py`; `tests/test_market_analytics.py`;
  `tasks/todo.md`, `CAPABILITIES.md` (delivery metadata).
- Scope: 5 files including metadata. Dependency: PV4. No durable release registry
  or certification. Programmatic path only; no CLI is claimed.
- Evidence: the known-answer report preserves all eleven observations, Greek
  labels, exact source money and raw/projection citations. Tests exercise all five
  outcomes, unchanged SQL/originals, closed SQL before verification/publication,
  relocated and physically deduplicated originals, retries, output conflicts,
  missing/corrupt/unprojected evidence and the actual 1 MiB result ceiling.
  All 16 focused cases pass. Full local `just check` passes 1,891 cases/92.93%,
  including build/security/secret/skill/lock checks; dependency audit is clean.
  A serializer mutation changing the count fails the independent known-answer
  assertion. Exact-head hosted verification accompanies the delivery PR;
  checkpoint V-B stays open for owner review before PV6.

### Checkpoint V-B: Complete programmatic readout reviewed

- [x] PV4–PV5 pass local/hosted gates; review raw-to-count attribution and unchanged
  SQL/originals, with previous artifacts retained on all observed failure paths.

### PV6: CLI readout

- [x] Delegate `analytics supplier-buyers --request ... --output-dir ...` to the
  verified programmatic path with the environment-only database configuration.
- Acceptance: root dispatcher holds no calculation logic; fixed summaries/errors,
  correct input/failure/interruption exit codes and no source/driver/path leakage.
- Verify: `uv run --frozen pytest tests/test_analytics_cli.py`; installed module
  invocation against disposable DB/private files; normal gates.
- Files: `src/nima/analytics/commands.py`, `src/nima/__main__.py`,
  `tests/test_analytics_cli.py`, `tasks/plan.md`, `CAPABILITIES.md`.
- Scope: 5 files including delivery metadata. Dependency: V-B.
- Evidence: #117 passes 37 focused CLI cases and 87 with root/graph regressions;
  all 37 also pass from the built wheel, including module subprocess execution.
  Local `just check` passes 1,928 cases/92.97% and dependency audit is clean.
  Removing the fixed parser error handler fails the private-value redaction tests.
  Exact-head hosted results accompany #117; this does not activate any source.

### PV7: End-to-end failure proof and operator instructions

- [x] Exercise the complete installed workflow under failures/interruption and
  document input, read-role grants, lineage, coverage and quality interpretation.
- Acceptance: introduced duplicate/missing receipt/corrupt source cases block
  publication; replay/actual process termination preserve prior results; tests
  assert no network route or application-table mutation. Parser rerun is not
  labelled full normalizer-version replay or provider completeness.
- Verify: `uv run --frozen pytest tests/test_market_analytics_failures.py tests/test_market_analytics_crash.py`;
  normal gates and unchanged old source-worker/orchestration hosted checks.
- Files: both named tests; `docs/analytics/supplier-buyers.md`,
  `docs/semantics/participation.md`, `tasks/todo.md` (delivery metadata).
- Scope: 5 files including metadata. Dependency: PV6. Reuse publication controls;
  no new egress harness or application/schema/dependency/CI change.
- Evidence: thirteen new real-PostgreSQL/private-file cases pass. Six introduced
  faults block publication and preserve old artifacts; a genuine duplicate
  observation is rejected by its SQL uniqueness constraint. Actual SIGKILL and
  Ctrl+C run before original verification and before/after the final atomic link,
  verify closed SQL and unchanged rows/originals, then replay the normal command
  to identical bytes without replacing old reports. Full local `just check`
  passes 1,941 cases/92.91%; dependency audit is clean. All 50 CLI/fault/crash
  cases also pass from the built wheel, including child processes. Removing the
  full stored-fact comparison fails the wrong-amount command regression even
  with valid hashes/receipt. Exact-head hosted proof accompanies the delivery
  PR. The runbook explicitly retains private
  SIGKILL temporary files; it does not claim automatic cleanup or full restore.

### Checkpoint V-C: Offline data-to-semantics proof reviewed

- [x] Owner reviews known-answer results, evidence trace, quality failures and
  installed CLI. This delivers one offline readout, not real-market/task validation.

### PV8: Isolated dbt candidate prerequisites

- [x] Prepare a separate Python 3.12 lock/environment for candidate Core 1.11.17 /
  Postgres adapter 1.11.0, with synthetic frozen seed inputs and private profile.
- Acceptance: resolve/pin exact packages; review resolved licenses/advisories and
  telemetry before running; test only a separately named disposable PG17 database.
  A failed prerequisite records a stop; application lock/CI/runtime remain unchanged.
- Verify: isolated `uv sync --frozen --project experiments/pipeline_dbt`, actual
  local connection after review, exact package inventory/lock hash and no source data.
- Files: `experiments/pipeline_dbt/pyproject.toml`, `uv.lock`,
  `seeds/input_observations.csv`, `seeds/input_mentions.csv`, `profiles.example.yml`.
- Scope: 5 files. Dependency: V-C. Synthetic seeds derive from the approved fixture.
- Evidence: #119 locks 55 external distributions, reviews all license metadata/
  texts and hash-checks compatible wheels. The applicable 54-package advisory
  audit is clean. Isolated install/import, actual PG17 connection and builder
  denial of application-schema access pass. Seeds derive from a verified managed
  synthetic capture; no original bytes or credentials enter Git. Local full
  gates pass 1,941 cases/92.97%, with clean application audit; all three exact-head
  hosted jobs pass in run 44048603575 on `51db5ec`.

### PV9: SQL/dbt parity and decision

- [x] Build the small observation/revision/count model graph and its quality tests,
  then compare exact record/evidence sets and diagnostics with the known-answer SQL.
- Acceptance: clean fixture matches; introduced bad grains/relationships fail;
  text identifiers/leading zeroes survive seed/model types and repeat build is
  stable; record versions/artifacts, setup effort, build/query time
  and diagnostic value. No production-performance or adopted-dependency claim.
- Verify: isolated `dbt seed`, `dbt build`, defect-case runs and private comparison
  report from the sealed input; exact invocation/profile/vars retained with results.
- Files: `experiments/pipeline_dbt/dbt_project.yml`,
  `models/observations.sql`, `selected_revisions.sql`, `counts.sql`, `properties.yml`.
- Scope: 5 files. Dependency: PV8. A new dependency/operating decision follows review.
- Evidence: two seeds, three models, 28 data tests; fifteen semantic/evidence
  scenarios match the full pure/reference-SQL payload and citation sets. Five
  injected data defects fail real dbt tests. Restored baseline hashes match.
  Fractional-time comparison caught a citation formatter defect, now fixed.
  A supplier-before-revision mutation returns seven instead of five while all
  28 generic tests pass; the independent oracle rejects it. Full application
  gates pass 1,941 cases/92.97%; no runtime dependency or schedule changes.
- [x] Record comparison and delivery status in a separate five-file documentation
  increment: this file, `tasks/plan.md`, `CAPABILITIES.md`,
  `docs/pipeline-quality-validation.md`, `docs/verification/pipeline-dbt.md`.
  Private proof retains exact commands/vars, compiled SQL and 153 target-artifact
  hashes, license evidence and synthetic originals. The
  [report](../docs/history/experiments/pipeline-dbt.md) recommends keeping SQL/Prefect;
  it distinguishes model tests from original-byte and whole-graph publication
  guarantees. Exact-head hosted checks accompany the delivery PR; hosted CI
  does not install or rerun dbt.

### Checkpoint V-D: Tool choice reviewed

- [x] Owner reviews measured benefit and license/security/compatibility evidence;
  retain plain SQL if the candidate stops or fails to justify adoption. No automatic
  conversion of the application pipeline or its semantic definitions.

### PV10: Protected real-data and analyst task pilot

- [ ] Use an authorized bounded captured cohort; sample grouping/revision/count
  and citation correctness; observe the owner or a consenting analyst's task.
- Acceptance: record checked cases, timing, errors, missing information and task
  usefulness, or explicit blocked status when protected originals/person are absent.
  No direct provider call or external contact is implied.
- Verify: installed readout, manual originals audit and observed task record;
  retain originals/results privately and publish only reviewed aggregate findings.
- Files: `docs/verification/market-readout.md` (reviewed result only).
- Scope: 1 file plus private evidence. Dependency: V-C; independent of dbt adoption.
- [x] Prepare the [readiness/result record](../docs/verification/market-readout.md)
  and audit/task protocol under the approved scope. Update this file, the plan,
  capability map and dbt report as delivery metadata (five files total).
- Initial evidence: repeated read-only inventory found no raw-body objects or
  managed-run manifests in the main and ingestion/archive companion checkouts' `data`/`work`
  locations; no application database environment was configured. That assessment
  prepared a private input handoff, frozen evidence audit, paired analyst task and
  blocked-result criteria. The following setup supersedes its missing-input state.
- [x] On the owner's explicit setup request, configure a separate private pilot
  database with NOLOGIN owner, scoped ingest/project/reader logins and exercised
  SCRAM/password/read-only checks. Prepare actual environment/request files and
  an offline launcher outside Git; do not request owner-created inputs again.
- [x] Execute the bounded KIMDIS proposal under the inherited managed-cloud proxy.
  Exclude incomplete discovery; admit the complete buyer-filtered cohort without
  quarantine. Preserve the declared convenience selection and all originals.
  The three-attempt allowance is exhausted; no new schedule or egress work starts.
- [x] Project/reconcile the entire admitted cohort, produce the private nonempty
  readout and reproduce identical bytes through the CLI with all 26 tables
  unchanged. Automated direct-JSON checks independently pass original fields,
  grouping, ordinals, cancellation and contribution/count sets. Retain source
  values, derived counts and evidence hashes privately for owner review.
- [x] Prepare the private guide and same-workspace table/archive/result checkpoint;
  verify its hashes. This is not a restore drill or off-host recovery proof.
- [ ] Complete human originals review and the consenting analyst task. Neither has
  been performed; automated checks are not human review or measured usefulness.
  Disclose the owner's prior exposure to aggregate answers and builder familiarity.
  PV10 stays open; the metric stays draft. The dbt comparison remains synthetic.

## Paused: approved remote boundary backlog

- [x] Verify owner-merged scope #104 at `f894800` and its three successful
  exact-head jobs on `b29eefe` (run 43810311235).
- [x] Record owner-accepted HTTPX/Playwright direction in
  [ADR-0004](../docs/decisions/0004-bounded-http-and-browser-acquisition.md), with
  the reviewed [comparison](../docs/research/acquisition-library-comparison.md).
- [x] Owner approved the plan in a later turn after #105 merged at `0536808`.

The [scope](../docs/sources/remote-worker-egress-pilot.md) and plan are approved.
RP1–RP2 are the current build batch; prepare/verify commands remain future interfaces.
Preserve all PE work below. Execute sequentially without delegation.

### RP1: Freeze closed remote configuration

- [x] Implement typed closed configuration and bounded private-file decoding.
- Acceptance: exact fields/types/version from the plan, all limits, duplicate keys,
  placeholder/source destinations, invalid authority/IP/subnet/pins/path/mode cases
  fail with fixed redacted errors; no DNS/network/Docker/SSH side effects.
- Verify: `uv run --frozen pytest tests/test_remote_config.py`; exact-boundary,
  adversarial private filesystem and forbidden-side-effect cases; normal gates.
- Files: `src/nima/egress/remote_config.py`, `tests/test_remote_config.py`.
- Scope: 2 files. Dependency: owner-approved plan.
- Local evidence: 110 focused cases; full `just check` passes 1,683 tests/92.62%,
  with clean lint/types/build/security and `just audit`. Removing the public-IP
  guard in memory fails three negative cases; disk source is unchanged. A real
  changed-file test and a descriptor-failure regression pass. Owner merged #106
  at `2e189f3`; all three hosted jobs pass in run 43820296909.

### RP2: Publish and reread an immutable private bundle

- [x] Prepare canonical no-clobber manifests and hash-bound bundle members.
- Acceptance: safe 0700/0600 objects, ≤1 MiB total, exact hash/byte reuse; changed,
  corrupt, extra/missing/conflicting/unsafe files fail; references only for
  credentials, no network/Docker calls or verification flag.
- Verify: `uv run --frozen pytest tests/test_remote_bundle.py tests/test_remote_config.py`;
  actual files, changed-file/symlink/mode/conflict/overflow tests; normal gates.
- Files: `src/nima/egress/remote_bundle.py`, `tests/test_remote_bundle.py`;
  `remote_config.py` only for an explicitly reviewed shared type.
- Scope: 2–3 files. Dependency: RP1.
- Local evidence: 38 bundle cases/148 combined configuration-bundle cases;
  full `just check` passes 1,721 tests/92.69% and `just audit` is clean.
  Actual SIGKILL leaves incomplete output unusable and unrepaired. Changed
  members/directories, conflicting bytes and coordinated manifest rewrites fail;
  readers require the caller-retained manifest pin. Removing that check in memory
  fails two regressions; source is unchanged. Owner merged #107 at `538de66`;
  all three hosted jobs pass in run 43822156321. Offline R-A is complete.

### Checkpoint R-A: Offline preparation reviewed

- [x] RP1–RP2 gates and exact-head hosted jobs pass; owner reviewed/merged both.
  New observer/policy work is paused by the later product-direction instruction.
  Preparation still establishes no remote egress.

### RP3: Define independent observer evidence

- [ ] Implement a controller-only authenticated, bounded, nonce-bound protocol.
- Acceptance: private control credentials, fixed endpoint paths/closed response
  schema and expected public IPv4/header/route/counter bindings; replay, malformed,
  oversized/missing observations fail; worker cannot access control credentials.
- Verify: `uv run --frozen pytest tests/test_remote_observer.py`; real controlled
  HTTP/TLS protocol cases, positive controls/redaction; normal gates.
- Files: `src/nima/egress/remote_observer.py`, `tests/test_remote_observer.py`.
- Scope: 2 files. Dependency: R-A; no public endpoint provisioning.

### RP4: Compile the separate remote network/gateway policy

- [ ] Bind approved authorities, public IPv4 answers, namespace ranges and pins.
- Acceptance: ≤8 public IPv4 answers/host, fixed 443 destination set, no mixed
  private answers/bypass route; changed resolution requires new policy; preserve
  fixture contracts; review immutable pins and remote asset differences explicitly.
- Verify: `uv run --frozen pytest tests/test_remote_policy.py tests/test_remote_gateway.py`;
  exact policy outputs and negative cases, normal gates.
- Files: `src/nima/egress/remote_policy.py`, `remote_gateway.py`;
  `tests/test_remote_policy.py`, `tests/test_remote_gateway.py`,
  `infra/source-worker-remote/pins.json`.
- Scope: 5 files. Dependency: RP3; pin/asset changes require explicit review.

### Checkpoint R-B: Remote evidence and policy reviewed

- [ ] Contracts, resource bounds and actual runtime pins reviewed/merged before
  any owned topology runs; no actual remote result is claimed.

### RP5: Create only the run-owned controlled runtime

- [ ] Add a separate remote stack with prerequisite checks and exact identities.
- Acceptance: existing images only; one bounded unprivileged/sandboxed worker,
  gateway-only external path, verified scoped helpers and identified local canaries;
  unsupported host, overlaps or missing images fail before workload; no broad teardown.
- Verify: `uv run --frozen pytest tests/test_remote_stack.py`; actual controlled
  Docker/namespace observations via explicit integration invocation; normal gates.
- Files: `src/nima/egress/remote_stack.py`, `tests/test_remote_stack.py`,
  `infra/compose.source-worker-remote.yml`.
- Scope: 3 files. Dependency: R-B; integration/asset invocation is reviewed explicitly.

### RP6: Prove independent cleanup after controller death

- [ ] Supervise controller lifetime and exact owned resource removal.
- Acceptance: pinned process/resource identities, independent SIGKILL recovery,
  reserved cleanup budget and unrelated resources unchanged; incomplete cleanup
  blocks success, with no prune or host-wide firewall mutation.
- Verify: `uv run --frozen pytest tests/test_remote_supervisor.py tests/test_remote_stack.py`;
  real process death and controlled Docker cleanup cases; normal gates.
- Files: `src/nima/egress/remote_supervisor.py`, `tests/test_remote_supervisor.py`;
  `remote_stack.py` only for the lifecycle boundary.
- Scope: 2–3 files. Dependency: RP5.

### Checkpoint R-C: Runtime and independent cleanup reviewed

- [ ] Actual controlled runtime/failure observations and cleanup reviewed/merged
  before case reconciliation; missing machine capability is a visible blocker.

### RP7: Reconcile the complete case set into a separate receipt

- [ ] Execute bounded cases and independently validate same-run evidence.
- Acceptance: closed required matrix ≤30 cases, one attempt each, ≤600 seconds
  including cleanup; nonempty controls, exact identity/policy/images and cleanup
  bind every result; separate local/remote receipt scope and hard-false source/
  identity/production flags; partial/forged/fixture receipts cannot pass.
- Verify: `uv run --frozen pytest tests/test_remote_run.py tests/test_remote_receipt.py`;
  independent expected rows, missing/duplicate/forbidden deliveries, time/byte
  bounds, tampering and fixture/local scope rejection; normal gates.
- Files: `src/nima/egress/remote_run.py`, `remote_receipt.py`;
  `tests/test_remote_run.py`, `tests/test_remote_receipt.py`.
- Scope: 4 files. Dependency: R-C.

### RP8: Expose commands and rehearse the complete kit

- [ ] Add module-level `prepare`/`verify` and the operator runbook.
- Acceptance: fixed redacted failures and 0/1/2/130 exits; canonical retry/reuse,
  no implicit image acquisition, same-run controls/cleanup and honest local scope;
  one material policy-bypass mutation fails before restoration; backup/restore recipe.
- Verify: `uv run --frozen pytest tests/test_remote_cli.py` plus full explicit
  controlled integration rehearsal; `just check`, `just audit`, all three hosted
  jobs and prose/link review. New integration/CI wiring needs its own reviewed
  invocation/change; fixture CI is not evidence the remote rehearsal ran.
- Files: `src/nima/egress/remote.py`, `tests/test_remote_cli.py`,
  `tests/remote_worker_integration.py`, `docs/verification/remote-worker-egress.md`.
- Scope: 4 files. Dependency: RP7; no root CLI, source collection or scheduler.

### Checkpoint R-D: Local technical kit reviewed

- [ ] Full rehearsal, mutation, quality/audit and exact-head hosted checks pass;
  owner reviews/merges. Actual remote acceptance remains input-gated.

### RP9: Run the actual controlled remote experiment

- [ ] Obtain declared host, independent controlled endpoints/observer credentials,
  stable egress, available reviewed images and private backup destination.
- [ ] Operator runs prepared commands; review every required case/control and
  exact owned cleanup on that host, plus private backup/restore evidence.
- Acceptance: only a complete same-run controlled remote receipt can assert
  `boundary_verified`; Publicity/company/production flags remain false.
- Verify: private receipts against independent endpoint and actual host evidence;
  missing inputs give an explicit blocked outcome, never inherited fixture success.
- Files: private config/bundle/receipts outside Git; no code/data commit required.
- Scope: controlled experiment. Dependency: R-D. **Blocked on operator inputs.**

## Preserved: approved evidence recovery and Publicity-first priority

The owner approved [scope #98](../docs/graph/company-evidence-pilot.md) and merged
it at `aef9f53`, then approved/merged plan #99 at `36bcb80`. Publicity is now the
primary acquisition development path and the API secondary. PE1 #103 is owner-merged
at `b3ee7eb`; all three exact-head hosted checks pass. The owner merged the
[remote egress scope](../docs/sources/remote-worker-egress-pilot.md) in #104;
its approved plan is above. PE2–PE3 remain authorized and key-independent.
The [source design](../docs/sources/gemi-publicity-fallback.md) records the proposed
remote topology/storage and unfinished extraction/import bridge. No live worker
is configured. All earlier incomplete tasks and history remain; execute sequentially.

- [x] Record owner approval of the evidence-recovery scope (#98).
- [x] Draft the bounded implementation plan and slices below.
- [x] Owner approval of this plan before PE1 (#99).

### PE1: Recover explicitly referenced original archive objects

- [x] Implement typed bounded read-only recovery (#103, owner-merged and verified).
- Acceptance: explicit root/reference binding and stable hash-verified bytes;
  missing/corrupt/unsafe files fail visibly without creation, repair, source-value
  errors or network access; exact 32-object/8 MiB-object/64 MiB-total bounds and
  safe descriptors hold on success, failure and interruption.
- Verify: `uv run --frozen pytest tests/test_graph_pilot_archive.py` plus normal gates.
- Files: `src/nima/graph/pilot_archive.py`, `tests/test_graph_pilot_archive.py`.
- Scope: 2 code/test files. Dependency: approved plan #99; independent of real company inputs.
- Local evidence: 65 new recovery cases; real private files/descriptor cleanup, alias
  and count/byte/source limits, replacement/hash failures and unchanged archives.
  Removing hash verification makes the corruption regression fail; exact source
  restored. Exact-head run 43760943303 passes 1,573 tests/92.47%, Compose and
  12 worker tests/654.53 s with one fresh full 28-case receipt. Live/privacy/
  production flags remain false; this completes PE1, not checkpoint A.

### PE2: Reconcile active-link evidence with the pinned snapshot

- [ ] Add evaluation rows/checks reusing existing normalizers, projection and graph.
- Acceptance: all complete-graph active edges, exact subject/version/role/event/
  revision, accepted-candidate and creating-anchor evidence are checked; expected
  keys/values/counts are independent of the helper under test; failures, source-
  consistent unknowns and missing human context stay distinct, with no automated
  verified-company outcome or zero-denominator pass.
- Verify: `uv run --frozen pytest tests/test_graph_pilot_checks.py tests/test_graph_pilot_archive.py`.
- Files: `src/nima/graph/pilot_checks.py`, `tests/test_graph_pilot_checks.py`;
  `src/nima/graph/pilot_archive.py` only if a shared recovery type needs adjustment.
- Scope: 2–3 files. Dependency: PE1.

### PE3: Rehearse the full offline audit and document actual operation

- [ ] Exercise the integrated SQL/archive workflow and write the operator recipe.
- Acceptance: real disposable SQL and labeled synthetic archives prove pinned
  hashes, closed SQL before reads, all 26 relations and archive bytes/metadata
  unchanged, private canonical retry/reuse, missing/tampered/zero-link failure and
  a meaningful mutation failure; recipe separates machine checks from human review.
- Verify: `uv run --frozen pytest tests/test_graph_pilot_checks.py tests/test_graph_pilot_archive.py tests/test_graph_export.py`;
  `just check`, `just audit`, Markdown links/prose and all three hosted jobs.
- Files: `tests/test_graph_pilot_checks.py`, `docs/verification/company-evidence-pilot.md`.
- Scope: 2 files. Dependency: PE2. PE1–PE3 target one five-file implementation PR;
  per-task commits/verification remain separate; split if the candidate is too large.

### Checkpoint A: Reviewed technical evaluation kit

- [ ] Full rehearsal/quality/audit/exact-head hosted checks pass and owner review/
  merge completes; implemented behavior and remaining empirical limits are explicit.

### PE4: Confirm real inputs and freeze a nonempty cohort

- [ ] Obtain the exact supported target identity, archives and accountable reviewer.
- Acceptance: private selection/inventory names one official entity, 1–10 exact
  contract versions, selection/window/omissions, report/import IDs and archive
  mappings, with source-supported active target participation and selected buyer;
  unavailable inputs yield `blocked_inputs`/`insufficient_evidence`, not success.
- Verify: private inventory against actual source files and supported SQL/report;
  confirm explicit preparation ends before the read-only audit baseline.
- Files: private `selection.json` and `inventory.json` outside Git; no source data
  commit, live request or new code. Scope: 2 private records.
- Dependency: checkpoint A and supplied real inputs. **Currently blocked on inputs.**

### Checkpoint B: Real cohort ready

- [ ] Exact identity/evidence availability, frozen cohort and reviewer confirmed;
  prerequisite gaps/conflicts recorded and no unsupported acceptance fabricated.

### PE5: Execute and review the real-company audit

- [ ] Recover all active-link evidence and complete the human audit matrix.
- Acceptance: exact pinned comparison/resolution/graph hashes and nonzero checked/
  required denominators; every required identity/provenance/edge/date/amount check
  complete, conflicts retained, reviewer/self-review disclosed; critical mismatch
  gives `failed_audit`, missing evidence gives `insufficient_evidence`, and only a
  fully supported nonempty cohort can be human-assessed `verified_selected_cohort`.
- Verify: existing helper/recipe on actual archives; independently trace each
  required matrix row and confirm database/archive state unchanged by the audit.
- Files: private graph/recovery/matrix/assessment records outside Git, published
  using existing private no-clobber helpers. Scope: bounded private case bundle.
- Dependency: checkpoint B; no human identity attestation is supplied by a model.

### PE6: Record the measured result and remaining product gate

- [ ] Reconcile delivery with actual technical and real-audit outcomes.
- Acceptance: distinguish shipped helpers, synthetic rehearsal, real audited counts
  and blocked/failed/verified outcome; preserve prior incomplete work/weights and
  all source privacy; public summary requires owner review and contains no case
  evidence or private review notes. Investigator usefulness remains unmeasured.
- Verify: exact candidates/checks, private audit receipt review, local links/prose
  and normal gates for any documentation candidate.
- Files: `docs/verification/company-evidence-pilot.md`, `tasks/plan.md`,
  `tasks/todo.md`; `docs/progress.md` only if a separately justified capability
  estimate changes (maximum 4 files, never credit PR/test/document counts).
- Scope: 3–4 documentation files. Dependency: PE5 or an explicitly recorded blocked
  PE4 outcome; a blocked handoff leaves PE4/PE5 and real-pilot success incomplete.

### Checkpoint C: Reviewed evidence handoff

- [ ] Owner reviews the recorded outcome and safe handoff. Real-pilot success is
  checked only for a supported nonempty audit; no automatic model/store/UI rollout.


The completed delivery sections below preserve their historical status wording;
the active scope and approval status are recorded above.

## GEMI live pilot (waiting for access)

- [x] Verify merged PR #18 and document official trial/access and offline pilot steps.
- [x] Configure a personal key after provider approval (received 2026-11-20; kept in untracked `.env`).
- [ ] Select 1–3 registry numbers and reconcile a credentialed small pilot.
  - 2026-11-20: first live profile (`1037501000`) collected, verified and normalized; see the pilot doc. Still open: more IDs, 404/429 cases, PostgreSQL import and the KIMDIS comparison.
  - Evidence: documented public test-key request returned HTTP 401 on 2026-11-10;
    no accepted live profile or personal-key compatibility is established.
  - Runbook: docs/verification/gemi-live-pilot.md; no key is needed for offline export checks.

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

## Repository controls and just

- [x] Verify merges and create dev from the then-current main.
- [x] Pin just and preserve every existing recipe/check in the migration.
- [x] Verify cleanup policy/leases and clean eligible old merged heads.
  - Seven matching remote heads deleted; local refs retained. Mutation caught;
    17 cleanup cases include real Git lease rejection after branch advancement.
- [x] Publish cleanup workflow and matching main/dev bootstrap PRs.
  - Verified: #30 merged to main at `0438f0f`; #31 merged to dev at `14ee45b`.
- [x] Run just check/audit and verify hosted checks for both targets.
  - Prior evidence: docs/verification/repository-controls.md; 486 tests, 92.53%
    coverage. Final-head hosted runs 43171630805/43171639562 passed before merge.
- [ ] Enforce GitHub-side main/dev rules and native deletion setting.
  - The owner approved public visibility on 2026-11-14, superseding the original
    private-hosting requirement. Last verification found no effective rules for
    main/dev; active `protect-main` targeted no branches. Historical settings
    writes returned integration HTTP 403. The prepared ruleset now names all
    three CI checks; no administration change is part of this specification PR.
- [x] Refresh the offline registry-comparison specification for review.
  - `docs/identity/registry-comparison.md` replaces the unpublished
    `docs/registry-comparison-spec` draft against main `127b3b8` and the current
    identity/GEMI storage contracts. This is documentation, not implementation.
- [x] Review/approve the comparison specification before implementation planning.
  - #65 merged at `48a0778`; the user requested continuation. Candidate `a7331a7`
    passed all three jobs in run 43629891127: 987 tests/91.58% coverage and
    12 real Docker tests/643.90 seconds. RC1–RC7's implementation plan now awaits review.

## Release planning: v1.0 product and agent handoff

- [x] Record baseline and distinguish package `0.0.1`, proposed milestones and
  implemented bounded capabilities; keep the previous readiness denominator.
- [x] Define v0.1/0.2/0.3/0.4/0.5/0.9/1.0 outcomes and R1–R10 acceptance.
- [x] Prepare fourteen dependency-linked agent work packages with exit evidence,
  boundaries, next-agent prompt and private-data/activation constraints.
- [x] Link existing specs/capability/architecture and correct stale first-slice
  "not implemented" headings without changing their metric/interface contracts.
- Before handoff: check links, docs-only scope, required local gates/audit and
  exact-head hosted evidence; record them in the roadmap PR.
- [ ] Owner scope review. No source budget, deployment, tag or release is activated.
- [ ] After verified #139 merge: scope V1-01 durable validation-result history;
  retain human PV10, certification, access/operations and paused egress work.
