# Release scorecard (v1.0 gates R1-R10)

Check the [release contract](../specs/SPEC-release-v1.0.md) against evidence, not
PR counts or test coverage. No gate is Passed and the package remains `0.0.1`.

**Snapshot: 2026-11-27 (Europe/Athens), main `7e0586e` after #237.** Its reviewed
`213e7b5` tree is identical; all three PR jobs passed in run 46008277708, hosted
5,375 / 95.49%. Application code is unchanged since the full local #235 gate:
5,375 / 95.50%. The [retained-cohort verdict](../verification/retained-real-cohort.md)
and [supported company-key capture](../verification/metlen-buyer-day-capture.md)
are delivered. The additional [same-query U4 pilot](../verification/same-query-change-pilot.md)
is evidence in this update, subject to this PR's review. Metric status and
operational configuration are unchanged; no release gate is upgraded.

## Status meanings

Started means some evidence exists but substantial gate proof is missing. Partial
means working capability lacks required proof. Mostly means a named final item
remains. Passed requires every proof in the contract; none meets that bar yet.
Gate updates require evidence in a merged change. Source coverage, a data-fitness
outcome, internal metric certification and analyst usefulness are different claims.

## Gates and the next evidence

| Gate | Status | Evidence now | Missing proof / next action |
|---|---|---|---|
| R1 Acquisition | Partial | KIMDIS bounded collector and adapter, approved 16-publication buyer/day capture including one company-key match; Diavgeia award/commitment adapters and [prior real pilots](../verification/diavgeia-r2-replay.md); GEMI profile/AFM paths and prior live proof | Reproducible current two-source cohort; retained positive Diavgeia pair is unavailable. Broader registry/company coverage and current freshness remain unmeasured |
| R2 Evidence and lineage | Mostly | Immutable originals/versions, hash/pointer verification, archive replay, preserved 77-record pilot pack and current isolated SQL-plus-archive reproduction | Off-host restore and declared recovery objectives; lost originals for older runs cannot be inferred from their SQL hashes |
| R3 Quality and deduplication | Partial | Five per-use acceptance consumers, injected-failure proof, citation history #235; retained and company-key raw reconciliation; real U4 pair with 32 occurrences/16 source IDs, nine ordering-only content changes | Positive two-source reconciliation and real value/missing/conflict cases; do not turn foreign identifier exclusions into source-error claims |
| R4 DataOps | Partial | Legacy journal/health, bounded refresh recovery, diagnostics/access controls, citation acceptance journal; real legacy U1 record/retry/inspection on an owned restored copy | Seven observed daily cycles per activated feed, freshness/late-change evidence and operational recovery observation |
| R5 Four certified metrics | Partial | U1-U4 draft providers, reference SQL and readouts; real U1-U3 arithmetic, U4 negative control and actual same-query 0/9/0/7 comparison reconciled; [catalogue](../semantics/metric-catalogue.md) | All four remain draft: human definition review, remaining case reconciliation and recorded certification. Content changes here are ordering diagnostics, not economic events |
| R6 Insights | Not started | Descriptive metrics and acceptance are prerequisites, not an implemented insight layer | Versioned insight contracts over reviewed metrics and explicit insufficient-evidence outcomes |
| R7 Serving | Partial | Bounded CLI/export for U1-U4 and exact source citations; evidence and private reproducible artifacts | Typed read-only query API and minimal local analyst view; actual task navigation |
| R8 Operations/security | Partial | Narrow role profiles, immutable/TRUNCATE guards, migrations/upgrade checks, private originals and secret scanning | Off-host restore, operational rollout review, effective branch-protection verification and signing decision. Last recorded branch-rule check is 2026-11-14, not a current protection claim |
| R9 Product/performance | Started | Automated retained-source audit, nine-publication commercial archive check and supported one-publication company-key SQL readout; limitations measured and no speedup claimed | Representative two-feed audit, declared performance envelope, three consenting analysts and manual baselines; current tasks are not observed |
| R10 Release reproducibility | Started | Wheel/sdist, isolated installed-wheel/native checks, migration and same-host restore proof, exact-head hosted CI | Versioned release manifest, clean-host end-to-end rehearsal, release upgrade/restore instructions and explicit owner release approval |

## Acceptance scenarios U1-U5

| Scenario | Current evidence |
|---|---|
| U1 repeat reported participation | Retained cohort: nine selected publications/one buyer in 77, limited. New buyer/day: one reported company-key publication/one buyer in 16, ready for that use |
| U2 reported CPV/month | Retained: 74 cells / 90 memberships / 77 publications, ready. New whole buyer/day: 32 cells / 74 memberships / 16 publications, ready |
| U3 buyer concentration | Retained: 75 resolved/two unresolved, top share 9/75, limited. New whole buyer/day: 16 resolved/zero unresolved, 16 supplier keys, six joint records, 24 participations, top share 4/16, ready |
| U4 observed change | Same-query pair: ready, 0 added / 9 changed / 0 missing / 7 unchanged, independently reconciled; all nine source-content differences are array order only under diagnostic. Earlier incomparable pair remains a negative control |
| U5 evidence/export | Retained report parity plus all four current reports/acceptance sidecars reproduced from native dump/relocated archives; independent raw checks pass; human retrieval/usefulness remains open |

Overlapping CPV cells and joint participations cannot be summed as distinct
contracts. The 77-record selection has one buyer by design and is not a national
market or competitor sample. All four metric definitions remain draft.

## Commercial-company case and sources

The retained METLEN archive has nine publication IDs, six buyer keys and six
award references; four publications share one award reference. All nine rows
match current normalization, with no unexplained discrepancy. It reports no
Diavgeia citation and its historical `vatNumber` query is outside the current
saved-query contract. The separate approved supported buyer/day capture now proves
a real company-key SQL path: one matching publication among 16. Its 160 raw field
comparisons pass and all three reports reproduce after isolated restore. That
company publication overlaps the earlier nine and has unchanged normalized fields;
do not add it as a tenth distinct publication. U2/U3 cover the whole buyer/day.
The response HTTP Date precedes observation; current freshness is unestablished.
No legal identity, revenue total or positive cross-source relation was inferred.

KIMDIS is reproducible for the retained scope. Prior Diavgeia award and commitment
pilots remain documented historical evidence; no Diavgeia capture manifest was
found in the bounded retained-workspace inventory. GEMI has prior profile/AFM pilot
proof; this checkpoint does not exercise registry access. CPV is reported
procurement classification, not exhaustive company-sector/KAD classification.
KAD, TED and data.gov.gr are not acquired by this checkpoint.

## Next actions

1. Review metric definitions and the actual supported company-key evidence with
   a human. Both approved managed-cloud proxy captures completed in one request
   each; unused slots stay unused. Automated data fitness is not certification.
2. Recover or separately arrange an approved positive two-source pair; four old
   KIMDIS reference candidates are retained but their Diavgeia originals are not.
   Broaden actual value/missing/conflict cases without inventing source changes.
   The first real same-query comparison is complete; do not extend its budget.
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
