# Capability progress: 2026-11-14

Planning estimate for CAPABILITIES.md and docs/architecture.md through main
`127b3b8`: bounded daily refresh, manual evidence intake and the complete E1–E12
controlled-worker delivery are merged. Final delivery candidate `39fd05b` passed
all three jobs in run 43627192150: 987 tests, 91.58% coverage and 12 real Docker
tests/624.58 seconds. The complete recipe validates one 28-case receipt before
upload; its implementation artifact was also downloaded and inspected. See the
[delivery record](verification/source-worker-egress.md). Coverage is not product
completion. The registry-comparison specification is approved through #65 at
`48a0778`; its implementation plan is drafted for review. No implemented matching
capability or progress credit is claimed for that planning work.

## Estimate and method

The original plan defined capabilities and release gates, not numerical weights
or effort estimates. The table introduces an approximate planning rubric for the
original product scope. It is not a measured percentage of elapsed effort, source
records covered, production readiness or time remaining. Values are judgment
estimates; a sensible headline is **25–30% overall**, approximately **26%** below.

| Original capability | Scope weight | Estimated delivered | Weighted credit |
|---|---:|---:|---:|
| Engineering foundation | 10% | 90% | 9% |
| Source ingestion and data pipeline | 25% | 55% | 13.75% |
| Entity resolution | 15% | 20% | 3% |
| Temporal graph | 15% | 0% | 0% |
| Risk analytics and ML | 15% | 0% | 0% |
| Evidence-cited AI research | 10% | 0% | 0% |
| Investigator workspace | 10% | 0% | 0% |
| **Total** | **100%** | — | **25.75%, rounded to 26%** |

Weights express product scope for tracking; they were not present in the initial
plan and are not promises about which capability will cost most. Keep this
baseline when reporting future progress, and explain scope/weight changes.

The previous 2026-11-11 snapshot estimated 22%. The weights are unchanged.
Ingestion credit rises from 40% to 55% for bounded daily refresh/coordinator state,
local Prefect schedules, manual evidence intake and verified closed-worker routing.
This is a judgment about delivered capability, not measured effort. Infrastructure
work earns credit inside its existing capability; every PR is not another product stage.
The E12 delivery record completes this worker increment within that existing
credit. Scope weights and capability estimates remain unchanged.

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
candidate reports exist. Registry corroboration, reviewer decisions, reversible
accepted identities and empirical matching evaluation remain.

Graph, analytics, AI and workspace: architecture and candidate-model research
exist, but no production implementation or validated model earns completion
credit. There is no resolved company graph, fraud detector, RAG service or browser
investigator workspace yet. Election-accountability work is outside this baseline.

## Immediate direction

1. Review the implementation plan/RC1–RC7 tasks for the approved
   [offline registry-comparison specification](identity/registry-comparison.md),
   then build its bounded evidence report after plan approval.
2. Add reviewed, reversible identity decisions with explicit supporting/conflicting evidence.
3. Build reproducible temporal graph projection with dated, inspectable evidence.
4. Add eligible company/sector statistics and explainable rules, then evaluated ML.
5. Add evidence retrieval/cited AI and the investigator workspace.

The GEMI personal-key pilot remains separate: validate live profiles when access
arrives. Offline comparison can be built and tested against synthetic imports
without credentials; live compatibility and empirical evaluation need real evidence.

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
