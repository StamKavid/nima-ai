# Capability progress: 2026-11-15

Main `50b43be` includes the owner-merged reviewed-decision workflow through #84,
following approved scope #74/plan #75 and checkpoints A–D. Local operators can
review exact company candidates, preserve reversible audit history and export
private evidence-backed resolution snapshots. The measured runbook #85 and delivery
record #86 are now owner-merged through `ef58c38`, completing checkpoint E with
all three exact-head gates green. The next [graph specification](graph/investigation-pilot.md)
is proposed for review; no graph code or additional capability credit is included.

The product is at the trusted-data/private-review milestone. The next major
user-facing target is a company → procurement → buyer investigation with dated,
inspectable source links. There is no implemented graph store, evaluated model,
AI research service or browser investigator workspace yet.

## Estimate and method

The original scope defined capabilities/release gates, not numerical weights or
effort estimates. This is an approximate capability-tracking rubric, not elapsed
effort, time remaining, Greek-record coverage or production readiness. The
headline is **approximately 30% overall**, with a planning range of **28–33%**.
Keep the same scope weights; explain any future scope/weight change.

| Original capability | Scope weight | Estimated delivered | Weighted credit |
|---|---:|---:|---:|
| Engineering foundation | 10% | 90% | 9% |
| Source ingestion and data pipeline | 25% | 55% | 13.75% |
| Entity resolution | 15% | 50% | 7.5% |
| Temporal graph | 15% | 0% | 0% |
| Risk analytics and ML | 15% | 0% | 0% |
| Evidence-cited AI research | 10% | 0% | 0% |
| Investigator workspace | 10% | 0% | 0% |
| **Total** | **100%** | — | **30.25%, rounded to 30%** |

The prior baseline through comparison delivery #73 was 27.25%, rounded to 27%
(25–30% range). All weights and other capability estimates stay unchanged.
Entity-resolution credit rises from 30% to 50% for the merged, complete local
review workflow: SQL-revalidated accept/reject/revoke, stable unclassified handles,
atomic/principal-bound retry, auditable history and private revision-bound exports.
That adds three weighted percentage points. Live matching accuracy, consolidation,
public authentication and a graph remain incomplete; this is partial credit.

PR counts, test counts and documentation earn no additional credit. The 1,375
passing tests/92.13% coverage prove tested implementation behavior, not identity
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
comparison and reviewed-resolution files. They retain provenance, notes, history,
current selected revisions and original report context. Old receipts do not
reactivate old acceptance; old exports do not silently adopt later decisions.
`automatic_identity_links=0`, with reviewed accepted occurrences counted separately.
Attribution is `database_principal_only`, not verified human authentication.

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

The executor has no configured local PostgreSQL/supported Docker capacity; its
SQL fixture setup failures are recorded, with hosted PostgreSQL/Docker providing
the physical evidence. These results do not establish server/power-loss recovery,
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
| Company-investigation graph pilot | Inspect a selected company, its contracts/public buyers and dated source links | Separate graph spec, reproducible rebuild, sampled edge/time correctness and identity review audit |
| Broader source coverage | Follow decisions/documents and procurement lifecycle changes | Live GEMI profile pilot; Diavgeia/TED; native text/OCR with location accuracy; distinct stage/value semantics |
| Company/sector signals | Review concentration, repeated relationships, eligible amendments and other explainable patterns | Coverage/denominators, comparable CPV cohorts and legal/context controls; no silent scoring of missing data |
| Evaluated ML and graph features | Prioritize useful leads at a realistic analyst review budget | Credible reviewed tasks, temporal/group-aware evaluation and improvement over simple baselines |
| Evidence-cited AI research | Ask questions and inspect supporting/contradicting Greek records | Retrieval recall, claim/citation/arithmetic correctness, abstention, cost/privacy/license gates |
| Full investigator workspace | Save companies/cases, explore timelines/networks and monitor changes | User-task validation, multi-user auth/permissions, deployment/operations and verified egress |

Recommendation for the next product specification: a bounded company → contracts
→ public buyers → evidence pilot, using a real reviewed cohort. A thin read-only
company dossier/explorer can test whether investigators finish verification faster;
it is a candidate for that spec, not an implemented workspace or a promise of broad
coverage. Expand the network and signals after sampled identity/edge checks and
observed investigator tasks support the value hypothesis.

Graph communities, shared addresses and repeated awards are investigative leads,
not findings of collusion or tax evasion. Co-bidding analysis needs identified
bidders/outcomes; awarded suppliers or bidder counts alone are insufficient.
Sector/price comparisons need comparable units, scope and amount basis. CPV and
company KAD are separate classifications. The
[architecture/model strategy](architecture.md) retains these eligibility gates.

The GEMI key pilot can run when authorized access arrives. Work on stored reviewed
evidence and a bounded graph specification can continue meanwhile. No production
model/provider, graph store or public service is selected by this documentation.
