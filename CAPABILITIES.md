# Nima capability map

## Company and market intelligence direction

The owner selected company/market intelligence on 2026-11-16: sectors,
competitors, public procurement and corporate changes. This supersedes the
investigation-led product framing, while preserving the evidence-first architecture.
The [direction ADR](docs/decisions/0005-market-intelligence-foundation.md) records
owner steering and the next product proof. The revised dependency map below is
**owner-approved through merged [#108](https://github.com/StamKavid/nima-ai/pull/108)**
and the subsequent instruction to continue with it on 2026-11-16.

Nima's mission is to help people understand Greek companies and markets through
traceable public data: reported commercial relationships, observed changes and
covered market activity. Journalist investigations are one future application.
Advertising performance, campaign attribution, private tax returns and bank-flow
access are outside this direction.

## Shared foundation and first analytics

| Stable module ID | Responsibility | Depends on |
|---|---|---|
| engineering-foundation | Reproducible development, checks, deployment boundaries and access controls | — |
| source-ingestion | Source contracts, raw revisions, observations, normalization, recoverable storage and lineage inputs | engineering-foundation |
| entity-resolution | Separate source occurrences, reported-identifier groupings and reviewed identity assertions; retain conflicts/history | source-ingestion |
| semantic-layer | Shared glossary, grains, keys, time/coverage rules, joins and versioned metric definitions with evidence mappings | source-ingestion, entity-resolution interfaces |
| market-analytics | Tested descriptive SQL readouts over eligible captured data; cited results, reproducibility and measured usefulness | semantic-layer |

These are capabilities within the existing modular monolith, not new services or
packages to create together. Dependencies identify required interfaces, not a demand
that every upstream capability be finished before a small downstream slice works.
Existing reported-party data can support explicitly labelled analytics without a
GEMI key, a verified-company claim or a graph database. Broader identity matching
still requires its own evidence and evaluation.

## Later consumers and extensions

| Stable module ID | Responsibility | Depends on |
|---|---|---|
| temporal-graph | Rebuildable dated relationships with source and identity/review status | entity-resolution; shared semantic definitions as adopted |
| risk-analytics | Eligible rules, peer comparisons and evaluated rankings; network methods only when graph inputs justify them | market-analytics; temporal-graph for graph-dependent methods |
| research-assistant | Evaluated evidence-cited explanations and bounded read-only questions over defined metrics/documents | semantic-layer, market-analytics; document corpus before retrieval |
| intelligence-activation | Saved analyses, exports, scheduled reports and deterministic change alerts; optional evaluated AI briefings | market-analytics; research-assistant only for AI features |
| investigator-workspace | Journalist/investigator case review and evidence export as one specialized persona workflow | shared data/semantics/analytics; reviewed identity/graph where needed |

Existing module IDs remain unchanged. The first bounded `semantic-layer` and
`market-analytics` slices are described below; `intelligence-activation` remains
an approved roadmap capability. The investigator module remains on the roadmap
but does not define the whole product or block other personas. Corporate/sector researchers, procurement
analysts and business-development
users may consume the same reviewed metric definitions through later scoped views.
No multi-user service or persona UI is authorized by this map.

The revised order is a thin vertical slice through data → semantics → analytics,
followed by observed user value, then broader sources and chosen consumer workflows.
Graphs are an optional branch; AI is not a prerequisite for analytics, alerts or
an eventual read-only interface. The previous linear graph → risk → AI → workspace
sequence remains history, not the dependency order for the first market readout.

## First proof and trust contract

First candidate: **Which public buyers repeatedly appear in captured KIMDIS
contract records reporting this selected supplier identifier?** Define
`captured_contract_record_count.v1`, its cohort/cutoff, eligible reported-identifier
keys, distinct-record/revision policy and cancellation/unknown-status disclosure.
This counts covered contract-publication records, not awards, paid spending,
market share or verified legal-company relationships.

Every result must identify source/stage, recorded observation cutoff, source
record/version, raw hash/pointer, transformation/metric version and eligibility/
coverage limitations. Latest-observed records cannot be labelled source-current
without a supported ordering rule. No single opaque trust score substitutes for
freshness, coverage, conflict and verification status. Metric certification is an
internal reviewed-definition status, not publisher or legal certification.

Start with this one metric and an evidence-linked readout. Current module scopes:

| Module | First bounded specification | Scope status |
|---|---|---|
| semantic-layer | [Metric, keys, revisions and lineage](SPEC-semantic-layer.md) | PV1 owner-reviewed provider; draft definition |
| market-analytics | [Private supplier–buyer readout](SPEC-market-analytics.md) | Owner-reviewed CLI; real readout/automated checks complete; human pilot pending |

The semantic layer is versioned code/SQL definitions plus a small glossary, not
an ontology generator, LLM dependency or separate metrics server. The two specifications share one
data-to-readout proof. After the conceptual quality/pipeline review, the owner
approved the [implementation plan](tasks/plan.md) through merged #110 and the
[validation contract](docs/pipeline-quality-validation.md). Real-data
reconciliation and an observed analyst task remain explicit product gates. No
product success is inferred from synthetic tests or PR counts.

PV1 supplies a pure policy and packaged PostgreSQL count over a known-answer
synthetic fixture. PV2 freezes bounded complete SQL cohorts under a SELECT-only
principal and re-derives facts; PV3 decodes explicit private selections without
source/SQL/archive access. The owner reviewed/merged these inputs, completing V-A;
#114 promotes their identical stacked tree into main. PV4 verifies every selected
original against frozen SQL; PV5 composes a deterministic private cited result
through a programmatic function. The report includes all selected observations,
revision decisions, covered query windows, five explicit outcomes and separate
byte/projection/identity/coverage limits. Identical relocated originals preserve
its bytes; invalid evidence fails without a result.

The owner merged #117/#118, completing V-C with all hosted checks passing.
`analytics supplier-buyers --request ... --output-dir ...` uses environment-only
database configuration and fixed private-safe summaries, with actual interruption/
replay tests and [operator instructions](docs/analytics/supplier-buyers.md).
The isolated [dbt comparison](docs/verification/pipeline-dbt.md) now passes fifteen
semantic/evidence scenarios and rejects five injected data defects. The report
recommends retaining packaged SQL/Prefect for the present metric. The owner merged
#119/#120, completing V-D review; dbt remains isolated. The protected
[real-data/task pilot](docs/verification/market-readout.md) now has an owner-requested
private database/configuration, bounded real KIMDIS capture and nonempty cited
readout. Complete original/projection reconciliation, independent automated
source-field checks and identical offline replay pass. Human source review and
task observation remain pending; no verified legal-company result or measured
usefulness is claimed. Source-derived results and credentials remain outside Git.
The capture's allowance is exhausted; no source schedule or paused egress work starts.
The definition remains draft; owner approval of code does not
silently certify a metric. See [tasks](tasks/todo.md) and the PRs for local versus
exact-head hosted evidence. No full semantic platform, live source-current view,
field-level lineage, financial concentration or product validation is claimed.

## Preserved implementation evidence

The notes below describe previously delivered source, identity and graph work.
They do not claim the new semantic/analytics/activation capabilities exist.

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

The `temporal-graph` module now has a bounded offline graph workflow through
owner-merged #91–#95 at `4a33a3e`, following approved scope #87/plan #90 and
checkpoints A–C. `graph snapshot` connects selected reported occurrences, exact
contract versions, unclassified reviewed handles, exact registry anchors and raw
evidence references. Optional focus stays inside selected history. One read-only
SQL snapshot, complete projection/byte revalidation and private deterministic
publication preserve unknowns, money/date semantics and prior artifacts.

The [graph operator/delivery record](docs/verification/investigation-graph.md)
documents unchanged 26-table state, concurrent-revoke snapshots, actual SIGKILL/
Ctrl+C publication recovery and full hosted gates. This is partial graph capability;
there is no installed graph store, global as-of/ownership model or investigator UI.
Real-company source recovery, sampled identity/edge/time checks and observed
investigator tasks remain the next product gate. Database adapters, eligible
signals/ML and cited AI remain separately scoped work.
