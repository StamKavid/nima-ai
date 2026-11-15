# Capability progress: 2026-11-15

Planning estimate through main `c764dcb`: RC1–RC5 offline registry comparison is
merged, alongside the existing ingestion/refresh/manual-evidence and complete
E1–E12 controlled-worker capabilities. Final implementation candidate `8c46f14`
passes all three jobs in [run 43679268034](https://github.com/StamKavid/nima-ai/actions/runs/43679268034):
1,106 tests, 91.82% combined coverage, Compose and 12 real Docker tests/648.64 s,
with one validated full 28-case receipt. See the
[comparison operator/delivery record](verification/registry-comparison.md) and
[worker delivery record](verification/source-worker-egress.md).

RC6–RC7 documentation is the current review candidate; its human merge is still
pending. The implementation is an offline reported-identifier comparison, with
zero accepted identity links. Test coverage is not product completion, matching
accuracy or production readiness.

## Estimate and method

The original plan defined capabilities and release gates, not numerical weights
or effort estimates. The table introduces an approximate planning rubric for the
original product scope. It is not a measured percentage of elapsed effort, source
records covered, production readiness or time remaining. Values are judgment
estimates; a sensible headline is **25–30% overall**, approximately **27%** below.

| Original capability | Scope weight | Estimated delivered | Weighted credit |
|---|---:|---:|---:|
| Engineering foundation | 10% | 90% | 9% |
| Source ingestion and data pipeline | 25% | 55% | 13.75% |
| Entity resolution | 15% | 30% | 4.5% |
| Temporal graph | 15% | 0% | 0% |
| Risk analytics and ML | 15% | 0% | 0% |
| Evidence-cited AI research | 10% | 0% | 0% |
| Investigator workspace | 10% | 0% | 0% |
| **Total** | **100%** | — | **27.25%, rounded to 27%** |

Weights express product scope for tracking; they were not present in the initial
plan and are not promises about which capability will cost most. Keep this
baseline when reporting future progress, and explain scope/weight changes.

The 2026-11-14 baseline was 25.75%, rounded to 26%. Scope weights and all
other capability estimates are unchanged. Entity-resolution credit rises from
20% to 30% for the merged cross-source comparison: one consistent bounded
snapshot, explicit agreements/conflicts/unknowns, provenance-linked private reports
and verified CLI replay/redaction. That adds 1.5 weighted percentage points.
It does not credit verified identities, live matching quality or a resolved graph.
No credit is added for the number of PRs, test counts or this documentation work.

The earlier 2026-11-11 estimate was 22%; the unchanged 55% ingestion estimate
already includes bounded refresh, Prefect schedules, manual intake and verified
closed-worker routing. Those capabilities are not counted again here.

## Evidence for partial credit

Engineering: owner-approved public repository, verified attribution, pinned skills/dependencies,
automated quality/security/audit checks and real crash tests. Branch-protection
enforcement remains unverified: main/dev effective rules were empty at review.
Production deployment/operations are incomplete; evidence and credentials stay outside Git.

Ingestion: working KIMDIS contract collection, archives, exact normalization,
SQL history, retries, leases, recovery and local projections. GEMI's connector and
offline import are implemented against synthetic profiles; public test-key access
returned 401, and personal-key/profile compatibility is unverified. Diavgeia,
TED, additional procurement stages, document extraction and production operations
remain. Bounded refresh and local scheduling are implemented; no live policy is
activated. Manual Publicity intake verifies opaque evidence files without providing
a live scraper. This estimate is not a percentage of Greek data or a source's records.

Identity: conservative source-scoped identifier assessment and reproducible
candidate reports exist. The merged registry comparison adds selected stored
AFM-text agreements, contradictions, dated provenance and safe replay. It does
not verify issuer/authority or accept identities. Reviewer decisions, reversible
accepted identities and empirical matching evaluation remain.

Graph, analytics, AI and workspace: architecture and candidate-model research
exist, but no production implementation or validated model earns completion
credit. There is no resolved company graph, fraud detector, RAG service or browser
investigator workspace yet. Election-accountability work is outside this baseline.

## Immediate direction

1. Review/merge the RC6–RC7 operator runbook and delivery/progress documentation
   for the implemented [offline comparison](identity/registry-comparison.md).
2. Specify reviewed, reversible identity decisions with explicit supporting and
   conflicting evidence, audit history and evaluation before implementing writes.
3. Build reproducible temporal graph projection with dated, inspectable evidence.
4. Add eligible company/sector statistics and explainable rules, then evaluated ML.
5. Add evidence retrieval/cited AI and the investigator workspace.

The GEMI personal-key pilot remains separate: validate live profiles when access
arrives. Offline comparison is built and tested against synthetic imports without
credentials; live compatibility and empirical evaluation still need real evidence.

E9/checkpoint C passed the full 28-case HTTPX/Chromium matrix with independent
controls and actual runtime evidence. E10 additionally proves forbidden delivery
after a narrow packet-rule mutation, rejection, exact restoration and a fresh
full-matrix replay, plus real worker deadline, missing-capability and controller
signal failures with redaction/owned reclamation. E11/E12's complete recipe,
success-only validated receipt upload and measured runbook are merged. Deployed
IP protection and production readiness remain unverified.

The first product milestone is a company → procurement → buyer investigation
with dated corporate links, coverage limits and evidence export. Graph, ML and AI
receive completion credit only after implementation and their evaluation gates.
