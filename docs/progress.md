# Capability progress: 2026-11-14

Planning estimate for CAPABILITIES.md and docs/architecture.md through main
`1c9ac26`: bounded daily refresh, manual evidence intake, the full controlled-worker
matrix and the real packet-rule mutation experiment are merged. Candidate
`32244f7` passed all three jobs in run 43615164185: 967 tests, 91.47% coverage
and seven real Docker tests/522.18 seconds. Coverage is not product completion.

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

1. Finish E10's real deadline/interruption, missing-capability and redaction
   experiments, then E11's CI interface and E12's delivery review/runbook.
2. Validate GEMI access when the key arrives; develop offline registry comparison
   and reviewed, reversible identities without waiting for credentials.
3. Build reproducible temporal graph projection with dated, inspectable evidence.
4. Add eligible company/sector statistics and explainable rules, then evaluated ML.
5. Add evidence retrieval/cited AI and the investigator workspace.

No later component is blocked from design or synthetic testing by GEMI access;
live source compatibility and empirical evaluation still need real evidence.

E9/checkpoint C passed the full 28-case HTTPX/Chromium matrix with independent
controls and actual runtime evidence. E10's first merged experiment proves real
forbidden delivery after a narrow packet-rule mutation, rejection by both policy
validation and the browser probe, exact restoration and a fresh full-matrix replay.
Remaining worker-failure checks and final integration/review are still pending.
Deployed IP protection and production readiness remain unverified.

The first product milestone is a company → procurement → buyer investigation
with dated corporate links, coverage limits and evidence export. Graph, ML and AI
receive completion credit only after implementation and their evaluation gates.
