# Nima capability map

The user reaffirmed the original investigation mission and ingestion-first
architecture on 2026-11-08. This is a delivery sequence, not a claim that future
modules or model benchmarks are implemented.

| Module ID | Responsibility | Depends on |
|---|---|---|
| engineering-foundation | Skills, Git, constraints, CI, reproducible development | — |
| source-ingestion | Collect and preserve public-record revisions and documents | engineering-foundation |
| entity-resolution | Resolve companies and other parties with reviewed evidence | source-ingestion |
| temporal-graph | Project dated, evidence-backed relationships | entity-resolution |
| risk-analytics | Peer comparisons, graph motifs, rules, and evaluated ML rankings | temporal-graph |
| research-assistant | Hybrid retrieval and evidence-cited AI explanations | risk-analytics |
| investigator-workspace | Explore networks, review leads, and export case evidence | research-assistant |

Build order: engineering-foundation → source-ingestion → entity-resolution →
temporal-graph → risk-analytics → research-assistant → investigator-workspace.

`SPEC-source-ingestion.md` is the first application specification. Later modules
receive their own specs when their evidence and interface requirements are clear.
The model strategy, graph boundaries, and per-stage validation gates are in
`docs/architecture.md`. The election-accountability idea is outside this project.

`SPEC-entity-resolution.md` was approved through PR #15. Its first release implements
offline identifier assessment and source-scoped review reports. Registry
corroboration, identity decisions and evaluated matching follow later gates.

The proposed GEMI source contract is in `docs/sources/gemi.md`, supplementing the
existing `source-ingestion` module. Its first bounded profile-lookup release awaits
review; it adds no new module or implemented registry capability.
