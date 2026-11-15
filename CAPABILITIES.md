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
offline identifier assessment and source-scoped review reports. The merged
[offline registry comparison](docs/verification/registry-comparison.md) adds bounded,
evidence-linked reported-AFM agreements with zero automatic identity links.
The merged reviewed-decision workflow adds explicit reversible identity links;
empirical matching and false-merge evaluation remain later gates.

The approved GEMI source contract is in `docs/sources/gemi.md`, supplementing the
existing `source-ingestion` module. Archive-only bounded profile lookup and
[offline registry evidence import](docs/sources/gemi-persistence.md) are implemented.
Personal-key/live validation and source-aware downstream dispatch remain later
gates. Stored imports support offline reported-identifier comparison; they do not
establish verified corporate identity or issuer authority.

The [reviewed-decision contract](docs/identity/reviewed-decisions.md) is implemented
through #84 at `50b43be`, following approved scope #74/plan #75 and owner-reviewed
checkpoints A–D. Explicit local accept/reject/revoke commands keep immutable
history, stable unclassified handles and private resolution snapshots. SQL source
revalidation, exact UUID/principal replay, races, limited grants and actual
COMMIT/publication interruption have measured tests. See the
[operator/delivery record](docs/verification/reviewed-decisions.md).

Attribution is `database_principal_only`; accepted review does not certify legal
identity or source authority. Coverage stays report context, automatic links stay
zero, and live GEMI compatibility/consolidation/matching evaluation remain gates.
The next implementation scope is a reproducible temporal graph and bounded
company → procurement → buyer investigation pilot, with its own spec/evaluation.
