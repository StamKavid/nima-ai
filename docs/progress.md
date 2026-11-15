# Capability progress: 2026-11-15

Runtime baseline `4a33a3e` includes owner-merged graph G1–G5 (#91–#95), following
approved [scope #87](graph/investigation-pilot.md)/plan #90 and checkpoints A–C.
Local operators can export a bounded private graph connecting selected reported
parties, exact contracts, reviewed unclassified handles, registry anchors and
evidence. Focus stays inside selected history; old artifacts retain their original
decisions. G6 runbook #96 is owner-merged at `66712bd`; this G7 reconciliation awaits
the remaining owner checkpoint D. Documentation candidate checks are separate from
the already-merged runtime evidence.

The next product gate is a real-company evidence-recovery and investigator-task
pilot. The [database assessment](graph/database-candidates.md) balances technical
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
G6 #96 is owner-merged; it and this G7 record have their own candidate checks, with
G7's owner checkpoint D remaining. Neither documentation increment adds runtime
capability or assumes G7's future merge.

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
| Bounded graph technical workflow — implemented | Inspect selected participation, active/historical reviewed links and source references in a reproducible private artifact | G1–G6 merged; G7/checkpoint D and candidate verification remain; broader graph stays partial |
| Real-company investigation pilot — next | Recover evidence for a selected company/contracts/buyers cohort and validate useful investigator tasks | Authorized cohort, all displayed active-link source recovery, critical identity/edge/date/amount audit and observed manual-workflow comparison |
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
