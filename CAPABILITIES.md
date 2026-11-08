# Capability map

This map records the research direction accepted in the conversation. It is a
delivery sequence, not a claim that future modules are implemented or specified.

| Module ID | Responsibility | Depends on |
|---|---|---|
| engineering-foundation | Skills, Git, constraints, CI, reproducible development | — |
| source-ingestion | Collect and preserve public-record revisions and documents | engineering-foundation |
| entity-resolution | Resolve companies and other parties with reviewed evidence | source-ingestion |
| temporal-graph | Project dated, evidence-backed relationships | entity-resolution |
| risk-analytics | Sector comparisons and explainable investigation indicators | temporal-graph |
| investigator-workspace | Search, explore, annotate, and export evidence | risk-analytics |

Build order: engineering-foundation → source-ingestion → entity-resolution →
temporal-graph → risk-analytics → investigator-workspace.

`SPEC-source-ingestion.md` is the first application specification. Later modules
receive their own specs when their evidence and interface requirements are clear.
