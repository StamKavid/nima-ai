# v1.0 agent work packages

Status: proposed work, **not automatically assigned or implemented**. Read the
[handoff](agent-handoff.md) before choosing a card. Milestone versions are in the
[product roadmap](v1.0.md); R/U references refer to the
[release contract](../../SPEC-release-v1.0.md). Existing approved work takes
precedence; first verify main and open PRs to avoid duplicate implementation.

Each card starts with a small scoped spec/plan and a failing acceptance test where
behavior changes. Deliver sequential focused PRs, not one PR per whole card.
Suggested areas below are ownership boundaries, not instructions to create all
listed packages or bypass existing APIs. Source activation is a separate operation.

| ID | Milestone / suggested role | Dependencies | Release proof |
|---|---|---|---|
| V1-01 | v0.1 / data-quality engineer | #138 main; #139 verified merged before depending on its gate | R3–R4 durable contract results |
| V1-02 | v0.1 / ingestion reliability engineer | Existing requests/refresh/replay contracts; independent of V1-01 implementation | R2–R4 version and recovery proof |
| V1-03 | v0.1 / operations engineer | Existing roles, restore and health contracts | R4/R8 observability, access and backup proof |
| V1-04 | v0.2 / ingestion architect | Stable V1-01 result interface; existing source guarantees | R1/R2 minimal reusable connector boundary |
| V1-05 | v0.2 / analytics engineer | V1-01 outputs; existing semantic provider and SQL metadata | R3/R5 reusable certified definitions |
| V1-06 | v0.3 / source engineer | V1-04; separately accepted official Diavgeia contract | R1 second feed |
| V1-07 | v0.3 / identity and lineage engineer | V1-05/06 | R2/R3/R5 source-explicit joins |
| V1-08 | v0.3 / data-quality engineer | V1-01/05/06/07 | R3 dataset acceptance and comparison eligibility |
| V1-09 | v0.4 / insights engineer | V1-05/07/08 | R5/R6 U1–U4 deterministic insights |
| V1-10 | v0.5 / serving engineer | V1-09 stable result contracts; restricted-role contract | R7 parameterized query API and exports |
| V1-11 | v0.5 / product interface engineer | V1-10 stable API; wireframes can be prepared earlier | R7 U1–U5 local read-only workflow |
| V1-12 | v0.9 / product validation lead | Existing PV10 can continue now; final tasks depend on V1-09/11 | R9 independent source and user proof |
| V1-13 | v0.9 / release reliability engineer | V1-02/03/08/10/11; approved host/source budgets | R4/R8/R9 observed operations and scale |
| V1-14 | v1.0 / release coordinator | V1-01–13 accepted, all R1–R9 passed | R10 reproducible release and owner go/no-go |

## V1-01 — durable validation history (next implementation candidate)

Read `SPEC-data-contracts.md`, `docs/semantics/data-contracts.md`, ingestion
contracts, current contract schema and DataOps health code. Keep historical Git
comparison separate from runtime dataset check history; GitHub CI logs are not a
per-dataset validation registry.

Freeze an append-only PostgreSQL result contract: stable dataset/observation or
derived-snapshot reference, contract ID/version/hash, validator version, distinct
validation time, pass/fail/blocked state, fixed check identifiers and bounded
counts. Separate a deterministic result identity from retry/attempt history; do
not put wall time into reproducible dataset identity. Failures before a valid
dataset reference use a separately scoped attempt record, not a broken foreign
key. Raw source values, secrets and arbitrary exception strings do not enter logs.

First slice: one existing publication boundary with real success/failure and
idempotent-retry evidence. Specify how artifact publication and SQL history can
recover when either succeeds alone; do not claim one transaction spans SQL/files.
Add migrations only after the exact event/ownership/retention contract is reviewed.
Likely area: `contracts/`, `dataops/`, SQL adapter/migrations and focused tests.
Exit: immutable prior results; correct repeated-attempt semantics; read-only
inspection/health integration; actual process-failure recovery and no new source
request. Preserve existing successful readout bytes or version a new interface.

## V1-02 — workflow evolution and recoverable refresh

Read saved request/policy/version rules, `archive replay`/`archive promote`, refresh
storage and runbooks. Replay/promotion already exist: do not rebuild them.
Reproduce which current requests/policies are invalidated by installed version or
default-limit changes, and which expired children cannot progress.

Specify stored-intent validation, supported execution versions, auditable policy
supersession and bounded child recovery. Preserve every original request/budget
and terminal attempt; recovery must not reset limits through new UUIDs. Exit:
normalizer-change and expired-child tests prove loading, refusal/recovery and
progress; original evidence/versions stay unchanged. Propose historical correction
sweeps only after measured source-date behavior; seven-day overlap is not CDC.
Area: orchestration/refresh and its storage adapter; keep schema changes isolated.

Current-profile implementation checkpoint: R1 (#144) bounded same-request recovery;
R2 (#145) immutable retirement; R3 explicit paused-successor/new-budget authority
([contract](../../SPEC-refresh-recovery.md#r3-explicit-successor-authorization--final-code-checkpoint)).
R3 ends this code checkpoint at verified review-ready delivery; owner merge and
live migration/activation remain distinct. After acceptance, advance to V1-03
rather than inventing another recovery increment. Future formats/correction
sweeps remain separately gated by actual source/version evidence.

## V1-03 — operating controls

First bounded increment: [O1 workflow stage diagnostics](../../SPEC-operating-controls.md).
V1-02 recovery code is owner-merged through #146 (`476f9be`). O1 stops at a
verified review-ready PR; the operational acceptance below remains separate.
O1 (#147), O2 selected-policy health (#148) and the O3 runtime-role audit (#149,
`fa4d772`) are owner-merged. In progress:
[O3e worker role profiles](../../SPEC-operating-controls.md#o3e-worker-role-profiles)
(`projector` delivered in #150, `collector` in #152; further duties paused until they go live). Migration 0013 (#151) added TRUNCATE
triggers to the 15 older evidence tables; applying it to a private database is an owner action. Runtime provisioning and off-host
operations stay separate.

Extend existing structured DataOps boundary events, selected-run health, scoped
roles and local restore runbook. Do not label those missing wholesale. Define
per-stage IDs, fixed failure reasons, source observation age versus processing
age, coverage gaps, blocked refresh children and operator attention states.
Choose log retention and protected operator configuration without adopting an
observability stack by default.

Exit: diagnose a failed run from its ID, enforce non-owner runtime writes and
immutable evidence, rehearse approved off-host SQL/blob backup restoration and
record effective branch-rule findings. Repository-admin action remains a stated
dependency if unavailable; an integration 403 is not success. No live notification,
infrastructure purchase or schedule is implied by the code PRs.

## V1-04 — source boundaries that support a second feed

Spec approved 2026-11-19: [SPEC-source-boundaries.md](../../SPEC-source-boundaries.md). S1 (import
graph check with a shrink-only baseline) is delivered in #154 and S2 (protocol and KIMDIS adapter) in #155,
S3 (engine on the protocol) in #156 and S4 (two synthetic adapters) in #157; S5 is gated
and needs source-neutral collection first: request, provenance and run options
([approved spec](../../SPEC-source-neutral-collection.md); N1 delivered in #158, N2 run options and
resume next).

Measure current imports/coupling before a narrow extraction. Separate pure source
normalization/types from transport/storage and publish necessary APIs. Preserve
archive-first, checkpoint, outbox, lease, quarantine and exact-money guarantees.
Prefer Python protocols and a modular monolith over a plugin platform or broker.
Exit: connector conformance tests and a second adapter without copying the full
stack or changing the shared engine for source fields; dependency tests prevent
new cycles. Existing crash/resume assertions still pass. Do not require a whole
package/CLI rewrite before a second small dataset can be tested.

## V1-05 — semantic model, party tier and metric catalogue

Extend `semantics/`, existing SQL metadata/projections and the glossary. Specify
current-as-observed record selection, typed date eligibility, contract lifecycle
references and party occurrences. A stable reported `(country, tax_id)` grouping
is rebuildable and explicitly distinct from a reviewed legal entity. Conflicts,
placeholders and rejection/override rules must prevent hidden false merges.

Define U1–U4 metric families with grain, formula, status/review event, version,
denominator, exclusions, source/stage/date/currency basis and evidence mapping.
Keep CPV release references; KAD runtime use stays behind its acceptance gate.
Exit: hand-calculated duplicate/revision/joint/unknown/conflict fixtures, SQL/pure
parity and versioned definitions reused by consumers. Retain source text alongside
parsed dates; unsupported source dates remain unknown. No arbitrary SQL or
generated ontology. Internal metric certification needs recorded review.

## V1-06 — Diavgeia source acceptance and connector

Inspect current official API/schema/access/reuse/rate documentation before code;
no dated API assumptions are authoritative. Freeze namespace/ADA identity,
revision/correction/cancellation semantics, date meaning, paging and original
attachments. Select a small supported decision class first. Reuse V1-04 and
archive all admitted responses before parsing. Area: source-specific adapter,
contract descriptors, projections and recorded-sample tests.

Exit: source conformance, strict/quarantine/retry/checkpoint tests, approved bounded
real cohort and reconstruction from originals. Unknown reuse/access or egress is
a blocked live pilot, not permission to fetch directly. Do not adopt a whole
document/RAG stack just because decisions link to PDFs.

## V1-07 — cross-source joins without invented identities

Specify exact supported ADA/contract references, direction, source stage and
evidence. A reference, reported identifier grouping and reviewed identity are
different relationship types. Keep disagreement, unmatched records and ambiguous
links inspectable; never count the same economic event by summing decision and
contract counts. Area: projections, identity policy, semantic join views/tests.
Exit: independently checked positive/negative/conflict examples, full supporting
provenance and reversible derived joins. Corporate ownership inference and fuzzy
name matching are separate evaluated features, not shortcuts here.

## V1-08 — dataset acceptance and comparability

Add versioned checks for key uniqueness, referential integrity, expected run/page
totals, quarantine/exclusions, reference membership and date/amount eligibility.
Record outcomes through V1-01. Declare which failures block a metric and which
remain a disclosed limitation; fail closed without plausible partial totals.
Exit: injected duplicate/missing/contradictory inputs produce precise outcomes;
two-source real-cohort reconciliation passes. Detect coverage changes before
claiming time trends or concentration shifts. Area: contract/quality policies,
DataOps result queries and real SQL tests. No single opaque trust score.

## V1-09 — deterministic insight layer

Freeze four insight result contracts supporting U1–U4, using only reviewed metric
definitions. Include snapshot/cutoff, baseline, observed change, reason/eligibility,
denominator, exclusions and evidence. Distinguish new observation, changed source
content and source-declared effective event; missing in a later capture is not
deletion. Use thresholds/peer groups only after eligibility is defined.
Exit: known answers, incomplete/incomparable-cohort abstention, original citations
and reproducible result bytes. No LLM arithmetic, fraud ranking or ML dependency.
Area: a small insights module over semantic/query interfaces, not the CLI.

## V1-10 — read-only serving

Specify a small typed parameterized query API, CLI/export adapters, pagination,
snapshot consistency, statement/row/output bounds and shared error vocabulary.
Select a web framework only in that bounded interface spec; PostgreSQL remains
authoritative. Preserve the existing bounded supplier–buyer command and its
evidence checks; a larger query surface needs its own tested envelope.
Exit: API/CLI/export result parity, real restricted-role SQL, malicious inputs,
interruption/retry, time/row limits and reproducible snapshots. Distinguish cached
validation attestation from verifying current archive bytes on every read.

## V1-11 — minimal local analysis view

Build only company/reported-party, buyer and CPV cohort views, metric definitions,
trust dimensions, insight detail and evidence/export navigation. Consume V1-10;
never reimplement metrics in browser code. Greek labels/identifiers and unknowns
must remain legible. Bound to the approved local operator environment; shared or
public exposure needs an explicit authentication/access specification.
Exit: actual U1/U2/U5 browser flows, loading/stale/empty/blocked states, keyboard
navigation and export parity. This is not a multi-user case-management suite.

## V1-12 — independent data and product validation

Finish existing PV10 human source checks/observed-task work; automated checks
are not a substitute. Extend to the release contract's stratified two-feed sample
and three consenting analysts when those surfaces exist. Pre-register tasks and
manual baseline; record builder familiarity and prior answer exposure.
Exit: R9 measurements, zero unexplained arithmetic/citation discrepancies and a
candid go/revise result. Keep originals/task records private; publish only reviewed
aggregate findings. Do not contact people without authorization or fabricate users.

## V1-13 — release-candidate operation and performance

Freeze the R9 workload/hardware envelope, then measure query plans, latency,
concurrency, replay throughput and resource capacity. Index/materialize only from
observed plans. Approve source budgets, protected deployment and schedules before
the seven-day observation. Exercise provider failure, restart, stale presentation,
restore, credential/role boundaries and rollback/upgrade procedure.
Exit: recorded target results or a reviewed scope change; a same-host copy does
not pass off-host recovery. No unlimited polling or silent weakening of bounds.

## V1-14 — release and handoff

Verify R1–R9 with evidence and exact main commits, clean-host installation and
upgrade/restore. Prepare version/changelog, supported-source/coverage matrix,
metric catalogue, known limits, operator runbook and reproducible artifact hashes.
Run all mandatory gates on the actual release candidate. Area: release docs and
minimal version/build metadata after scope is reviewed.
Exit: R10, independent operator reproduction and explicit owner go/no-go. Do not
tag, publish, merge or deploy from this backlog alone. Preserve failed/blocked
evidence rather than converting checklist completion into a release claim.
