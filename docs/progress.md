# Capability progress: 2026-11-11

Planning estimate baseline: CAPABILITIES.md and docs/architecture.md through
PRs #20–#21 at `b24c14a`. PRs #22–#26 now add local Prefect orchestration on main
at `e80e23f`, identical to tested `749b9ee`: 435 tests, 93.67% combined coverage,
hosted quality/Compose run 43094208540 passed. Post-merge main CI 43095249289
was queued at review. Coverage is not product completion.

## Estimate and method

The original plan defined capabilities and release gates, not numerical weights
or effort estimates. The table introduces an approximate planning rubric for the
original product scope. It is not a measured percentage of elapsed effort, source
records covered, production readiness or time remaining. Values are judgment
estimates; a sensible headline is **20–25% overall**, approximately 22% below.

| Original capability | Scope weight | Estimated delivered | Weighted credit |
|---|---:|---:|---:|
| Engineering foundation | 10% | 90% | 9% |
| Source ingestion and data pipeline | 25% | 40% | 10% |
| Entity resolution | 15% | 20% | 3% |
| Temporal graph | 15% | 0% | 0% |
| Risk analytics and ML | 15% | 0% | 0% |
| Evidence-cited AI research | 10% | 0% | 0% |
| Investigator workspace | 10% | 0% | 0% |
| **Total** | **100%** | — | **22%** |

Weights express product scope for tracking; they were not present in the initial
plan and are not promises about which capability will cost most. Keep this
baseline when reporting future progress, and explain scope/weight changes.

## Evidence for partial credit

Engineering: private repo, verified attribution, pinned skills/dependencies,
automated quality/security/audit checks and real crash tests. Branch-protection
enforcement remains unverified; production deployment/operations are not complete.

Ingestion: working KIMDIS contract collection, archives, exact normalization,
SQL history, retries, leases, recovery and local projections. GEMI's connector and
offline import are implemented against synthetic profiles; public test-key access
returned 401, and personal-key/profile compatibility is unverified. Diavgeia,
TED, additional procurement stages, document extraction, unattended orchestration,
source-refresh policies and production operations remain. This is not 40% of
Greek public data or 40% of a particular source's records.

Identity: conservative source-scoped identifier assessment and reproducible
candidate reports exist. Registry corroboration, reviewer decisions, reversible
accepted identities and empirical matching evaluation remain.

Graph, analytics, AI and workspace: architecture and candidate-model research
exist, but no production implementation or validated model earns completion
credit. There is no resolved company graph, fraud detector, RAG service or browser
investigator workspace yet. Election-accountability work is outside this baseline.

## Immediate direction

1. Review/merge the implemented bounded refresh increment; live activation remains separate.
2. Add controlled source connectors and registry comparison/reviewed identities.
3. Build temporal graph projection, evaluated analytics, evidence AI and the workspace.

No later component is blocked from design or synthetic testing by GEMI access;
live source compatibility and empirical evaluation still need real evidence.

The merged 2026-11-11 increment adds bounded self-hosted Prefect execution, with
no recurring polling or additional live-source validation. Retain the approximate
20–25% headline; the table is the original planning snapshot, not a recalculated
measurement. A workflow engine does not deliver graph, models or investigator features.
