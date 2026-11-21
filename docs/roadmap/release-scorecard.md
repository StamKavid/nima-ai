# Release scorecard (v1.0 gates R1-R10)

Where the project stands against the [v1.0 release contract](../specs/SPEC-release-v1.0.md), with the
evidence for each claim. It exists so progress is checked against gates and proof, not against a
count of merged pull requests; the contract itself says a percentage, a test count or a merged PR is
not a substitute. Nothing here is a release claim.

**Snapshot: 2026-11-21, main `689897e`.** Last fully green hosted run on main: run 44915536361
(`689897e`, all three jobs; it contains S4, S5, S6a, the hierarchy spec and this scorecard). The
package still declares `0.0.1`.

## How to read it

| Status | Meaning |
|---|---|
| Not started | No code or measurement toward the gate |
| Started | Some code or measurement; the gate's proof is far off |
| Partial | Working code with tests, but a required piece of the gate is missing |
| Mostly | The gate's own proof exists except a named item, usually an owner action |
| Passed | Every proof in the contract is recorded (none yet) |

Each row names the evidence (a document, test or merged change that can be opened) and the missing
piece. A status moves only when a merged change adds evidence, and the row is updated in that change.

## The gates

| Gate | Status | Evidence now | Still missing | Next evidence |
|---|---|---|---|---|
| R1 Acquisition: two validated source adapters | Started | KIMDIS collector (real, bounded, archive-first); the `SourceAdapter` boundary with two synthetic adapters (V1-04, #154-#159); GEMI profile collector proven live on one company, with two bugs found and fixed ([pilot record](../verification/gemi-live-pilot.md)); GEMI search parser (#172); Diavgeia acceptance dossier and link census ([dossier](../sources/diavgeia-acceptance.md)) | A second real feed: no Diavgeia adapter or cohort; GEMI collection beyond one company; search by tax number is a parser only | Owner chooses the Diavgeia pilot shape; adapter spec (V1-06) |
| R2 Evidence and lineage | Mostly | Original bytes archived before parsing, content hashes and JSON pointers, immutable SQL evidence, replay, archive verification, local restore drill; the first metric's result bytes pinned across a refactor (#175) | Off-host restore rehearsal (owner); archives of local runs 2 to 5 were lost with temporary containers, so real-data metadata snapshots cannot yet be rebuilt from them | A capture whose archive is preserved, then a reconciliation |
| R3 Quality and deduplication | Partial | Quarantine with reasons, exact decimal money, revision and tie handling, measured real formats and identifier classes ([measurements](../semantics/date-format-measurements.md)): 1,317 records, no placeholder tax IDs, about 1.2 percent irregular lengths | Versioned dataset acceptance checks (key uniqueness, referential integrity, expected totals): V1-08 | V1-08 once two feeds exist |
| R4 DataOps | Partial | Durable validation history and health (#141-#143), bounded refresh recovery (#144-#146), stage diagnostics and policy health (#147-#148), access audit (#149) | No observed schedules; the seven daily observed cycles per feed are not started | Schedules and an observation period (V1-13) |
| R5 Semantic layer: four certified metrics | Partial | Shared record selection and reported party keys (#175); measured time model (#174); metrics U1 (draft), U2 (#176), U3 (#178) and U4 (#180), each a pure provider plus reference SQL with full-result parity on PostgreSQL; hierarchy dimension specified (#177); the metric catalogue with published definition hashes and tests that refuse a silent promotion ([catalogue](../semantics/metric-catalogue.md)) | The owner's review of each definition (checklist in the catalogue); **no metric is reviewed or certified**, and certification needs the owner's real-data reconciliation plus the readout commands and preserved archive it depends on; the lifecycle references model (S6b) is in review | Owner review records; a preserved real capture to reconcile |
| R6 Insights | Not started | None | Insight contracts over certified metrics | V1-09 |
| R7 Serving: API, export and a minimal view | Started | One bounded readout command for the first metric; U2 and U3 exist as providers only | Readout commands for U2 and U3, a typed query API, export, a local view | V1-10, V1-11 |
| R8 Operations and security | Partial | Scoped runtime roles, TRUNCATE guards (#151), collector and projector profiles (#150, #152), private archives outside Git, secret scanning, a line-ending fix that made hosted and local checks comparable (#169) | Migration 0013 on the pilot database, off-host restore, effective branch protection, a commit-signing decision: all owner actions | Owner actions below |
| R9 Performance and product proof | Not started | The measurement census only | Workload envelope, observed analyst tasks, a private real-data audit | V1-12, V1-13 |
| R10 Release reproducibility | Not started | Hosted CI is green on main; the build produces a wheel containing the packaged SQL | Release manifest, clean-host install, upgrade and restore instructions, owner go or no-go | V1-14 |

## Acceptance scenarios U1-U5

| Scenario | State |
|---|---|
| U1 which buyers repeatedly appear with a supplier | Working bounded readout, human review pending |
| U2 captured activity by CPV and period | Provider and SQL reference; no readout; no CPV release or hierarchy yet |
| U3 buyer concentration of captured supplier participation | Provider and SQL reference; no readout |
| U4 change between two captures | Not started (S6) |
| U5 evidence and reproducible export | Evidence lists exist in every result; no export command for U2 and U3 |

## Sources

| Source | State |
|---|---|
| KIMDIS contracts | Live, bounded; 1,317 real records measured locally |
| Diavgeia decisions | Dossier decided, link census run: 4 of 1,317 records cite a decision, so the explicit key is sparse; no adapter |
| GEMI profiles | One company proven live; search by tax number specified, parser merged, collector not built |
| CPV 2008 | Reference reader merged; release selection waits for the hierarchy slice |
| KAD, TED, data.gov.gr | Not started (KAD optional for v1.0; TED and data.gov.gr are v1.1 or later) |

## Owner-only actions that block gates

1. Apply migration 0013 to the pilot database; run the off-host restore rehearsal (R2, R8).
2. Enable branch protection; decide commit signing (R8).
3. Choose the Diavgeia pilot shape (R1).
4. Approve any further live captures; preserve the archive of the next one (R2, R5).

## Foundation rubric, re-scored

The [older rubric](analytics-readiness.md) is a planning judgement of the single-operator analytics
foundation with fixed weights. It stood at about 65 out of 100 at #147 and was pending re-scoring.
This is the maintainer's re-score on the same weights; the owner may adjust any line.

| Capability | Weight | Was | Now | Why |
|---|---:|---:|---:|---|
| Source integration and coverage | 20 | 6 | 7 | GEMI profile path proven live for one company; still one feed at scale |
| Ingestion and versioned storage | 15 | 14 | 14 | Adapter boundary and source-neutral collection are architecture; first real revisions observed |
| Data quality and deduplication | 15 | 13 | 13 | Real formats measured; dataset acceptance checks still absent |
| Lineage and reproducibility | 10 | 9 | 9 | Unchanged |
| Semantic definitions and references | 15 | 9 | 11 | Shared selection, party keys, measured time model, three draft metrics with parity; none reviewed |
| Analytics delivery and user proof | 10 | 4 | 4 | No new delivery surface; no analyst task |
| DataOps and operations | 15 | 10 | 12 | Policy health, access audit, role profiles and TRUNCATE guards delivered; off-host recovery and schedules open |
| **Total** | **100** | **65** | **70** | Not v1.0 completion |

## Check it yourself

- Hosted CI on main: `gh run list --branch main` and read the jobs of the newest head, not a cancelled
  intermediate run.
- The first metric did not move: `uv run pytest tests/test_semantic_pins.py`.
- Metric parity: `uv run pytest tests/test_cpv_period.py tests/test_buyer_concentration.py tests/test_semantics.py`
  with `NIMA_TEST_DSN` pointing at a disposable PostgreSQL named `nima_test`.
- The full gate: `just check` and `just audit` (Linux or the project container).
- Real data: the read-only measurement census `uv run python -m scripts.semantic_census --top 20`
  and the link census `uv run python -m scripts.diavgeia_link_census --top 5` against a database you own.

## Keeping it honest

A merged change that adds evidence updates its row in the same change, with a link. A claim without
evidence is removed, not softened. The gate statuses change only when the contract's own proof for
that gate exists; rubric points may move on judgement but never a gate to Passed.
