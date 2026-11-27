# Release scorecard (v1.0 gates R1-R10)

Check the [release contract](../specs/SPEC-release-v1.0.md) against evidence, not
PR counts or test coverage. No gate is Passed and the package remains `0.0.1`.

**Snapshot: 2026-11-27 (Europe/Athens), main `65887b9` after #235.** Its reviewed
`ff2ea60` tree is identical; all three PR jobs passed in run 45963960528. Full
local proof: 5,375 / 95.50%; hosted: 5,375 / 95.46%. The additional
[retained real-cohort verdict](../verification/retained-real-cohort.md) is evidence
in this update; its publication is subject to this PR's review. Application code,
metric status and operational configuration are unchanged.

## Status meanings

Started means some evidence exists but substantial gate proof is missing. Partial
means working capability lacks required proof. Mostly means a named final item
remains. Passed requires every proof in the contract; none meets that bar yet.
Gate updates require evidence in a merged change. Source coverage, a data-fitness
outcome, internal metric certification and analyst usefulness are different claims.

## Gates and the next evidence

| Gate | Status | Evidence now | Missing proof / next action |
|---|---|---|---|
| R1 Acquisition | Partial | KIMDIS bounded collector and adapter; Diavgeia award/commitment adapters and [prior real pilots](../verification/diavgeia-r2-replay.md); GEMI profile/AFM paths and prior live proof | Reproducible current two-source cohort; retained positive Diavgeia pair is unavailable. Broader registry/company coverage remains unmeasured |
| R2 Evidence and lineage | Mostly | Immutable originals/versions, hash/pointer verification, archive replay, preserved 77-record pilot pack and current isolated SQL-plus-archive reproduction | Off-host restore and declared recovery objectives; lost originals for older runs cannot be inferred from their SQL hashes |
| R3 Quality and deduplication | Partial | Five per-use acceptance consumers, injected-failure proof, citation history #235; current raw reconciliation of all 77 records and measured limited/ready/limited/blocked outcomes | Positive two-source reconciliation and real missing/conflict/revision cases; do not turn foreign identifier exclusions into source-error claims |
| R4 DataOps | Partial | Legacy journal/health, bounded refresh recovery, diagnostics/access controls, citation acceptance journal; real legacy U1 record/retry/inspection on an owned restored copy | Seven observed daily cycles per activated feed, freshness/late-change evidence and operational recovery observation |
| R5 Four certified metrics | Partial | U1-U4 draft providers, reference SQL and readouts; current real U1-U3 arithmetic and U4 abstention control; [catalogue](../semantics/metric-catalogue.md) | All four remain draft: human definition review, real case reconciliation and recorded certification. No same-query numeric-change pair is retained |
| R6 Insights | Not started | Descriptive metrics and acceptance are prerequisites, not an implemented insight layer | Versioned insight contracts over reviewed metrics and explicit insufficient-evidence outcomes |
| R7 Serving | Partial | Bounded CLI/export for U1-U4 and exact source citations; evidence and private reproducible artifacts | Typed read-only query API and minimal local analyst view; actual task navigation |
| R8 Operations/security | Partial | Narrow role profiles, immutable/TRUNCATE guards, migrations/upgrade checks, private originals and secret scanning | Off-host restore, operational rollout review, effective branch-protection verification and signing decision. Last recorded branch-rule check is 2026-11-14, not a current protection claim |
| R9 Product/performance | Started | Automated retained-source audit and a separate nine-publication commercial archive check; limitations measured and no speedup claimed | Representative two-feed audit, declared performance envelope, three consenting analysts and manual baselines; current tasks are not observed |
| R10 Release reproducibility | Started | Wheel/sdist, isolated installed-wheel/native checks, migration and same-host restore proof, exact-head hosted CI | Versioned release manifest, clean-host end-to-end rehearsal, release upgrade/restore instructions and explicit owner release approval |

## Acceptance scenarios U1-U5

| Scenario | Current evidence |
|---|---|
| U1 repeat reported participation | Existing report reproduced byte for byte: nine selected publications, one buyer in a declared 77-record buyer/day cohort; fitness limited |
| U2 reported CPV/month | Existing report reproduced: 74 cells / 90 memberships across 77 publications; fitness ready for that use only |
| U3 buyer concentration | Existing report reproduced: 75 resolved / two unresolved publications; 57 supplier keys, five joint records, 80 participations; top share 9/75; fitness limited |
| U4 observed change | Readout and acceptance exist; current real negative-control pair correctly blocks on query mismatch/incomplete capture; numeric change is unvalidated |
| U5 evidence/export | Four private reports retain provenance and reproduce with relocated archives; independent raw checks pass; human retrieval/usefulness remains open |

Overlapping CPV cells and joint participations cannot be summed as distinct
contracts. The 77-record selection has one buyer by design and is not a national
market or competitor sample. All four metric definitions remain draft.

## Commercial-company case and sources

The retained METLEN archive has nine publication IDs, six buyer keys and six
award references; four publications share one award reference. All nine rows
match current normalization, with no unexplained discrepancy. It reports no
Diavgeia citation and its historical `vatNumber` query is outside the current
saved-query contract. No company SQL cohort, legal identity, revenue total or
positive cross-source relation was invented.

KIMDIS is reproducible for the retained scope. Prior Diavgeia award and commitment
pilots remain documented historical evidence; no Diavgeia capture manifest was
found in the bounded retained-workspace inventory. GEMI has prior profile/AFM pilot
proof; this checkpoint does not exercise registry access. CPV is reported
procurement classification, not exhaustive company-sector/KAD classification.
KAD, TED and data.gov.gr are not acquired by this checkpoint.

## Next actions

1. Review the private proposal for one supported METLEN buyer/day capture: at most
   two pages/HTTP requests, one attempt per page and 120 seconds. It is proposed,
   not executed; an explicitly approved protected route is required. The worker
   gets no database credentials; later reconstruction stays offline and owned.
2. Recover or separately arrange an approved positive two-source pair and complete
   same-query change pair. Do not expand source budgets or invent missing originals.
3. Complete human metric/source review and consenting analyst tasks. Prior answer
   exposure and builder familiarity must be disclosed; no speedup is measured.
4. Observe schedules/performance and off-host recovery before release acceptance.
   Keep other history adapters behind this real-data/product checkpoint.

## Historical foundation rubric — 2026-11-21

This historical score has **not** been re-scored for the 2026-11-27 checkpoint;
it is not current release completion. Use the gate evidence above.

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
