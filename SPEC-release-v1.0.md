# Nima v1.0 release contract

Status: **proposed release scope**, prepared at the owner's request on 2026-11-18.
This is a product acceptance contract, not a claim that v1.0 exists. Existing
approved increments continue. New interfaces, metric meanings, sources, migrations
and operational activation receive their own bounded specifications and review.
The [roadmap](docs/roadmap/v1.0.md) orders delivery; the
[agent backlog](docs/roadmap/agent-backlog.md) defines implementable work packages.

## Product and scope

Help an analyst understand companies, buyers and sectors in covered Greek public
procurement records, with inspectable originals, reproducible calculations and
visible limitations. Initial users are the owner and a small consenting pilot
group of company/sector researchers and procurement analysts. Journalists reuse
the same foundation; no separate investigation pipeline is needed.

V1.0 is a single-operator, self-hosted analytics product for explicitly selected
cohorts. Propose KIMDIS contracts plus Diavgeia decisions as two independently
validated feeds. GEMI is an optional registry enrichment adapter until approved
access and live compatibility are verified. Registry/corporate-change coverage is
not silently promised by procurement data. National company coverage, verified
legal identity, paid-spend estimates, cartels and tax-evasion detection are outside
this release contract. Broader corporate intelligence continues after v1.0.

Daily bounded observation is the target, per approved source policy. The product
must label actual last observation, query windows and late-change limitations;
"real time" is not a release claim. A source outage must produce a stale/partial
state rather than an apparently complete empty result.

## User acceptance scenarios

| ID | Question or task | Required result |
|---|---|---|
| U1 | Which buyers repeatedly appear with this reported supplier? | Distinct eligible contract-record counts, buyer rows, revisions, exclusions and original citations |
| U2 | What procurement activity is captured for this CPV category and period? | Comparable covered counts, date basis, taxonomy release, unknown/unclassified bucket and coverage |
| U3 | How concentrated is a buyer's captured supplier participation? | Versioned count-based definition, eligible denominator, joint-supplier treatment and explicit unresolved share |
| U4 | What changed between two observed snapshots? | Added/changed/missing-from-later-capture categories, both evidence sets and observation times; no inferred deletion or legal event |
| U5 | What evidence explains this insight, and can I reproduce/export it? | Exact metric/input versions, contributing and excluded records, raw hash/location, coverage and repeatable export |

These are acceptance targets. U1 has a bounded implemented precursor; U2–U5 are
not claimed complete. Query/API/UI consumers must share the same semantic result,
not duplicate calculations. Missing data is unknown, never automatically zero.

## Required capabilities and acceptance

| Gate | v1.0 requirement | Proof required before release |
|---|---|---|
| R1 Acquisition | Two validated source adapters, explicit reuse/access rules, bounded budgets, reviewed source contracts | Recorded-sample conformance; approved real cohorts; no source rejection bypass; independent feed counts |
| R2 Evidence and lineage | Archive before parse; stable source namespace, revisions and observations; released metric-input mappings through normalization/projections to original bytes | Hash/pointer and transformation mapping checks; deterministic replay; old versions/observations/review decisions preserved |
| R3 Quality and deduplication | Shape, keys, completeness, referential integrity, exact amounts, duplicate/revision policy, quarantine and conflicts | Known-answer fixtures, injected defects and real-cohort reconciliation; no double counting across observations/stages/suppliers |
| R4 DataOps | Durable validation outcomes, stage logs, freshness/coverage diagnostics, bounded recovery and observed schedules | Forced failure/restart, blocked-child recovery, version-policy compatibility, scheduled-run history and stale-result handling |
| R5 Semantic layer | Shared grains/keys/joins/time/CPV definitions and at least four internally certified descriptive metrics supporting U1–U4 | Named versions, SQL/provider bindings, eligibility/denominator rules, independent hand calculations and recorded review |
| R6 Insights | Deterministic insights over certified metrics with reproducible comparisons and evidence | Known-answer/injected-defect cases, coverage-comparability checks, reason codes and abstention on insufficient data |
| R7 Serving | Documented parameterized read-only query API, CLI/export and minimal local read-only company/buyer/sector view | Shared-result parity, input/row/time bounds, actual task navigation to evidence, no user-supplied SQL |
| R8 Operations and security | Restricted runtime roles, private originals, approved egress, verified backups/restores and effective delivery controls | Non-owner access tests; off-host restore drill; retention/RPO/RTO decision; effective branch-rule check or explicit unresolved blocker |
| R9 Performance and product proof | Measured workload envelope, usable latency, checked source evidence and observed analyst tasks | Published synthetic methodology/results; private real-data audit; consenting task observations; candid limitations |
| R10 Release reproducibility | Installable pinned release, migration/upgrade/restore instructions, release notes and independent reproduction | Clean-host rehearsal, all mandatory CI jobs on release candidate, reviewed artifact manifest and explicit owner release approval |

All R1–R10 must pass; a percentage, test count or merged PR is not a substitute.
"Certified" means Nima's reviewed definition, not government or legal certification.
The existing first metric remains draft until its actual review is recorded.

## Semantic and insight rules

Keep source assertions, reported-identifier groups, reviewed identity facts and
derived insights distinct. CPV describes procurement; KAD describes reported
business activity. Missing KAD acceptance does not block a CPV-only release, but
the UI must not label a CPV cohort as an exhaustive company sector.

Use four initial metric families: eligible captured-record activity, repeated
buyer/supplier participation, count-based concentration and observed revision
change. Freeze each metric's exact formula and treatment of joint suppliers,
cancelled/unknown status, conflicting identifiers and incomplete dates in its own
contract before coding. U3 must not copy the full record into every supplier's
denominator without a declared shared/ambiguous category. Combined source displays
keep decision and contract counts separate; cross-references do not create extra
contracts. Monetary rankings require a separate eligible value/currency/tax/stage
definition and may remain unavailable in v1.0.

Every insight includes its metric/definition version, input snapshot/cutoff,
comparison cohort, included/excluded counts, source/observation time and supporting
evidence. Explanations are deterministic templates first. Low coverage or
incomparable cohorts produce "insufficient evidence" with a reason. No detector
or prose may claim wrongdoing or invent a numeric claim.

Expose trust dimensions separately: coverage, source freshness, identifier
conflicts, validation outcome, metric review state and evidence-verification
scope/time. A validated stored snapshot does not claim current archive verification
or complete publisher accuracy. For released metric inputs, document the source
field/JSON pointer, normalized field, projection/SQL expression and versioned
metric rule; a whole-record hash alone is not field-level transformation lineage.

## Proposed measurable release tests

These are proposed targets, not measured capability or an upstream SLA. Freeze
hardware, source volumes and thresholds in the performance work package before
implementation tuning. If measurements change a target, record the reason and
review the revised contract rather than silently lowering it.

- Exercise at least 100,000 synthetic normalized records, 10 concurrent bounded
  read queries, and ingestion replay at ten times the selected pilot's measured
  daily volume. Record indexes, `EXPLAIN`, CPU/RAM/disk and fixture generator seed.
- Target p95 under two seconds for bounded top-100-row served summaries on the
  declared release host; expensive reconciliation/export is an explicit bounded
  job with its own measured latency. No million-node graph performance is implied.
- Observe seven consecutive scheduled daily cycles for each activated release
  feed, including a rehearsed provider-failure/recovery scenario. Record late-change
  uncertainty and backfill policy; seven days alone do not prove complete change capture.
- Independently check a stratified sample of at least 50 source records across
  both feeds, all four metric families and empty/unknown/conflict cases. Require
  zero unexplained calculation/citation discrepancies before certification.
- Observe at least three consenting analysts completing U1/U2/U5, retaining task
  time, errors, missing information and a manual baseline. At least two must
  complete the tasks unaided and report a useful outcome; publish failure honestly
  and revise scope if that gate fails. Builder familiarity is disclosed.
- Decide RPO/RTO and retention from the approved observation cadence; prove them
  in an off-host restore rehearsal. No recovery SLA is invented before that proof.

## Boundaries and deferred scope

No new source requests, production deployment, outreach, spend, public hosting,
notifications, database administration, tags or release publication are authorized
by writing this contract. Develop with synthetic or already authorized captured
data until source-specific activation is approved. Retain IP-protection requirements.

Multi-user tenancy, paid commercial feeds, national coverage, formal ontology,
general text-to-SQL, graph database, vector store, LLM explanations, GNNs and
automated wrongdoing scoring are not v1.0 gates. They receive later release
experiments with evaluations, cost/latency constraints and failure criteria.
PostgreSQL remains authoritative; Prefect coordinates durable SQL-backed work.
The existing dbt experiment is evidence, not a dependency adoption decision.
