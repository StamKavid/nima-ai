# Capability progress: 2026-11-26

## Current project and chapter position

**Update 2026-11-26 (Europe/Athens).** #225 is delivered on main `e6c869d`:
the verified citation-acceptance consumer follows the V1-07 two-source readout and
V1-08 pure policy. Reviewed `fd35041` is reachable with an identical tree; all
three exact-head PR jobs passed in run 45719893571. Proof: 4,598 tests / 95.12%
overall, 135 focused cases / 100% new-module line/branch, 22 rejected mutations,
clean audit and isolated-wheel/native proof.
[Delivery record](verification/citation-acceptance-readout.md).

#227 now contains the approved U1 acceptance consumer, incorporating #226's
reviewed request-path correction. C1–C3 were approved on 2026-11-26. Its candidate
has 276 focused cases, 100% U1/shared-file/CLI line and branch coverage and 22
rejected mutations; full local/package/audit and exact-head hosted results are
recorded on that PR. It measures eleven counters, preserves provider status and
hash-binds the private supplier selection without copying its tax number.
[Proof](verification/participation-acceptance-readout.md). Neither PR is assumed
merged. U2–U4 consumers and durable history remain open.

Actual four-positive reconciliation, metric review/certification and investigator
task proof remain pending. No new source acquisition, release or rescore of the
historical rubric below follows from this checkpoint.
Since #161: the Diavgeia award pilot and its Β.1.3 commitment pilot
(collect, replay, three live runs; [records](verification/diavgeia-c2-commitments.md)), source-aware archive replay
and promotion, and the GEMI AFM lookup end to end (search collector, offline verification, SQL import,
comparison policy v3, live pilot; [records](verification/gemi-afm-l6.md)). The rubric score and the capability rows
below were **not** re-scored for these and describe 2026-11-19; the active work list is `tasks/todo.md`, and the
owner-side open items are in the last section of this page. What follows is the 2026-11-19 position, kept as written.

Merged main was `4c6d41f` after #161 (Diavgis prior art and the measurement to run first, docs only),
including exact `5f74cc4`. The Diavgeia dossier itself is #160; V1-04 is delivered through #159.
The unchanged-weight [analytics-foundation rubric](roadmap/analytics-readiness.md)
was **approximately 65/100** when last scored at merged #147 (up from 61: saved-intent/
recovery evolution, contract history and diagnostics earned four points). It has
**not** been re-scored for the later O2 and O3 deliveries; that judgement is pending
and must keep the same weights. Sources, semantic review and
human task proof earned no new credit. This is not whole-v1.0 completion or
coverage of Greek companies. The old 33% investigator/graph estimate below is a
historical assessment of different scope.

Current chapter: **v0.1 dependable foundation / V1-03 operating controls**.
Contract evolution/first durable validation boundary, current-profile recovery
O1 diagnostics, O2 selected-policy health (#148), the O3 runtime-role audit (#149) and
the O3e-1 `projector` profile (#150) are delivered. O3e adds worker role profiles proven
by running the real worker; `projector` (#150) and `collector` (#152) are delivered. Migration 0013 (#151, O3f) adds
TRUNCATE guards to the 15 older evidence tables; it is not yet applied to any private
database.
Scoped runtime/operator setup, approved off-host restore and effective branch
controls remain open. No milestone tag or v1.0 release is created.

| Chapter | Current product position | Main remaining acceptance |
|---|---|---|
| v0.1 Foundation | In progress; bounded ingestion/evidence/contracts/recovery and diagnostics work | Full operations proof and deployment configuration |
| v0.2 Shared semantics | One draft metric and CPV reference precursor | Reusable source/provider boundaries, shared semantic registry and reviewed definitions |
| v0.3 Two-source data | One KIMDIS pilot feed | Diavgeia connector and cross-source quality/lineage |
| v0.4 Insights | Planned metric families | Comparable activity, repeat participation, concentration and observed changes |
| v0.5 Serving/workspace | Cited CLI precursor | Shared read-only API/exports and a minimal local interface |
| v0.9 Release proof | Pending | Real source/analyst checks, observed daily cycles, off-host recovery and measured workload |
| v1.0 Release | Not released; package remains 0.0.1 | All R1–R10 acceptance and explicit owner go/no-go |

Sources: KIMDIS contracts has the bounded real end-to-end pilot. GEMI API code
awaits key/live compatibility; Publicity is manual/fixture-backed with no deployed
gateway. CPV is an offline reference, not a second company feed. Diavgeia/TED notice
connectors and a runtime KAD dictionary remain pending. No live daily schedule is
claimed. See the [version roadmap](roadmap/v1.0.md) and fixed rubric for details.

## V1-04: source boundaries for a second feed (S1-S4 delivered, S5 gated)

The owner approved [the spec](specs/SPEC-source-boundaries.md). Slice S1 (#154, merged at
`d3b0e90`, hosted run 44606219260) added an import-graph check with a committed shrink-only
baseline: six engine modules import a concrete source (three KIMDIS, three GEMI), one
five-package import cycle group and two module cycles exist, and the check fails on any new one.
Slice S2 (#155, merged at `bb99485`, hosted run 44609972812) added a neutral
`nima/sources/base.py` (page types, `SourceAdapter` protocol, `SourcePageError`) and a
`KimdisAdapter` that wraps the unchanged parser, proven equal to what the page store persists.
Slice S3 (#156, merged at `53b53ad`, hosted run 44629025079): the page store, run store, collector, resume and replay now work through
the adapter protocol, with KIMDIS the default via a small registry. Before the change, four real
collections were fingerprinted (every database row, the archive sidecar files and the replay
artifact) and pinned; the same pins pass on the moved engine, so no stored or archived byte
changed. The three KIMDIS engine-to-source imports are removed from the dependency baseline; the
three GEMI ones remain. Slice S4 (#157, merged at `0945918`, hosted run 44692930584) proves the protocol with two test-only synthetic
sources of different shape (text with decimal-comma money and line evidence; cursor-paged
nested JSON with minor-unit money). Parsing, storage, replay, quarantine and identity checks
pass unchanged for KIMDIS and both, with no engine change. **Correction (2026-11-20):** the
collection side is not yet source-neutral. The archive manifest records KIMDIS provenance and
every request goes to the KIMDIS endpoint for any adapter, and run options are stored and
reloaded as a KIMDIS `Query`, so resume was only exercised with a KIMDIS-shaped query. These are
specified in `docs/specs/SPEC-source-neutral-collection.md` (approved 2026-11-20). Slice N1 (#158, merged at
`535a16e`, hosted run 44702178868) delivered request and provenance: adapters now declare their origin and build
their own requests, a guard refuses unsafe or mismatched ones before any network call, and the
KIMDIS wire requests and manifest are byte-identical to `main`. Slice N2 (#159, merged at
`384a446`, hosted run 44709623301) delivered run options and resume: a run's query now comes from
its adapter, resume rebuilds the adapter from the saved connector version through the registry,
and an unregistered source stops before any request. The engine can now collect, resume and
replay any registered source; the S4 correction above is resolved. S5, a real second dataset, stays gated until the owner names it. The owner agreed to start with a
Diavgeia acceptance dossier. It is written (`docs/sources/diavgeia-acceptance.md`, from the official
documentation read on 2026-11-20) and awaits the owner's decisions before any adapter work.

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
[release contract](specs/SPEC-release-v1.0.md) and
[maintainers' handbook](maintainers-handbook.md#4-how-change-is-delivered). These proposed gates add no source,
metric, insight or operating capability. Baseline main is `9d29845` (#138);
contract-evolution PR #139 is separately in progress. Package version stays
`0.0.1`; old readiness percentages retain their original denominator.
