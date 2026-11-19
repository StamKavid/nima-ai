# Capability progress: 2026-11-19

## V1-01 VH1 candidate: selected journal health

Owner-merged #141/#142 reach main `ef657aa`, including exact reviewed `2c9cbf6`.
[Selected-artifact journal health](operations/validation-history.md#health-of-an-explicitly-selected-artifacts-journal)
adds a bounded read-only snapshot and pure time/current-policy assessment. Newer
failures cannot be hidden by older late-completing passes; old corruption blocks
a verdict. Empty, pending, stale, tied, clock and old-policy states stay explicit.
Counts retain historical outcomes without treating them as current source truth.

Actual SQL/role/interleaved-snapshot tests and a latest-failure guard mutation pass;
the guard is restored. Existing output bytes and prior command behavior remain.
Final full gates/audit, wheel and exact-head hosted evidence are recorded with
delivery before handoff. No new schema, source access, private migration or
schedule. This inspects recorded attestations; it does not revalidate current
artifacts or certify a metric/source. Other dataset boundaries and live setup
remain separate work.

## Delivered V1-01 first boundary (#141/#142)

Owner merged #139/#140 at `73f8aa4` and requested continuation. The
[first history contract](../SPEC-validation-history.md) adds a separate append-only
journal and an explicit post-publication verifier/inspection command. Existing
publication remains read-only and byte-compatible; no source is acquired or
private pilot migrated. Invalid, blocked and cached attestations remain explicit.

Actual limited-role SQL, original/report preservation and process-kill/retry tests
pass. Removing byte-equivalence enforcement fails its artifact regression and is
restored. The provider and consumer are separate review checkpoints; full local
gates/audit, package resources and final-head hosted evidence are recorded with
delivery before handoff. Other dataset boundaries and health aggregation remain
later; a recorded pass does not certify the metric, source or identity.

## Current checkpoint C10 candidate: contract evolution in CI

Owner merged #138 into main at `9d29845`; reviewed head `4716e4b` and its exact
files are verified reachable. The [historical contract gate](semantics/contract-evolution.md)
compares committed ODCS catalogues by stable ID using immutable PR/push baselines.
It refuses unversioned/incompatible changes, removals, invalid metadata and
unavailable history. Renames retain identity; valid additions are counted.

Real disposable Git histories and actual CLI executions cover supported CI
events, dirty-tree bypass attempts and fixed diagnostics. The removal-policy
mutation loses the expected removal diagnostic and is detected by its regression;
the original source is restored. Only the quality checkout adds full history;
all existing jobs, pins, permissions and checks remain. Two scoped, explained
subprocess annotations require review; the security gate retains its policy.
Final local gates/audit and exact-head hosted results are recorded with delivery
before handoff. No runtime source policy, schema, dependency or activation changes.
Durable per-dataset validation history and scheduled monitoring remain later.

## Delivered checkpoint C9 (#138): ingestion contracts

The owner merged #137 at `9cd4c8a`; its exact contract files are verified on main.
The [KIMDIS ingestion extension](semantics/ingestion-contracts.md) adds draft
source-acceptance and normalized-record contracts alongside the output contract.
Neutral schema support does not import semantic, analytics or storage modules.
Both public normalizers check producer output; malformed source records retain
their original quarantine behavior. Normalizer defects stop the current page,
with raw bytes retained and no page/observation/outbox checkpoint advancement.
The version constant moved to the source boundary without changing its value.

Source/producer-hook mutations fail their actual regressions and are restored.
Final local, packaged pilot replay/readout and exact-head hosted results are
recorded in the delivery PR before handoff. No new source request, schema,
dependency, schedule, live deployment or validation-history registry is introduced.
Contract validity is not publisher accuracy, national coverage or certification.

## Current checkpoint C8 candidate: ODCS output contract

The owner continued the [data-contract extension](../SPEC-data-contracts.md).
The first [ODCS output contract](semantics/data-contracts.md) binds the existing
draft captured-record metric to a pinned official 3.2.0 schema, supported output
shape and reviewed semantic/SQL definition. Original reconciliation still precedes
publication; the new gate refuses shape, metric-payload and evidence-grain drift.
Existing successful report bytes remain unchanged. Semantic-binding and version
guard mutations fail their regressions and are restored; final local, packaged
pilot and exact-head hosted evidence is recorded in the delivery PR before handoff.

#136 is merged at `772c321`. Its separately authorized private health activation
passed source/permission/report preservation checks and reported stale capture
and low capacity. No source refresh or schedule was activated. The new contract
has no freshness SLA and does not certify that capture. Input/normalized dataset
contracts and automatic historical PR-base checks were subsequent increments
(C9/C10 above); durable validation history remains
later. One output contract does not complete the platform's contracts.

## Current checkpoint C4 candidate

Owner merged #130/#131; all three jobs passed on serving head `ec6402e` in
run 44290911542. C4 adds [explicit CPV references](semantics/cpv-reference.md)
and separate base-code annotations over selected SQL metadata snapshots.
The complete source metadata and its evidence remain unchanged; unknown reported
versions and unchecked check digits remain explicit. No supplier sector inference,
KAD crosswalk, model, source coverage or human-validation credit is claimed.

The bounded offline reader supports Greek/English from one explicitly selected
OP-TED SDK release with raw-hash selection and CC BY 4.0 attribution. Real-release
checks cover all 9,454 entries in each language. Actual command/SQL checks pass on
retained data. Private operational proof remains outside Git; no company-source
request or live schedule was added. Seventy-two new cases pass; the combined
`just check` passes 2,285 tests/93.27% and `just audit` is clean. Duplicate-code
and version-conflict guard mutations fail their regressions and are restored.
Exact-head hosted jobs are the handoff gate; owner review remains pending.

## Delivered checkpoint C3 (#130/#131)

Owner merged C2 through [#129](https://github.com/StamKavid/nima-ai/pull/129)
(`6051d41`); all three jobs passed on `0709027` in runs 44267217179 and
44267160859. The [C3 contract](../SPEC-source-ingestion.md#checkpoint-c3-explicitly-selected-sql-metadata-snapshots)
continues SQL metadata serving in two reviewable parts.

The first adds canonical preparation without file publication and additive 0009:
an immutable derived snapshot table, exact source foreign keys, actual diagnostic
counts and an occurrence view. UPDATE/DELETE/TRUNCATE are rejected. Prior migration
bodies remain unchanged. Source observation time and processing time stay distinct.
The dependent serving implementation adds explicit-hash promotion and read-only
SQL queries through CLI/library operations. SQL results are checked against the
shared pure selection policy, and filtered output keeps full capture quality
coverage. SQL-only reads attest the stored snapshot, not current archive integrity. No automatic pilot migration or schedule is activated.

The [official taxonomy assessment](semantics/taxonomy-releases.md) records separate
CPV and KAD release boundaries. Dictionary files/licences/parsers/matches are still
C4 work; reported versions and `taxonomy_validation: not_checked` are preserved.
Final combined local `just check`: 2,213 passed/93.05%, with a clean audit and
package SQL-resource smoke. Mutations, real process kills, concurrent retries,
restricted roles and source/selection refusal pass. Exact-head hosted results are
recorded with both delivery PRs before C3 handoff. Private proof stays outside
Git; human pilot validation remains open.

## Delivered checkpoint C2 (#129)

Owner merged C1 through [#128](https://github.com/StamKavid/nima-ai/pull/128)
(`bd7fec4`); all three exact-head jobs pass in PR run 44258789845 and branch run
44258739500. Continue the same structured metadata roadmap under the
[C2 contract](../SPEC-source-ingestion.md#checkpoint-c2-structured-market-metadata).

The merged increment adds [reported market metadata](semantics/market-metadata.md):
buyer function/legal classification/type and procurement CPV from verified KIMDIS
captures, and reported supplier KAD/version/type/dates from completed GEMI archives.
These describe different subjects and remain separate. Source paths, raw hashes,
original observation time, quality states and record status stay visible. Query
filters retain full-scope quality counts; unsupported source/dimension combinations
fail before I/O. Duplicate positions/observations remain occurrences.

This is a bounded read-only CLI/library snapshot, not SQL metadata indexing,
current-state metrics, taxonomy certification or inferred company sectors. It
reuses a public verified capture boundary and the existing strict source/GEMI
verifiers and canonical private publisher. Prior replay bytes remain compatible.
No new source request, schema/dependency/CI change or model is introduced.

Forty-six new cases and retained replay/promotion regressions pass. Dropping the
invalid-code eligibility guard fails its regression; it is restored. Full local
`just check` passes 2,182 tests/93.13%; `just audit` is clean. Hosted gate results
are recorded with the delivery PR before C2 handoff.
Private operational proof stays outside Git. Human pilot review and task
observation remain pending. Next: reviewed SQL metadata serving/dictionary scope,
then isolated Greek-model evaluation; no capability percentage is reweighted.

## Delivered checkpoint C1 (#128)

The owner-approved direction is company and market intelligence, following
[ADR-0005](decisions/0005-market-intelligence-foundation.md). The trusted data and
analytics foundation precedes persona workflows, sector inference and models.
The [C1 contract](../SPEC-source-ingestion.md#checkpoint-c1-operational-replay-and-saved-intent-compatibility)
continues owner-merged #127 (`ef2b438`) through a bounded build/review checkpoint.

The private pilot now runs reviewed migration 8. A fresh native snapshot backup,
paired originals/request/readout and anchored manifest were restored and checked
before the upgrade. Existing selected replays are promoted into derived SQL with
original capture time separate from processing time. Source rows, old definitions,
counters, source grants, archive bytes and the original readout are preserved,
except the intentional journal/derived-schema additions and explicit new grants.
The dedicated promoter uses scoped CONNECT/SCRAM and cannot write source tables;
the reader can read the derived view and cannot promote. No source request was
added and no live refresh schedule was activated. Private proof stays outside Git;
this is a single-operator local pilot, not off-host recovery or a shared service.

The merged C1 code decodes known v1 saved intents against their own hashes and
recorded values. New constructor defaults do not change an existing request or
refresh child. Historical processing pins remain visible; incompatible collection,
dispatch and policy activation fail before source/budget/RPC effects. Historical
pause remains available, and prepared manifests retain the actual request format.
Additive diagnostics distinguish saved enable state from executable compatibility.
Only supported v1 formats/ceilings are implemented; no silent upgrade or linked
replacement is claimed. Existing archive binding/resume restrictions remain.

Local verification: 43 new compatibility cases, 61 focused request/refresh cases,
and full `just check` at 2,136 passed/93.07%, with a clean audit. A removed pin guard
fails its regression before restoration. Exact-head hosted checks and owner merge
are recorded with #128. C1 does not close human evidence review or task
observation, select a runtime model, certify a metric or add source coverage.

Next: queryable buyer-function, procurement CPV and reported supplier KAD metadata,
keeping those concepts distinct, followed by an isolated Greek model evaluation.
Explicit intent replacement is separate work if a version transition needs it.

## Historical original-scope baseline (2026-11-15)

The remaining sections retain the earlier graph/investigator release rubric and
its evidence. Their 33% estimate is historical; it is not a refreshed company and
market intelligence completion estimate. PR/test counts do not add capability
credit, and no new overall percentage is invented at this checkpoint.

Runtime baseline `4a33a3e` includes owner-merged graph G1–G5 (#91–#95), following
approved [scope #87](graph/investigation-pilot.md)/plan #90 and checkpoints A–C.
Local operators can export a bounded private graph connecting selected reported
parties, exact contracts, reviewed unclassified handles, registry anchors and
evidence. Focus stays inside selected history; old artifacts retain their original
decisions. G6 #96 and G7 #97 are owner-merged through `686875d`, completing
checkpoint D; both pass all three exact-head hosted checks.

The next proposed scope is [real-company evidence recovery](graph/company-evidence-pilot.md),
followed separately by investigator-task validation. The [database assessment](graph/database-candidates.md) balances technical
performance, recovery/resources, query/tooling, community/support and licensing;
no store/adapter has been adopted or benchmarked. Evaluated models, cited-AI service
and the browser investigator workspace remain unimplemented.

## Estimate and method

The original scope defined capabilities/release gates, not numerical weights or
effort estimates. This is an approximate capability-tracking rubric, not elapsed
effort, time remaining, Greek-record coverage or production readiness. The
headline is **approximately 33% overall**, with a planning range of **31–36%**.
Keep the same scope weights; explain any future scope/weight change.

| Original capability | Scope weight | Estimated delivered | Weighted credit |
|---|---:|---:|---:|
| Engineering foundation | 10% | 90% | 9% |
| Source ingestion and data pipeline | 25% | 55% | 13.75% |
| Entity resolution | 15% | 50% | 7.5% |
| Temporal graph | 15% | 20% | 3% |
| Risk analytics and ML | 15% | 0% | 0% |
| Evidence-cited AI research | 10% | 0% | 0% |
| Investigator workspace | 10% | 0% | 0% |
| **Total** | **100%** | — | **33.25%, rounded to 33%** |

All scope weights and other capability estimates stay unchanged. Graph credit rises
from 0% to a conservative 20% for the working offline graph read/build/export/CLI:
one consistent validated SQL snapshot, deterministic evidence-linked versions and
occurrences, active-only reviewed links/focus and private reproducible publication.
That adds three weighted points (15% × 20%), rather than treating this precursor as
the full temporal-graph capability. Twenty percent is a planning estimate, not a
measured accuracy score or fraction of Greek companies represented. Legal validity,
broader corporate relationships, graph-store/query operations, real-company source
recovery and investigator usefulness remain unverified or unimplemented.

The prior reviewed-release baseline through #85/#86 was 30.25%, rounded to 30%
(28–33% range). Its entity-resolution credit rose from 30% to 50% for the complete
local review workflow: SQL-revalidated accept/reject/revoke, stable unclassified
handles, atomic/principal-bound retry, auditable history and private exports.
The earlier comparison baseline through #73 was 27.25%, rounded to 27% (25–30%).
Those identity/pipeline gains are not counted again here.

PR counts, test counts and documentation earn no additional credit. The final
runtime's 1,508 passing tests/92.37% coverage prove tested implementation behavior,
not identity
accuracy, investigator usefulness or product completion. Earlier milestones were
25.75% (rounded to 26%) on 2026-11-14 and approximately 22% on 2026-11-11. The
unchanged 55% ingestion estimate already includes refresh, Prefect, manual intake
and controlled-worker routing; those capabilities are not counted again.

## Working capabilities and their limits

**Data/evidence pipeline:** bounded KIMDIS contract collection, original archives,
exact normalization, PostgreSQL versions/observations/outbox, retries, leases,
resume and reported-participation projections. Self-hosted Apache 2.0 Prefect can
execute explicit workflows and bounded local daily refresh schedules. No live
refresh policy is activated and no production operation is claimed.

**Registry comparison and review:** GEMI has a bounded archive connector and offline
SQL import. Selected stored AFM-text agreements expose unknowns and contradictions.
Trusted local operators explicitly accept/reject/revoke one occurrence/candidate
pair, with no automatic propagation or legal identity/ownership inference. Stable
handles remain unclassified and duplicate selected handles are visible.

**Private investigation artifacts:** operator commands produce reproducible source
comparison, reviewed-resolution and bounded graph files. They retain provenance,
notes, history,
current selected revisions and original report context. Old receipts do not
reactivate old acceptance; old exports do not silently adopt later decisions.
`automatic_identity_links=0`, with reviewed accepted occurrences counted separately.
Attribution is `database_principal_only`, not verified human authentication.

**Bounded graph:** selected contract versions, reported occurrences, unclassified
reviewed handles, exact registry anchors and raw-evidence references form a private
deterministic JSON graph. Active acceptance supplies exact event/candidate/revision
references; unresolved and historical members remain. Optional focus adds a view
without collecting more data or replacing the full selection. Source dates stay
separate from observation/review time, validity stays unknown, and contract money
is never allocated to joint suppliers or summed into spending. SQL closes before
private no-clobber publication; later decisions preserve old artifacts. This is an
offline operator workflow, without scheduled graph refresh, a store or a browser UI.

**Engineering:** pinned skills/dependencies, verified StamKavid attribution,
quality/security/audit gates and actual database/publication process-kill tests.
Main/dev effective protection rules were empty at the last recorded inspection;
the proposed policy is not an enforcement claim. Public code hosting was approved
by the owner; source evidence, private reports and credentials remain outside Git.

The complete controlled-worker fixture boundary is delivered through E12: 12
Docker tests include the full 28-case HTTPX/Chromium matrix, independent controls,
runtime/topology evidence, actual packet-rule mutation/restoration and real failure/
cleanup checks. `just source-worker-check` validates one fresh full receipt before
CI upload. Deployment, internet egress and investigator IP protection remain
unverified; this is not a live Publicity scraper or automatically activated fallback.

**Remaining source work:** personal-key/live GEMI profile compatibility is unverified;
public test-key access returned 401. Manually captured Publicity files remain opaque
verified archive objects, not normalized company profiles. Diavgeia, TED, document
extraction and other procurement stages remain. Private invoices, tax filings,
unrestricted beneficial ownership and bank flows are not assumed available.
Near-real-time means processing updates when sources publish them; KIMDIS describes
daily refresh. No completion percentage represents coverage of all Greek companies.

## Delivery evidence

The owner merged graph #91–#95 through `4a33a3e`; exact candidates, runs, limits and
recovery evidence are in the [graph runbook](verification/investigation-graph.md).
Final runtime `e406c02` passes all three jobs in
[run 43739790204](https://github.com/StamKavid/nima-ai/actions/runs/43739790204):
1,508 tests/92.37%, build/security/audit, Compose and 12 Docker tests/833.86 s with
one fresh full 28-case receipt. The fixture's production/privacy flags remain false.
G6 #96 and G7 #97 are owner-merged and verified. G7 `24a9fa4` passes all three
jobs in run 43744988054: 1,508 tests/92.37%, Compose and 12 Docker tests/861.28 s
with one fresh full 28-case receipt. Production/privacy flags remain false.
Checkpoint D is complete; documentation adds no runtime capability credit.

The graph shares one validated SQL snapshot across contract facts and selected
review state; independent committed revokes during/after the read yield coherent
exports. Ordinary reads/retries leave all 26 source/workflow/review relations
unchanged; race cases account for their intentional ledger writer. Four real child
interruptions cover before/after publication with SIGKILL and Ctrl+C, demonstrate
closed SQL before interruption, then retry the normal CLI and preserve already
published bytes/mtime. Material active-link mutations fail before exact restoration.

Earlier reviewed-decision delivery remains part of this baseline:

The owner merged #76–#84 through `50b43be`; exact candidates, runs, boundaries and
recovery results are in the [reviewed-decision runbook](verification/reviewed-decisions.md).
Final implementation `fdf8289` passes all three jobs in
[run 43707453503](https://github.com/StamKavid/nima-ai/actions/runs/43707453503):
1,375 tests/92.13%, clean build/security/audit, Compose and 12 Docker tests/855.34 s,
with a full validated 28-case receipt and production/privacy flags false.

Independent connections exercise replay after a waiting head lock, competing
acceptances, global request collisions and entity/anchor creation conflicts.
Limited disposable logins exercise principal attribution and denied writes/replay.
Six SIGKILL cases cover accept/reject/revoke around real COMMIT before acknowledgment;
two more interrupt actual export publication and retry through normal CLI. Full
JSON snapshots preserve all 23 pre-existing source/projection/outbox/workflow/
migration relations. Mutation regressions fail before exact restoration and
normal gates. No production crash hook, skip or weakened gate is introduced.

Earlier runbooks record the executor's historical PostgreSQL setup failures.
Since graph G1, disposable loopback PostgreSQL 17.11 supports complete local SQL
checks; G5's local gate passes 1,508 tests/92.32%. A further runbook smoke verifies
the 16-table reader grants, denied UPDATE, identical CLI retry/cross-directory
bytes and unchanged 26-relation state on synthetic fixtures. Temporary roles,
database and files are removed. Supported Docker evidence remains hosted; no local
Docker or deployed egress success is claimed. These results do not establish
server/power-loss recovery,
production scale, empirical false-merge accuracy or reviewer ground truth.

Earlier comparison RC1–RC7 delivery remains recorded in
[registry comparison](verification/registry-comparison.md), including #73 candidate
`9e5e4ac` (1,106 tests/91.82%, 12 Docker tests/660.33 s). Earlier worker E1–E12
delivery and undeployed privacy limits remain in the
[worker record](verification/source-worker-egress.md). Election-accountability
work is outside this baseline.

## Product roadmap

| Milestone | Investigator outcome | Remaining gate |
|---|---|---|
| Private review release — delivered | Reproducible operator setup, review and evidence export | RI10/RI11 and owner checkpoint E completed in #85/#86 |
| Bounded graph technical workflow — implemented | Inspect selected participation, active/historical reviewed links and source references in a reproducible private artifact | G1–G7 and checkpoint D complete; real-company validation and broader graph remain |
| Real-company evidence recovery — proposed next | Trace a small selected company/contracts/buyers cohort back to original records | Approve the linked scope; exact entity and available archives; all active-link source recovery and critical identity/edge/date/amount audit |
| Investigator-task validation — follow-on | Establish whether the workflow helps investigators | Separate scope after evidence recovery; observed tasks and manual-workflow comparison |
| Broader source coverage | Follow decisions/documents and procurement lifecycle changes | Live GEMI profile pilot; Diavgeia/TED; native text/OCR with location accuracy; distinct stage/value semantics |
| Company/sector signals | Review concentration, repeated relationships, eligible amendments and other explainable patterns | Coverage/denominators, comparable CPV cohorts and legal/context controls; no silent scoring of missing data |
| Evaluated ML and graph features | Prioritize useful leads at a realistic analyst review budget | Credible reviewed tasks, temporal/group-aware evaluation and improvement over simple baselines |
| Evidence-cited AI research | Ask questions and inspect supporting/contradicting Greek records | Retrieval recall, claim/citation/arithmetic correctness, abstention, cost/privacy/license gates |
| Full investigator workspace | Save companies/cases, explore timelines/networks and monitor changes | User-task validation, multi-user auth/permissions, deployment/operations and verified egress |

Recommendation for the next product specification: an authorized private real-company
cohort using the implemented graph, with source-byte/pointer recovery and a review
matrix for every displayed active link. METLEN remains a candidate from the owner's
earlier request; no real-company retrieval, verified demonstration or company-data
availability is asserted by this release. Record selection, coverage, contradictions,
unknowns and checked-link numerator/denominator. Any critical identity, provenance,
date or amount error blocks describing that cohort as verified.

Then observe participation lookup, citation recovery and explanation of a changed/
revoked link against the manual workflow, recording completion, critical errors,
time, familiarity and failures. A thin read-only dossier/explorer is a candidate
for that separate scope; no user-task speedup or full workspace is implemented.
Broader sources and graph-store adapter/benchmarks remain separately scoped. Expand
the network and eligible signals after source checks and observed tasks support
the value hypothesis; a larger graph alone does not establish usefulness.

Graph communities, shared addresses and repeated awards are investigative leads,
not findings of collusion or tax evasion. Co-bidding analysis needs identified
bidders/outcomes; awarded suppliers or bidder counts alone are insufficient.
Sector/price comparisons need comparable units, scope and amount basis. CPV and
company KAD are separate classifications. The
[architecture/model strategy](architecture.md) retains these eligibility gates.

The GEMI key pilot can run when authorized access arrives. Stored reviewed evidence
already supports the bounded graph workflow; selecting and verifying a real cohort
is the next evidence/value gate. No production model/provider, graph store or public
service is selected by this documentation. Election-accountability work remains
outside this baseline.

## Release planning, not release delivery

The owner requested a [versioned v1.0 roadmap](roadmap/v1.0.md),
[release contract](../SPEC-release-v1.0.md) and
[agent handoff](roadmap/agent-handoff.md). These proposed gates add no source,
metric, insight or operating capability. Baseline main is `9d29845` (#138);
contract-evolution PR #139 is separately in progress. Package version stays
`0.0.1`; old readiness percentages retain their original denominator.
