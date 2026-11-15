# Delivery plan

## Current: bounded investigation graph — technical delivery

Status: **G1–G7 owner-merged through checkpoint D**, 2026-11-15, main `686875d`.
Scope #87 and implementation plan #90 were approved. The private JSON graph,
optional selected-history focus, operator CLI and measured runbook are delivered.
G6 #96 and G7 #97 both pass all three exact-head hosted checks and are owner-merged.
The [next evidence-recovery scope](../docs/graph/company-evidence-pilot.md) is a
proposal awaiting approval; no new pilot implementation plan is approved here.
Execute sequentially without delegation; no database adapter, extension, migration,
model/provider, live Greek-source request or deployment is added by this delivery.

The requested [database assessment](../docs/graph/database-candidates.md) identifies
Memgraph/FalkorDB as prototype candidates, Neo4j as a tooling baseline and AGE/HydraDB
as alternatives. Their benchmark/adoption needs a separate adapter scope after a
reference graph exists; it does not block this offline implementation. Older
incomplete work and the full historical plan below remain preserved.

### Intended outcome and dependency order

A local investigator can produce one reproducible, private artifact connecting
selected reviewed handles and reported occurrences to exact contract versions,
selected buyers and evidence locators. Unknown identity/validity remains unknown;
old snapshots and review history remain immutable. The graph is an evidence view,
not a company classification, spending total, fraud score or national coverage claim.

G1 connection-owned review read → G2 consistent graph source snapshot → checkpoint A
→ G3 pure graph/focus view → G4 complete private export library → checkpoint B
→ G5 CLI and physical publication recovery → checkpoint C → G6 measured runbook
→ G7 delivery/progress reconciliation → checkpoint D. Human review/merge applies at
each checkpoint; no automatic merge/deploy. G5 gets its own checkpoint because it
exposes the operator interface. The exact 2–5-file slices and focused commands are
in tasks/todo.md; a slice cannot expand scope silently when a new risk is found.

### Approved architecture and ownership

**One authoritative read.** The current review_snapshot.read_snapshot owns its
connection, so chaining it with another fact read would mix snapshots. G1 extracts
a guarded connection-owned reader while preserving the wrapper's input-before-SQL,
fixed-error and byte-for-byte export behavior. It requires an active repeatable-read,
read-only UTC transaction and never commits/closes its caller's connection. Keep
review validation, event folding and ledger reconciliation in the identity layer;
no caller-supplied validated token or duplicated review policy.

G2's graph reader owns schema checks and one transaction. Count/deduplicate selected
contract-version keys, preflight the additional stored projection and normalized
record bytes before labels, then reserve those bytes in the existing review reader.
The combined 8 MiB budget includes contract context plus all prior source/catalog/
anchor/ledger/terminal context, rather than two independent allowances. The old
review wrapper uses a zero extra reservation. Reject bool/negative/oversized budgets
and validate all selected evidence as before. Never substitute current whole-run
membership for the historical report selection.

Recompute each full contract projection with the existing codec and compare both
its digest and actual stored projected values. Return only immutable minimal
contract facts needed by the graph, not unselected supplier labels or normalized
source bodies. Use batch reads keyed by complete source/version tuples; no N+1
query per node. Existing SQL timeouts apply. Close every connection on success,
fixed failures and interruption. No source, outbox, review or workflow writes occur.

**Pure graph construction.** The graph package owns typed graph inputs, node/edge
keys, focus construction and graph-specific failures. Reuse build_resolution and
canonical encoding for the embedded review object/hash; do not reimplement identity
semantics. Namespaced node/edge IDs retain complete keys. Sorted arrays and collision/
dangling checks preserve deterministic output. Repeated observations retain their
own occurrence nodes while sharing a contract-version node; legal entity class,
validity intervals and new supersedes links are never inferred.

Keep all five approved edge families, selected-history handles and ambiguities,
including unresolved/rejected/revoked members. Only active acceptance creates a
reviewed_as edge; its exact candidate/revision/event remains inspectable. A focused
UUID selects inside this same cohort, with omitted/active_links/no_active_links/
not_in_selected_history outcomes and explicit absent selected buyers. It cannot
search for additional company occurrences or auto-consolidate buyer keys.

**Publication and CLI.** The export library reads, closes SQL, builds/encodes and
publishes through the existing private no-clobber publisher. Original comparison
and resolution hashes, exact source dates, observation times and ledger metadata
remain distinct. No generation clock, path or process metadata changes artifact
identity. Retain decimal-text contract amounts, nulls, record-level procurement
pointers and field-level registry pointers. Never allocate joint-supplier totals
or sum record versions. Archive integrity stays not_checked and attribution stays
database_principal_only; automatic links stay zero.

G5 adds graph snapshot through a graph-owned handler and minimal root CLI wiring.
Reuse the existing strict private report reader. Root graph parsing emits fixed
redacted errors for unknown/misplaced options and invalid values; other commands
retain existing help/exit behavior. Keep DB credentials out of arguments/output;
only NIMA_DATABASE_URL is read for access, with no HTTP/GEMI/provider client or key.
Fixed graph_ failure suffixes and 0/1/2/130 exits follow the approved contract.

### Resource and verification gates

Preserve 100 selected occurrences, 100 combined registry/anchor observations,
1–10,000 events, 8 MiB combined SQL input and exact 32 MiB private input/output
bounds. Enforce at most 600 graph nodes/500 edges and fail before publication
rather than truncate. Counts/bytes include every additional field read for graph
validation. The graph builder does not weaken existing identity/report limits.

Every implementation slice runs focused tests plus just check and just audit,
then all three exact-head hosted jobs: quality with real PostgreSQL, Compose and
the complete controlled-worker verifier. Coverage remains ≥90% combined. Missing
local PostgreSQL/Docker prerequisites are reported; hosted physical evidence is
required, without new skips, suppressions, dependency or CI changes. Existing
StamKavid author/committer verification applies to every pushed candidate.

Verify exact expected graph sets independently of the builder, real SQL budget/
corruption guards, unselected-data exclusion, repeated observations, joint suppliers,
old/new versions, outside anchors, ambiguous handles, missing fields and full review
reversals. Independent transactions exercise a revocation during a pinned read;
results must be a coherent before or after state. Snapshot all 23 existing evidence/
workflow relations plus the three review relations; ordinary export/CLI/retry leaves
all rows unchanged. The concurrent test separately accounts for its intentional writer.

Physical child-kill tests interrupt real publication before/after its final link,
prove SQL is closed and retry the uninstrumented CLI. No production pause hook.
A material active-review or version-deduplication mutation must fail a meaningful
regression, followed by exact restoration and the normal gates. Security review
checks parameter binding, private artifacts and source-value-free errors; performance
review checks batch access, bounded input/output and linear graph/focus construction.

### Risks, mitigation and remaining gates

| Risk | Mitigation / evidence required |
|---|---|
| Refactoring shared identity reads changes old behavior | Separate G1; existing wrapper/export/CLI regression suite and unchanged canonical bytes before graph code |
| Extra contract data bypasses review preflight | Count full normalized/projection payload and reserve it in the same 8 MiB budget before labels; real over-budget tests |
| Matching hashes hide altered projected columns | Compare re-derived full payload and digest with exact stored facts; mutation/corruption cases |
| Review/fact read races or resurrected acceptance | One guarded snapshot, exact active-event keys, independent concurrent revoke and history cases |
| Duplicate observations/versions inflate spend | Stable per-version keys, distinct observations, no aggregate spend or edge value allocation |
| Partial files or source-bearing errors leak | Shared private publisher, actual SIGKILL/retry, fixed parser/driver codes and redaction tests |
| A small graph is mistaken for an evaluated product | Separate real-cohort source recovery and observed investigator tasks; no benchmark or product-value credit from fixtures |
| Database choice becomes a hidden prerequisite | Portable contract first; separately scoped adapters compare technical/runtime results and actual-use license fit |

The merged offline workflow needs no live GEMI key or graph-store choice. Broader
adapters, packages, services, source requests, purchases, deployment and admin changes
still need their own scope. Real-cohort availability, source recovery, empirical
identity/edge/time checks and observed investigator tasks remain separate gates.
The [progress estimate](../docs/progress.md) is approximately 33% using unchanged
weights and limited credit for the implemented bounded graph; documentation and
PR/test counts add no credit.

### Measured delivery and completed owner checkpoints

| Slice | Delivery | Owner merge |
|---|---|---|
| G1 caller-owned review read | #91 / `964c33a` | `0f623a1` |
| G2 complete graph source snapshot | #92 / `7e7660b` | `7de0b9c` — checkpoint A |
| G3 pure graph/focus | #93 / `1f39df4` | `652e609` |
| G4 private export/races | #94 / `8518a7f` | `eb5d9dd` — checkpoint B |
| G5 CLI/physical publication recovery | #95 / `e406c02` | `4a33a3e` — checkpoint C |
| G6 measured operation | #96 / `cab6769` | `66712bd` |
| G7 delivery/progress reconciliation | #97 / `24a9fa4` | `686875d` — checkpoint D |

Every runtime candidate passes all three exact-head hosted jobs. Final runtime
`e406c02` in run 43739790204 passes 1,508 tests/92.37%, quality/build/security/audit,
Compose and 12 Docker tests/833.86 s with one fresh validated 28-case receipt.
Internet-egress/IP-protection/production flags stay false. The
[graph runbook](../docs/verification/investigation-graph.md) records full candidates,
runs, source/identity/time/value limits, 26-relation read-only checks, independent
revoke interleavings, mutations and actual pre/post-link SIGKILL/Ctrl+C retry.
The disposable local PostgreSQL baseline now supports complete SQL checks; earlier
local-prerequisite limitations remain historical, and supported Docker evidence
still comes from hosted CI. Documentation candidates run their own normal gates.

Checkpoint D is complete. G7 `24a9fa4` passes quality (1,508 tests/92.37%),
Compose and the full worker suite (12 tests/861.28 s, one fresh 28-case receipt)
in run 43744988054. Production/privacy flags remain false. The approved design
above and all earlier incomplete tasks and historical records below are preserved.

The proposed next scope is a separate real-company evidence-recovery pilot:
authorize a small private cohort, recover source bytes/locations for every displayed
active link, record contradictions/unknowns and audit identity, dates and amounts.
Then observe participation/citation/revocation tasks against the manual workflow,
including completion, critical errors, time and familiarity. METLEN remains a
candidate from the owner's earlier request; no real-company retrieval or validated
demonstration is asserted here. A thin read-only dossier/explorer and separately
scoped graph-store benchmarks can follow the evidence/value gate. Wider sources,
eligible signals, ML, cited AI, public auth and production operation remain later.

## Completed: reviewed identity decisions — implementation plan

Status: **implementation and measured documentation merged through checkpoint E**,
2026-11-15. Scope #74 and plan #75 were approved. The owner merged RI1–RI9 through
#84 at `50b43be`. Final implementation `fdf8289` passes all three jobs in run
43707453503: 1,375 tests/92.13%, clean build/security/audit, Compose and 12 Docker
tests/855.34 s with one full validated 28-case fixture receipt. Production/privacy
flags stay false. See the [measured runbook](../docs/verification/reviewed-decisions.md).
RI10 #85 and RI11 #86 are owner-merged through `ef58c38`. Both final documentation
heads pass quality, Compose and the full worker suite; see their PR delivery evidence.
No completion credit is added for documentation, PR counts or test counts.

The sections below preserve the approved design and its boundaries. The merged
implementation is a trusted-local-operator workflow, not a deployed public service.

Deliver explicit local accept/reject/revoke operations, stable unclassified party
handles and private reviewed-resolution exports. Preserve all original evidence,
source/projection/outbox/workflow state and existing CLI/report behavior. No source
request, key, model, graph, dependency, public service or production/admin action
is included. Execute sequentially without agent delegation. Older incomplete
access/product work and the complete RC1–RC7 delivery record remain below.

### Dependency order and review checkpoints

RI1 strict private input/request types → RI2 pure state rules → checkpoint A →
RI3 additive ledger schema → RI4 SQL evidence validation → checkpoint B →
RI5 atomic acceptance library → RI6 rejection/revocation library →
RI7 concurrency, permissions and actual SQL-commit recovery → checkpoint C →
RI8 private resolution-export library → RI9 operator CLI/export crash checks →
checkpoint D → RI10 measured runbook → RI11 delivery/progress reconciliation →
checkpoint E. The roughly 2–5-file tasks, acceptance and focused commands are in
`tasks/todo.md`. Every checkpoint includes human review/merge of working slices;
no automatic merge/deploy. Keep dependent PRs draft or target main with their
complete approved prerequisites included. RI1 followed owner approval of plan #75.

### Measured implementation delivery and product handoff

| Slice | Owner-reviewed delivery | Main merge |
|---|---|---|
| RI1 private inputs | #76 | `3a6d1fc` |
| RI2 pure transitions / checkpoint A | #77 | `d07bfb2` |
| RI3 ledger schema | #78 | `3667518` |
| RI4 SQL evidence / checkpoint B | #79 | `623bbf5` |
| RI5 atomic acceptance | #80 | `e9f1e1c` |
| RI6 reject/revoke | #81 | `120febb` |
| RI7 races/principals/COMMIT recovery / checkpoint C | #82 | `b37ec70` |
| RI8 private resolution snapshots | #83 | `cda2c07` |
| RI9 operator CLI/publication recovery / checkpoint D | #84 | `50b43be` |

All final candidates pass quality/Compose/full worker checks; the runbook records
exact results. These are implemented local capabilities, not empirical matching
accuracy or production operations. Local PostgreSQL/Docker setup limitations were
reported rather than skipped. RI10/RI11 candidates have their own final checks.

Capability tracking remains scope-weighted: approximately 30% overall (28–33%
planning range), up from 27% for the complete merged manual review/audit/export
workflow. Weights and other estimates stay unchanged; identity rises 30%→50%,
adding three weighted points. See [progress](../docs/progress.md) for arithmetic,
partial-credit limits and older baseline history.

After checkpoint E, draft a separate reproducible temporal-graph/company-investigation
pilot specification: selected company → procurement → public buyer → dated evidence,
with sampled identity/edge/time correctness and reproducible rebuilds. A thin
read-only dossier/explorer is a product-validation candidate for that scope; full
workspace, broader sources, eligible signals, evaluated ML and cited AI remain later
milestones. Live GEMI compatibility, public-service authentication, consolidation,
production operation and deployed egress are still unverified. No next-stage code
or deployment is authorized by this delivery record itself.

### Typed input and evidence boundary

RI1 uses `nima.evidence.artifacts`' descriptor-based private regular-file reader;
translate its errors into fixed review diagnostics rather than building another
file framework. Require 0700/0600 ownership, no symlink traversal, bounded reads
and unchanged-file checks. Bound the request at 16 KiB/rationale at 4 KiB UTF-8
and comparison bytes at 32 MiB. Reject duplicate/unknown JSON keys, excessive
nesting, wrong types (including bool-as-int), non-finite/oversized numbers, blank
rationales and unsupported versions before database access. Preserve original
Unicode/free text. Canonical request identity includes operation, source keys,
expected revision, entity/reversal fields, rationale, acknowledged issues and the
expected report hash; exclude local file paths and server recording time.

Keep parsing/type validation, pure state folding and I/O separate. Exact request
and report schemas are versioned together with the accepted specification; no
private source-bearing parser error can escape. Pure RI2 transitions forbid direct
replacement/rejection of an active acceptance, cross-pair revocation, resurrection
and implicit propagation. A rejection may be superseded explicitly. At most one
pair is actively accepted for a subject; no rejection creates an entity.

RI4 validates selected immutable SQL tuples through a caller-owned connection.
Do not call the current-run cohort wrapper as if it reproduced historical coverage:
that wrapper would include later collection. Resolve the frozen report occurrence
keys against observations/receipts/mentions and complete declared GEMI imports,
terminal responses/profiles and approved scalar pointers/dates. Reuse existing
normalization codecs and the pure comparison policy. Report hashes are byte
identity, not authentication. Supplied coverage stays labeled report context;
it neither authorizes a write nor certifies historical completeness.

A new accept/reject validates the chosen subject and complete registry catalog.
An existing target handle adds its exact anchor, including AFM-change issues even
outside the report. Resolution validates every selected subject plus needed anchors
and ledger history. Count overlapping observation keys once against the combined
100-observation budget; never discard unmatched/404 rows to fit. Preflight combined
SQL source/ledger context at 8 MiB before transferring labels/notes. No source or
archive repair/import is implicit. Recompute eligibility/issues from SQL facts,
never copied file outcomes. New writes cannot use caller-supplied validation flags
or a fabricated typed proof to bypass that database boundary.

### Additive storage and first working write path

RI3 adds migration `0007.sql` and registers it in `_migrations()`; migrations
0001–0006 and their hashes remain untouched. New authoritative relations hold
immutable entity anchors and request/event history; mutable subject heads contain
only concurrency state that must reconcile with the event fold. Key subjects by
observation/projection/role/ordinal and cross-check their run/source/content keys.
Use foreign keys to existing source observations, projected mentions and GEMI
observations where their existing unique keys support exact references.

Use request UUID as the single immutable event UUID/primary idempotency identity;
store a canonical payload digest, server-derived `session_user`, UTC recording
time, subject revision, exact source/report/candidate refs, policy, rationale,
issues, target entity and reversal reference. Constrain allowed operation/target
shapes, unique `(subject, revision)`, exact anchor ownership and compatible entity
references. Entity creation and its creating event may use deferred mutual foreign
keys checked at commit; no orphan entity is accepted. New immutable triggers use
the existing mutation-rejection mechanism. Add no PUBLIC or dedicated worker-role
grants. Database owners/shared owner credentials remain privileged and are not
claimed to be isolated reviewers or tamper-proof actors.

RI5 owns one READ COMMITTED write transaction with per-subject row locking. Source
facts/anchors are immutable; a fresh statement after acquiring the head lock lets
a waiting identical request observe its winner. Read the database principal,
check committed UUID/payload/principal identity, then create/lock the subject head
and check idempotency again before comparing the expected revision. The latter
check prevents a concurrent exact replay from becoming a false stale-head failure.

For a new request, validate source/anchor context, fold current subject events,
check the expected revision and single-active-accept invariant, create/select the
compatible entity, append the event and advance the head exactly once atomically.
Initialize a new subject at revision zero only inside that transaction; failed
validation leaves no partial head/entity/event. Entity/anchor uniqueness races
must not bypass winner-anchor validation; safe rollback with a fixed conflict is
acceptable. A global request UUID collision on a different subject also rolls back
all local work before classification. No unbounded retry or hidden reassignment.

An identical committed replay returns the original acknowledgment/revision, without
reapplying a decision, checking the now-stale head or claiming that old acceptance
is current. Its declared report hash is part of the stored request identity;
committed replay need not revalidate current source coverage. Changed content or
another principal cannot reuse a committed UUID. An uncommitted rolled-back
request leaves no reserved identity. Print success only after commit; a lost
acknowledgment is recovered with the same request UUID/payload.

RI6 adds rejection and revocation through the same transaction boundary. Revoke
resolves the stored current pair event and expected subject revision without a
report/archive file; it can undo a decision made under an older policy. It appends
history and returns that pair to unreviewed without reviving older decisions or
removing another pair's acceptance. Reassignment remains explicit revoke, then
accept, so interruption between them is safely unresolved.

### Permissions, races and physical recovery

RI7 uses independent PostgreSQL connections to race same/different UUIDs and
expected revisions, including same-subject competing targets and entity-creation
collisions. Verify one accepted pair, one event per committed request, exact head
fold and unchanged source/outbox/workflow state. SQL privileges are checked using
separate disposable test principals, not a request's claimed actor. Read-only
principals cannot perform new writes; another principal cannot replay a UUID as
its own. Shared/trust-authenticated test credentials prove database attribution,
not human authentication.

Create only uniquely named test roles on the supported disposable local PostgreSQL
server; revoke test grants and drop them in guaranteed cleanup. No role/admin setup
runs against production or through an application command. Use child-only database
commit interception/locks for real pre/post-COMMIT SIGKILL and lost-ack replay.
No production pause hook, crash switch or weakening of immutable source controls.
Retain the existing 5-second connection/lock and 30-second statement bounds.

### Resolution export and CLI exposure

RI8 reads one repeatable-read, read-only transaction, then closes SQL before private
publication. Preflight selected event count (requested 1–10,000), source/ledger
context bytes and catalog/anchor count before materialization. Fold every selected
subject, including unresolved/rejected/revoked cases; reconcile each head with its
history and exact immutable anchors. Expose selected ambiguity rather than global
entity uniqueness. Keep review status, unchecked authority/issuer fields and source
claims separate. Preserve original report/context and count reviewed accepted links
separately from `automatic_identity_links=0`.

The canonical artifact binds report hash, policy, selected subject revisions/events
and provenance; server event times are retained, but no generation timestamp or
sequence-as-global-commit-order claim is added. Reuse `identity.artifacts.encode`
and `publish`, their exact 32 MiB guard, private permissions and verified no-clobber
reuse. Later decisions yield a new artifact; old snapshots and comparison reports
remain unchanged. No second generic artifact/persistence framework.

RI9 exposes `identities review` and `identities resolution` only after complete
library paths pass. Existing routes remain unchanged. Fixed IDs/counts/statuses/hash
summaries and 0/1/2/130 exits must redact private files, notes, labels and raw driver
messages, including malformed parser options and transaction errors. It reads no
GEMI key and creates no HTTP client. Test actual export publication termination
and normal-CLI replay using child-only interception. Temporarily mutate a material
revision/reversal guard, prove its regression fails, restore exact bytes, then run
all normal gates. No mutant is committed or exposed as product configuration.

### Verification, delivery and remaining gates

Use failing focused tests before behavior. Every slice runs its listed tests and
unchanged `just check`/`just audit`; final heads also require all three hosted jobs
and the complete `just source-worker-check` receipt. Keep the 90% combined coverage
floor, pins, timeouts and all security/advisory checks. Local PostgreSQL/Docker
prerequisites are currently unavailable; report setup failures honestly and use
supported hosted runners for real evidence. Do not install/pull large local images
into an executor below the worker's storage prerequisite.

RI10/RI11 document measured commands, mutation/physical recovery, grant/trust limits
and exact-head results, then reconcile delivery without crediting proposals or PR
counts as product completion. Live GEMI compatibility, empirical matching quality,
public-service authentication, entity consolidation and graph projection remain
separate gates. No external key or missing operator preference blocks this plan.

| Main risk | Planned control |
|---|---|
| Forged/partial report hides conflicts | Full selected import reconciliation, SQL source checks and existing-handle anchor union |
| Retry reactivates a revoked match | Committed-request acknowledgment before CAS; no state mutation on replay |
| Competing accepted links or orphan handles | Per-subject lock, revision compare, unique constraints and one transaction |
| Shared credentials mistaken for a human | Server principal and explicit assurance/trust limits; no public API |
| Incorrect reversal or stale export | Pure fold, no resurrection, immutable revision/event-bound snapshots |
| Huge private history or leaked rationale | SQL preflight, bounded private readers/encoder and fixed CLI diagnostics |

## Completed increment: offline registry comparison

Status: **RC1–RC7 merged**, 2026-11-15, through #73 at main `d6c1552`.
The user approved the specification through #65 and the implementation plan
through #66, then merged the implementation/review checkpoints through #72.
Main `c764dcb` introduced the complete offline comparison CLI. #73 adds the
measured runbook and progress reconciliation; its candidate `9e5e4ac` passes all
three jobs in run 43681084835 (1,106 tests/91.82%, 12 Docker tests/660.33 s and
one validated 28-case receipt). No new behavior is claimed by that documentation.

| Delivered slice | Human merge / evidence |
|---|---|
| RC1 shared reader | #67, `fd65387`; unchanged assessment and caller-owned transaction checks |
| RC2 pure policy / checkpoint A | #68, `8885aa6`; typed three-way outcomes and zero accepted links |
| RC3 bounded shared snapshot | #69, `09975d2`; SQL limits, exact joins, concurrency and unchanged evidence |
| RC4 private report / checkpoint B | #70 merged to its dependency branch at `6232f71`; #71 integrated its unchanged files into main at `054ca5f` |
| RC5 CLI / checkpoint C | #72, `c764dcb`; redaction, actual pre/post-publication SIGKILL and deterministic replay |
| RC6–RC7 | #73, `d6c1552`; measured runbook, capability notes and reconciled task/progress record |

Final implementation candidate `8c46f144e6ec2f889b56a8f76170e7c5dd9d07b6`
passes all three jobs in [run 43679268034](https://github.com/StamKavid/nima-ai/actions/runs/43679268034):
1,106 quality tests, 91.82% combined coverage, clean build/security/audit,
Compose, and 12 real Docker tests in 648.64 seconds. The worker verifier accepts
one full 28-case controlled-fixture receipt. All 23 new CLI cases and both actual
SIGKILL/replay cases pass on hosted PostgreSQL. Local PostgreSQL is unavailable;
its fixture setup errors were not represented as passes.

A temporary material eligibility-guard bypass caused 10 regression failures;
exact original bytes were restored, then 63 focused policy/CLI tests and the
full hosted suite passed. No mutant or production pause hook is committed.
See the [operator and delivery record](../docs/verification/registry-comparison.md)
for exact slice-level evidence, limits and the policy-file restoration hash.

Build one private, reproducible report comparing a selected KIMDIS run with
1–10 selected stored GEMI imports. Keep all occurrences/observations, three fixed
outcomes, source assertions, contradictions and unknowns. Automatic identity links
stay zero. No live request, key, migration, dependency, graph, model or schedule
change is required. The original access, administration and later-product tasks
remain below; this plan extends the active comparison work without replacing them.

### Dependency order and delivery slices

RC1 shared cohort reader → RC2 typed comparison policy → checkpoint A →
RC3 bounded registry snapshot → RC4 canonical private report → checkpoint B →
RC5 operator CLI/crash/mutation checks → checkpoint C → RC6 measured runbook →
RC7 capability/progress record. Execute sequentially, without agent delegation.
Task acceptance criteria, commands and roughly 2–5 files per task are in
`tasks/todo.md`. Human review/merge remains a checkpoint; do not automatically merge or deploy.
The order below records the approved implementation contract, now delivered
through RC7, including documentation/reconciliation.

RC1 leaves the existing assessment working through a reusable connection-owned
reader. RC2 supplies tested pure comparisons without exposing a command. RC3/RC4
then deliver the complete SQL-to-private-report library path. RC5 exposes that
verified path to operators. No placeholder CLI, fake profile or separate normal
worker-matrix invocation substitutes for a working slice. Combine compatible
small tasks into a focused PR only while their complete diff remains reviewable;
leave dependent PRs draft until their parents are merged or safely retargeted.

### Shared snapshot and source boundary

Extract the existing KIMDIS query/validation body into a reader that accepts an
already configured connection. Preserve `read_cohort`'s public signature, default
32 MiB guard, coverage semantics, sorting and existing assessment output. Its
wrapper retains schema validation, connection ownership, repeatable-read/read-only
transaction and UTC setup. The connection-owned helper must not open, commit or
close another transaction. Give that new helper an optional stricter input-byte
budget, defaulting to the current 32 MiB guard; the public wrapper stays unchanged.
Comparison applies its own complete provenance ordering
without changing the old assessment format.

The comparison reader owns one connection/transaction and sets its characteristics
before evidence queries. Preflight both the selected KIMDIS membership and selected
GEMI metadata/counts/allowlisted scalar contexts in SQL before transferring labels.
Reserve the registry/context estimate from the 8 MiB budget before the shared
KIMDIS helper preflights/materializes its part; fetch registry/context labels only
after the combined bound succeeds. Reuse the membership logic rather than copy
its eligibility/coverage rules into a second KIMDIS reader.
Enforce at most the requested 1–10,000-mention budget, 100 registry observations
and 8 MiB aggregate input; zero KIMDIS occurrences are valid. Do not independently
read the two sources and combine snapshots afterward. Reuse the existing driver's
5-second connection, 30-second statement and 5-second lock timeouts.

Reconcile import versions/counts and terminal response/profile references, including
found versus 404 outcomes. Decode only the approved scalar fields and provenance;
do not fetch full manifest bodies, whole profiles/activities or archive paths as
report context. Retrieve procurement source dates from the matching existing
contract facts. Preserve null/empty values and field pointers; malformed stored
shapes or missing joins fail with a fixed reason. Do not rehash archives or write
source, outbox, identity or scheduling tables. Close SQL before publication.

### Comparison, report and publication contracts

Keep new immutable evidence/result types and comparison functions in
`registry_policy.py`, with no SQL or filesystem dependency. Reuse the existing
KIMDIS assessment for eligibility. Compare only eligible reported AFM texts;
preserve ASCII-only trimming, leading zeros, GR/EL distinction, buyer-key
separation, unknown issuer and unchecked checksum/authority. Candidate agreement
never accepts an identity. Index eligible registry keys, retaining every selected
observation and explicit conflicting AFM/registry-number issues.

`registry_cohort.py` materializes the bounded snapshot. `registry_report.py`
assembles and publishes the complete result through a `compare_run` library entry
point. Keep registry observations in one shared catalog; occurrences hold bounded
references. Use complete provenance keys, including observation IDs, for stable
ordering; selector order and repeated A→B→A versions cannot change replay bytes.
Include observed coverage and import metadata in the report's inputs, with no
wall-clock generation field. Keep temporal claims distinct and
`archive_integrity=not_checked`.

Use `report_format=nima-registry-comparison-report-v1` and
`policy_version=registry-comparison-v1`. Reuse the current streaming canonical
encoder's exact 32 MiB ceiling and the private no-clobber/hash-based publisher;
do not create a second generic artifact framework. Hashes and input provenance
distinguish this format from existing assessment reports. An interrupted publish
may leave a complete reusable artifact; replay verifies exact bytes. Partial or
conflicting files are never accepted or overwritten.

Only after checkpoint B, add the approved `identities compare` interface. Validate
UUID selectors, duplicate/count limits, projection and numeric bounds without
echoing invalid source-bearing values. Preserve all other CLI routes. Use only
environment-supplied `NIMA_DATABASE_URL`; do not inspect a GEMI API key. New
comparison errors and reused assessment/database/publication errors must map to
the specified fixed diagnostics and exits 0/1/2/130. Stdout remains IDs, counts,
statuses and hash; names, AFMs, paths and driver text stay private.

### Verification and release

Use failing focused tests before behavior. Pure tests cover identifier eligibility,
contradictions, 404s and observation preservation. Real PostgreSQL tests use
independent connections and synchronization to prove the common snapshot,
pre-transfer count/byte bounds, exact joins and unchanged evidence/outbox state.
Synthetic cohorts exercise unknown/empty supplier lists and incomplete projection
rejection. Report tests cover deterministic bytes and exact canonical output caps.

CLI tests cover fixed outcomes/exits and redaction. Adapt the existing child-only
publication-boundary interception pattern for actual pre/post-publication SIGKILL;
add no production test switch or pause hook. Replays must leave one complete
accepted report and preserve source state. Temporarily mutate one material
eligibility/provenance guard, prove its regression fails, restore the exact bytes
and rerun the normal suite. Never commit the mutant or make mutation a product API.

Required commands remain `just check`, `just audit` and the additive
`just source-worker-check`, with all three hosted jobs on the exact final head.
Keep the 90% combined coverage floor, pins, timeouts and security checks. The local
executor currently lacks PostgreSQL and cannot inspect Docker's data filesystem;
record those setup failures honestly and use supported hosted runners for physical
evidence. Source calls, external accounts, deployment and live administration are
outside this plan. GEMI live-profile compatibility and empirical matching quality
remain separate gates.

### Risks and open questions

| Risk | Planned control |
|---|---|
| Refactor changes existing assessment bytes/coverage | Keep the wrapper contract and verify existing reports plus caller-owned snapshot behavior in RC1 |
| Different source snapshots or incomplete joins | One real read-only transaction, synchronized concurrency tests and exact reconciliation in RC3 |
| Large text or repeated candidate expansion | SQL preflight for aggregate input, shared observation catalog and exact streaming output cap |
| Report agreement mistaken for identity/history | Zero automatic links, explicit unknowns/dates, no transitive closure or inferred validity |
| Secret/source values in CLI failures | Fixed codes, value-free validation and sentinels through actual command failures |
| Process dies at publication | Real child termination and byte-verified no-clobber replay |

No credential blocked the delivered offline build. The next product work needs
a separate specification for reviewed, reversible identity decisions, evidence
selection and empirical evaluation before temporal graph projection. GEMI live
profile compatibility remains a separate access/pilot gate.

## Completed increment: source-worker egress verification

The user approved implementation on 2026-11-12 by “Continue”, following
`docs/sources/source-worker-egress.md`. E1–E12 are merged through PR #64 at
`127b3b8`. Source collection and deployment stayed disabled throughout this
fixture-only increment. The implementation and measured checkpoint history follow.

Implementation progress: E1–E3 and checkpoint A passed at `98fa958` in
[hosted run 43267775558](https://github.com/StamKavid/nima-ai/actions/runs/43267775558)
(602 tests, 91.53% coverage, all three jobs green). E4's offline policy/receipt
semantics passed at `1f72c8f` in
[run 43272416378](https://github.com/StamKavid/nima-ai/actions/runs/43272416378)
(634 tests, 91.86%, all three jobs green). The user merged PRs #35 and #36
on 2026-11-13. E5 reached main through #37, #38 and #40 (#39 was first
merged into its dependency branch). Delivery head `cfcb677` passed all three jobs
in push run 43398560990 and PR run 43398771919: 650 tests, 90.54% coverage.
E6 gateway CONNECT/TLS/auth and checkpoint B passed at `4d749ae` in
[run 43403470378](https://github.com/StamKavid/nima-ai/actions/runs/43403470378):
two real Docker tests passed in 21.04 seconds, including pinned Envoy validation,
HTTPX/Chromium HTTPS/auth, Chromium NSS trust and independent delivery counters.
Its real client probes live in `protocol.py`; the observer reads allowlisted admin
counters plus origin delivery counts. Unit tests verify configuration and failure
classification; they do not substitute for the real Docker gate.
The user merged #41 and #42 to main. Their delivery head `2ce99b1` passed
687 tests with 90.66% coverage in PR run 43404629205.
Runtime discovery: Chromium 158 reports an invalid-credential
407 CONNECT response as `ERR_HTTP_RESPONSE_CODE_FAILURE`; retain independent
RBAC-denial and origin-delivery checks when classifying this outcome. Do not
accept arbitrary browser errors as authentication proof.
E7 passed at `d8e0a3c` in
[run 43422295581](https://github.com/StamKavid/nima-ai/actions/runs/43422295581):
746 tests, 90.72% coverage, all three jobs green; three real Docker tests passed
in 49.27 seconds. Seven destination/protocol counters increased while independent
canary/host/metadata delivery counts stayed zero after successful controls.
An inner user namespace could not map the observer's outer UID, administer the
parent network namespace or bypass the rule using its own inner UID 10002.
The normal helper reads back policy without rewriting it. Scope is Nima's named
table only; existing Docker tables remain intact. nft 1.0.6 elides a redundant
l4proto check beside a typed port selector; normalize that equivalent form only.
The fixed nft/ip wrapper has two narrowly documented Bandit annotations, B404 and
B603, with no shell or external command/argument/stdin selection. Review the
annotations explicitly; no global scanner exclusions or threshold changes.
At that checkpoint, the complete client/fault matrix and checkpoint C remained
unverified. E8 moved execution into the bounded fixture-only runner. Deployed
IP protection remains unverified throughout this increment.
The user merged E8's HTTP probe slice in #46. E8 now has a reusable bounded
controller and private HTTP-stage reports: delivery head `e866c97` passed all
three jobs in run 43514084957 with 884 tests and 91.37% coverage. Four real Docker
tests passed in 149.92 seconds; the fourth executes the application runner,
reconciles all 18 HTTP cases and reads its report after verified owned cleanup.
The user merged #47–#50 into main at `84ae48d`. Final E8 head `ec9bd87` passed
all three jobs in runs 43515242251/43515327115: 884 tests, 91.37% coverage and
four real Docker tests. See `docs/verification/source-worker-runner.md`.

The user merged E9 PRs #51–#53 into main `c02ef94`: ten Chromium cases, independently
observed runtime/topology and the combined 28-case runner. A small additional
runtime slice reads actual process/forwarding state and privilege probe results;
it does not infer receipt fields from Compose declarations. The initial real
browser suite reached forced QUIC and reported `ERR_QUIC_HANDSHAKE_FAILED`;
recognition of that client outcome still requires the positive independent
QUIC control, named kernel drop increase and zero delivery. STUN now waits for
asynchronous ICE gathering. The real matrix passes those transports and reaches
browser gateway outage, where a timeout needs classification as a network
failure while actual stopped-state/zero-delivery checks remain required. That
correction is published in #54. The owner explicitly confirmed public repository
visibility on 2026-11-14; that supersedes the original private-hosting requirement.
Evidence archives, source data, credentials and databases remain outside Git.
Candidate `c6e9c39` in #54 passes all three jobs in runs 43613463647/43613476257:
967 tests, 91.55% coverage and six real Docker tests in 334.31 seconds, including
the complete 28-case run and actual runtime receipt. This passes checkpoint C;
the correction was merged through #54 at `9562213`. The full receipt validator is
unchanged; it still requires all 28 cases and actual runtime evidence. See
`docs/verification/source-worker-browser.md`. Deployed IP protection is unverified.
Local focused tests/types/security passed; the full local PostgreSQL gate could
not start because this executor lacks Docker storage. Hosted full tests used
real PostgreSQL. Keep that validation limitation visible at delivery.

E10 is merged through #61 at `920472e`. Final candidate `f3a063e` passed all
three jobs in run 43622181210: 967 tests/91.55% coverage and 12 real Docker
tests/853.96 seconds. Actual worker deadline, missing capability, controller
signals, credential redaction, scoped reclamation and packet-rule restoration
are measured. The hard-signal tests cover an explicit between-command boundary;
they do not provide a deployed supervisor.

E11 is merged through #63 at `9a4eddf`: the complete `just source-worker-check`
recipe, fresh private full-receipt validation, success-only canonical JSON upload
and matching proposed protection context. Candidate `4fe920d` passes all three
jobs in run 43625798326: 987 tests/91.58% coverage and 12 real Docker tests in
616.42 seconds. Downloaded artifact 14126851164 matches GitHub's ZIP digest and
contains exactly one valid canonical 28-case JSON receipt, with deployment/privacy
flags false. E12's runbook and five-axis review were merged in #64 at `127b3b8`.
Its exact candidate `39fd05b` passes all three jobs in run 43627192150:
987 quality tests/91.58% coverage and 12 real Docker tests/624.58 seconds.
The final verifier accepted one complete 28-case receipt before successful upload.
See
`docs/verification/source-worker-egress.md` for commands, evidence and limits;
older stage-specific reports retain their historical results.

### Selected stack and immutable pins

First support Linux/amd64 only. Use official publisher images and preserve source
licences. Envoy and Playwright are Apache-2.0; cryptography is Apache-2.0 OR BSD-3-Clause.
Debian utilities retain their upstream OS-package licences. No service subscription
or proprietary proxy SDK is needed. This is a test stack, not a production image.

| Component | Selected pin |
|---|---|
| Gateway | `envoyproxy/envoy:v1.40.2@sha256:49d3e8b6246d1a804acffaebe42f2799edc77b77a37a97709ef742af90b6d223` |
| Browser fixture base | `mcr.microsoft.com/playwright/python:v1.65.1-noble@sha256:ce84a3d75a47e81657d2ec2c0a949e6e0ef790abdc32ce6819220a3df987ff9a` |
| Namespace helper base | Existing `python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e` |
| Python browser binding | `playwright==1.65.1`; Linux x86_64 wheel SHA-256 `5660e0b050a5bd5672bf8e366ed2580288a3d3640ff9444436ed2d890d3dc442` |
| Bundled browser target | Chromium `158.0.8127.18`, revision `1254`, from the verified wheel's `browsers.json` |
| Fixture certificate generation | `cryptography==50.0.2`, already resolved in the current root lockfile |
| Seccomp profile | Playwright JS commit `a1f35e1955976e84411f9c10358228a80b763ebe`; profile SHA-256 `cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849` |

The Python 1.65.1 wheel bundles JS driver 1.65.0. Its matching upstream seccomp
profile therefore comes from JS tag v1.65.0, not a nonexistent JS v1.65.1 tag.
Retain its Apache-2.0 licence and exact source/digest in the fixture pins file.
Implementation discovery: derive runtime profile `nima-userns-chroot-v1` from
those exact upstream bytes, adding only a `chroot` allow rule. Runtime SHA-256:
`1ec225154906ce8e797e22d7fadaff5b592d273a08774f35c627f5c940faf4b4`.
The upstream rule is conditional on Docker granting SYS_CHROOT, which conflicts
with our required cap-drop-all parent: its compiled filter blocks even a child
that obtains capabilities solely in its new user namespace. Chromium 158 calls
`sys_chroot("/proc/self/fdinfo/")` to construct its own filesystem sandbox.
Closed network-none probes reproduced child denial with the original filter and
child success with this single rule; the parent remained denied under both.
Keep the upstream file unchanged and test the exact derived delta/hash. Verify
parent chroot denial, child namespace/chroot success, UID/capability restrictions
and real browser sandbox observations before passing checkpoint A. No SYS_CHROOT
capability, host-policy edit or browser sandbox disable flag is added. This is an
explicit syscall-filter expansion for security review in the draft PR, not a
change to the browser/TLS/network boundary or permission for later stages.
Source: [Chromium credentials.cc at the selected version](https://chromium.googlesource.com/chromium/src/+/158.0.8127.18/sandbox/linux/services/credentials.cc#56).
Before launch, check the browser binary/image actually matches the wheel metadata.
Do not silently use the environment's unrelated installed Chromium.

Build the helper from Debian snapshot
`https://snapshot.debian.org/archive/debian/20261112T000000Z/`, suite `bookworm`.
Keep APT signature/TLS verification. The InRelease SHA-256 is
`77737fa4b34f2693e982cc9ee35736816c35a7778fc2d326cc1bbf5b301fe1aa`;
its main amd64 Packages.xz SHA-256 is
`9e0b5aabb2465b3d2e7a7fe27f9913846277833f7a2826e7767acccff5b588c5`.
Treat this as an intentionally frozen build feed; any later pin/feed refresh needs
a reviewed update, not a floating fallback to current mirrors.

| Helper package | Version | amd64 .deb SHA-256 |
|---|---|---|
| nftables | `1.0.6-2+deb12u2` | `966ff20ce58c17163a771c02ddbca264291408f94c512bd85dd18da0ebdbe88c` |
| iproute2 | `6.1.0-3` | `1204b29e916e836267096d0b9d778106752f821ebde0d281539008b4386d9070` |
| libnss3-tools | `2:3.87.1-1+deb12u2` | `7d4efc0ccd28edf39c9bbc108794c7b78020e99376a049c50416e429bae96a9b` |

Resolve transitive OS packages only from the same signed snapshot and record the
installed package manifest. Historical feeds may require snapshot-specific
Valid-Until handling; bind it to this exact verified metadata rather than disabling
repository signatures or TLS. No latest-image or unversioned-package substitution.

Add Playwright and a direct dev-only cryptography pin to the existing root uv dev
group. Keep runtime dependency declarations unchanged. Regenerate the hash-locked
orchestration development export because it intentionally includes all dev tools;
it receives the Python binding, not downloaded browser binaries. Browser binaries
live only in the fixture image. Freeze unrelated resolved packages during this change.

### What planning actually verified

Registry metadata confirmed both selected amd64 image digests. The downloaded
Playwright wheel matched PyPI's SHA-256 and supplied the driver/browser revisions
above. Debian InRelease signatures verified with the archive keyring from the
pinned Python image; the package index matched its declared SHA-256.

Disposable, read-only, network-none probes on Docker 29.9.2 verified:

- A root helper with only NET_ADMIN could set a socket mark; effective capabilities
  were exactly `0x1000`.
- UID 10001 with all capabilities dropped and no-new-privileges could not do so.
- With the pinned seccomp profile, the unprivileged process could create a user
  namespace, but still could not gain NET_ADMIN over its parent network namespace.

These are capability primitives, not installed nftables rules or a Chromium launch.
Gateway CONNECT/TLS/auth, NSS trust and browser sandbox operation remain untested.
The current executor had about 1.6 GB free; do not pull the large browser image
there and pretend a full launch was checked. The build preflight requires at least
8 GiB free on the Docker data filesystem; use a sufficiently sized Linux runner.
No automatic pruning of unrelated images/caches or host security relaxation.

### Concrete process and network boundary

Use two internal Compose networks with fixed test-only addresses selected from
nonoverlapping private subnets. Abort on a conflict; do not attach to the implicit
default network. An anchor holds the worker network namespace. The gateway alone
bridges worker/fixture networks, with IP forwarding disabled. Neither has Internet
egress. Build-time downloads still use the mandatory platform proxy and CA.

| Process | UID/capabilities | Access |
|---|---|---|
| Namespace anchor | 10001, none | Holds the isolated namespace, no service ports |
| Policy setup helper | 0, NET_ADMIN only | Joins that namespace, installs fixed rules/aliases, then exits |
| Collection workload | 10001, none, no-new-privileges | Shares guarded namespace, can contact only the fixed gateway TCP port |
| Independent fixture observer | 10002, none | Test-only control identity; proves canaries reachable without changing the policy |
| Gateway and fixture services | 10002, none | Their own namespaces; only explicit synthetic routes and private control mounts |

The trusted observer shares the worker namespace for comparable positive controls,
but has its own PID/container context and UID. Its exception is explicitly limited
to this fixture profile. Workloads must be unable to assume that UID, alter rules,
mount control volumes or reach the Docker socket. It is not a live deployment
exception or an Internet path. Do not ship the observer/canary aliases as production
configuration.

Install an nftables inet OUTPUT chain with a default drop policy. Accept only the
fixed gateway IPv4/TCP destination for workload UID 10001. Do not add a general
OUTPUT established-flow exemption that could reuse an observer's previous flow.
Playwright uses a local pipe, so no blanket IP-loopback allowance is needed.
Observer UID 10002 is a declared test-only positive-control exception. Disable
IPv6 explicitly in the anchor namespace and verify the effective settings.

The setup helper exits successfully before Compose starts workloads. Applications
never receive NET_ADMIN. A separate short-lived trusted helper may read kernel
policy/counters later; it does not rewrite rules during normal cases. No host
network/PID/IPC sharing, privileged container, host policy edit or mounted Docker
socket. Use private /dev/shm of 256 MiB, read-only roots and bounded tmpfs/state.

Canaries include same-network TCP/UDP/DNS targets and a synthetic metadata address
installed locally within the disposable namespace. A metadata case must never
contact a real cloud metadata endpoint. For the host-boundary case, bind a
synthetic HTTP canary directly to the dedicated Docker bridge address, never
0.0.0.0/public interfaces. Implementation discovery: the Docker-published port on
an internal bridge refused the observer connection despite a reachable direct
canary; confirmed by an isolated two-container probe. The trusted host controller
therefore owns this unprivileged listener and its in-memory counters, while other
fixtures use container UID 10002. It requires the controller and Docker daemon to
share the host network namespace; no container uses host networking. Verify the
positive control, exact binding and controller-side delivery counts before any
negative case. Gateway/browser control interfaces are never exposed as host TCP services.

### Gateway, TLS and observation choices

Use Envoy's HTTP/1 CONNECT termination to a static fixture upstream, not dynamic
DNS forwarding or a custom Python tunnelling server. Exact-authority/port/method
RBAC is enforced, not shadow mode; no wildcard or raw-IP destination is allowed.
Fixture-only Basic proxy credentials are generated at runtime. Configure a bounded
407/Proxy-Authenticate challenge for authentication denial so Chromium can respond;
prove both HTTPX and browser behaviour rather than assuming a 403 is sufficient.
Validate the bootstrap with the pinned Envoy binary before starting it.

TLS remains end-to-end between client and fixture; the gateway does not intercept
certificates. Generate CA/server keys privately with cryptography, publish only
the CA certificate to the workload, and use SSLContext trust for HTTPX. Import
that CA into Chromium's private NSS database with certutil. Chromium M146+ defaults
to `$HOME/.local/share/pki/nssdb`; verify the selected process's actual private home
and database. Do not rely on system CA changes, ignore_https_errors or sandbox
disable flags. Launch full Chromium with `channel="chromium"` and
`chromium_sandbox=True`, with first-run/background networking disabled.

Keep fixture keys, generated gateway credentials/config and observer control
sockets on private mounts absent from the worker. Use separate public-CA mounts.
No unfiltered gateway access logs, configs, HARs or raw exception values enter CI
logs. Gateway admin statistics, if needed, use an observer-only Unix socket and
allowlisted numeric counters; no admin TCP listener. Counters reset/read through
private control channels which the workload cannot reach or spoof.

### Cases, receipts and executable interfaces

Freeze at most 30 named cases from the approved matrix. Each negative case has an
observer positive control, a stable active-policy identity and counter evidence.
Prove proxy-variable removal, trust_env=False and NO_PROXY cannot bypass rules;
cover real browser subresources, DNS/UDP/QUIC/STUN, IPv6 disabled mode, host/metadata
targets, denied redirects, gateway failure, bad auth and bad TLS. Distinguish a
blocked delivery from a dead fixture or a successful UDP send without delivery.

The host-side runner generates its own UUID/project name and private state root,
uses structured Docker CLI arguments and tracks exact resource IDs/ownership.
Cleanup may remove only those resources. The runner can use the local Docker
socket; no test container receives it. Missing disk/kernel/sandbox prerequisites,
timeouts, absent cases or incomplete controls fail nonzero without skips.

First-party code lives under `src/nima/egress/`. Ordinary unit files use
`tests/test_source_worker_*.py`. Real Docker tests use the explicitly selected file
`tests/source_worker_integration.py`, which default pytest discovery does not select
but strict mypy/Ruff still cover. The dedicated CI job must run it; no skip marker,
weakened ordinary check or pretend green result substitutes for this gate.

Proposed commands after implementation:

```bash
uv run --frozen python -m nima.egress.runner --profile fixtures \
  --output-dir data/source-worker
just source-worker-check
uv run --frozen pytest tests/source_worker_integration.py
just check
just audit
```

The just recipe selects the explicit integration file, which exercises the same
fixed-profile runner once per required scenario. It does not redundantly run a
second normal matrix. No live mode, arbitrary target URL, collector integration or
source job is exposed. The runner separates image
builds from runtime's 10-minute deadline. Keep 15-second attempts, one attempt per
case, 1 MiB responses and 64 KiB receipts. Serialize cases; one Chromium instance.

Receipts preserve fixture scope, actual image/policy identities, kernel/workload
observations, counter/control results and UTC times. The report is bounded, private
and published atomically after reconciliation. Keep internet_egress_verified,
investigator_ip_protection_verified and production_ready false. Packet enforcement
does not authenticate the host or prove a remote public IP. No GEMI archive format,
SQL write, identity acceptance or model output is involved.

### Ordered delivery and review checkpoints

E1 dependencies → E2 pins/helper → E3 sandbox prerequisite → checkpoint A →
E4 policy/receipts → E5 controlled fixtures → E6 gateway TLS/auth → checkpoint B →
E7 namespace enforcement → E8 HTTPX cases/runner → E9 browser cases → checkpoint C →
E10 failure/mutation checks → E11 complete CI gates → E12 runbook/review PRs.

Task acceptance criteria and roughly 3–5 files per task are in `tasks/todo.md`.
Use focused failing tests before behaviour, small commits, sequential execution
and no delegation. Stop at a failed feasibility checkpoint; do not silently change
the approved stack or weaken sandbox/TLS/network controls to proceed.

Add `source-worker-egress` as a dedicated `ubuntu-24.04` CI job, initially proving the
image/sandbox prerequisite and extended to the complete matrix by delivery. It
never claims deployed IP protection. Keep quality and orchestration-compose jobs
unchanged in purpose. Use a 25-minute job bound for builds, the complete integration
suite and cleanup; each controller retains its 600-second budget. No live source
secrets. Final exact-head local/hosted evidence,
clean audit and the 90% coverage floor are required before marking delivery ready.
Add the new check to the proposed main/dev ruleset payload. The repository is now
public, but the current active ruleset targets no branches and effective rules for
main/dev are empty. This work updates the payload/instructions, not account
settings or billing; public visibility does not establish server enforcement.
Split large delivery diffs into dependent PRs and leave dependents draft until
their parents are merged/retargeted; human merges only.

### Risks, limits and remaining review

The original sandboxed-Chromium, NSS trust and Envoy CONNECT/auth feasibility
checks have now passed on supported hosted runners. The current small executor
cannot establish those physical fixture results locally: PostgreSQL is unavailable
and Docker's data directory is inaccessible. Preserve that distinction, the final
exact-head CI gate and the separate deployment/public-egress verification gate.

There is no need for a GEMI key, Webshare account or VPN credential in this work.
No source access, hosting purchase or deployment is authorized by this plan.
Provider permission and deployment-specific public-egress verification remain
separate gates. Existing manual intake and the original ingestion/identity roadmap
continue independently.

Official sources: [Envoy CONNECT](https://www.envoyproxy.io/docs/envoy/v1.40.2/intro/arch_overview/http/upgrades),
[RBAC](https://www.envoyproxy.io/docs/envoy/v1.40.2/configuration/http/http_filters/rbac_filter),
[local replies](https://www.envoyproxy.io/docs/envoy/v1.40.2/configuration/http/http_conn_man/local_reply),
[Playwright Docker](https://playwright.dev/python/docs/docker),
[Chromium headless mode](https://playwright.dev/python/docs/browsers#chromium-new-headless-mode),
[NSS trust](https://chromium.googlesource.com/chromium/src/+/main/docs/linux/cert_management.md),
[nftables UID metadata](https://wiki.nftables.org/wiki-nftables/index.php/Matching_packet_metainformation).

## Completed increment: private manual Publicity evidence intake

Status: **implementation approved**, 2026-11-12, by the user's “Yes”. The user approved
`docs/sources/gemi-publicity-fallback.md`, including protection of the investigator's
home/office IP. Execute the reviewed plan and task acceptance criteria.
This extends the existing source-ingestion roadmap. Preserve
the older plans and incomplete access, registry-comparison and administration tasks.

### First delivery and boundaries

Deliver an entirely offline CLI for importing and independently verifying a small
bundle of manually saved public evidence. It needs no GEMI key, browser dependency,
database migration, Prefect dispatch or outbound connection. This is verified
manual-evidence staging, not registry-field extraction or company verification.

Start with PDF, PNG and JPEG files, stored as opaque evidence. Signatures constrain
declared file types; they do not establish that a document is valid or authentic.
Do not render/open files, execute scripts, OCR documents, follow links or fetch URLs.
HTML, HAR, browser sessions and archives are unsupported in this first delivery;
HTML capture requires a separate session-data and safe-display contract.

Manual acquisition must happen through a remote browser or a separately verified
protected VPN path. The offline importer records the operator's declared capture
context; it cannot prove which IP the source saw or authenticate supplied files.
Remote browsing, source egress enforcement and leak testing remain later milestones.
No hosting/proxy purchase or deployment is authorized by this plan.

### Implemented offline interfaces

```bash
uv run --frozen python -m nima evidence intake publicity \
  --request-id 00000000-0000-4000-8000-000000000001 \
  --manifest /private/capture/input.json \
  --input-dir /private/capture \
  --archive-dir /private/publicity-evidence

uv run --frozen python -m nima evidence verify \
  00000000-0000-4000-8000-000000000001 \
  --archive-dir /private/publicity-evidence
```

The UUID is synthetic. Paths denote operator-selected private local directories.
The manifest is versioned JSON, capped at 64 KiB and at ten records. Each record
supplies a GEMI number, relative file path, declared media type, original public
source URL, timezone-aware claimed capture time, capture method and declared
protected capture context. Preserve original values and normalized representations;
unknown JSON keys, duplicate keys and inconsistent declarations fail visibly.

Apply existing positive ASCII-decimal GEMI-number rules without inventing a fixed
number length; preserve supplied text and label the number as operator-supplied.
Use only HTTPS metadata URLs on `publicity.businessportal.gr`, with no userinfo,
query, fragment or nondefault port in this version. Do not resolve or fetch them.
Other document hosts need an explicit later source contract. Maximum URL length is
2,048 characters. Capture/import times remain distinct; supplied dates are claims.

Allow one evidence file per record, at most 8 MiB each and 50 MiB total. Read from
regular files beneath the selected input directory through no-follow directory
descriptors; reject symlinks, traversal, devices, FIFOs and changing inputs. Stream
bounded copies into private staging, hash the bytes copied and never reread an
unchecked pathname for publication. Do not infer a company's identity from a file
name, claimed metadata or successful file-format checks.

### Archive and replay decisions

Keep `source_family=gemi`, `acquisition_channel=publicity-manual` and a distinct
manual archive marker/version. The existing API verifier/importer must reject it.
Reuse established descriptor-based publication patterns from
`src/nima/identity/artifacts.py`; do not weaken or broadly refactor current archives.

Use owner-only directories/files (0700/0600), an archive-local Git exclusion,
content-addressed blobs and a canonical immutable completion manifest. The manifest
binds the request UUID, frozen input metadata, original-byte hashes, importer
version and actual import time. It does not add the investigator's IP or local
absolute paths. No arbitrary notes, request headers or session-state exports are
part of the accepted input contract.

Publish the completion manifest only after all blobs are durably stored. Concurrent
same-request publication uses an atomic no-clobber operation: matching immutable
content reuses the first accepted bundle; conflicting content fails without
replacement. The first import timestamp remains stable on replay. A crash before
publication can leave unreferenced blobs but never a completed partial bundle.
The read-only verifier reconciles every declared reference and byte bound; a
stored digest is not trusted without reading and hashing its referenced bytes.

CLI output exposes only request UUID, version, counts and fixed status/reason codes.
Exit 0 means evidence was staged or integrity verified, not identity established;
2 means invalid configuration/input; 1 means archive/integrity failure; 130 means
interruption. Exclude supplied paths, URLs, IDs and document text from errors.
No browser/collect subcommand, automatic API fallback or active schedule is exposed.

### Dependency order and review checkpoints

1. **P1: input policy.** Pure types, strict bounded manifest decoding, protected
   capture declarations, identifiers, URL/path/media validation and synthetic tests.
2. **P2: private intake.** Bounded descriptor-based file copying, content hashes,
   immutable publication and duplicate/conflicting-request tests.
3. **Checkpoint A.** Review archive/metadata limits, original-byte retention and
   absence of outbound work before exposing a public command.
4. **P3: independent verifier.** Read-only reconciliation, missing/corrupt/unsafe
   archive rejection, unchanged replay and concurrent-publication tests.
5. **P4: CLI.** Lazy command dispatch, help, redacted outcomes and end-to-end
   synthetic intake/verify tests, including explicit no-network guards.
6. **Checkpoint B.** Review the usable offline path and confirm API import remains
   a distinct channel with no accepted identity or SQL writes.
7. **P5: failure verification.** Actual process termination before/after publication,
   races, bounded hostile inputs and a meaningful integrity-guard mutation check.
8. **P6: review and delivery.** Capture runbook/evidence, complete quality/audit
   checks and publish a private implementation PR as StamKavid. Human merge only.

Every code task begins with focused failing tests and ends with its relevant
passing checks and a small commit. Task details are in `tasks/todo.md`; no task
requires more than about five files. Execute sequentially; no agent delegation.

### Verification and risks

Future focused tests are named in the task list; no test results are claimed for
unimplemented code. The repository-wide gates remain `just check` and `just audit`,
with the existing disposable local PostgreSQL fixture for the full suite and the
90% combined line/branch coverage floor. Government services are never CI fixtures.

| Risk | Mitigation and limit |
|---|---|
| Forged or mislabelled manual evidence | Preserve supplied claims and bytes; integrity is not origin, identity or IP verification |
| Input/path substitution or crash | Descriptor-based reads, fixed bounds, immutable completion and real interruption/race tests |
| Imported HTML makes local source requests | Accept only opaque PDF/PNG/JPEG; no rendering, live embeds or automatic link following |
| Operator captured directly from home | Require declared protected capture context and a clear runbook; actual egress requires separate verified remote infrastructure |
| Mistaking this slice for the full fallback | Release notes list pending UI capture, network isolation, extraction and SQL integration explicitly |

Subsequent milestones remain gated: controlled-endpoint egress tests and remote
manual-browser setup; conditional offline UI adapter with pinned dependencies;
live UI pilot only after permitted access is established; explicit channel-aware
registry assertions/import; shared SQL source guard and optional Prefect scheduling.
The original GEMI key/pilot and registry-comparison work remain pending separately.
The offline intake/verification slice is implemented. Final quality and hosted
delivery checks are recorded in docs/verification/publicity-evidence.md and the PRs.
Delivery is split into design, archive-core and CLI/failure-verification PRs to
keep each dependent review below roughly 1,000 changed lines. No automatic merge.

## Previous increment: repository controls and just

The user requested cleanup of merged PR branches, protected main/dev branches,
replacement of make with just, and an explanation of Python 3.12 versus 3.14.
These operational changes are explicitly authorized; preserve all quality gates.

1. Verify refresh PR merges, create dev from main, inspect GitHub controls and
   attempt native settings. Record actual plan/permission blocks without changing
   repository privacy or purchasing a plan.
2. Pin/install official just, port every active recipe and CI invocation, and
   preserve archived command evidence and the immutable skill snapshot.
3. Test a conservative merged-head policy and actual Git deletion leases; add a
   trusted-default-branch cleanup workflow. Preview then clean verified old heads.
   Keep main/dev, protected heads, unmerged/new work and open PR dependencies.
4. Check/audit locally and in hosted CI, publish matching bootstrap PRs for main
   and dev, and supply an importable protection ruleset/manual setup instructions.
   Human merges only; actual protections require a supported plan/admin access.
5. Continue the application roadmap with a bounded offline registry comparison
   spec. The runtime remains 3.12 until a separately validated compatibility change.

## Completed increment: bounded KIMDIS refresh

The user approved docs/sources/kimdis-refresh.md by requesting continuation on
2026-11-12. Implement local/offline tests only; no policy or live poller activation.
Preserve previous completed plans and unrelated pending access/control tasks.

1. Test pure policy validation and Athens calendar/date selection (policy module,
   tests). Include DST, clipping, overlap and bounded oldest-gap catch-up.
2. Add migration 0006 and real-SQL policy lifecycle/frozen cycles (storage module,
   migration loader, SQL tests). Persist cycle intent before idempotent request
   creation; UUID5 child IDs survive a crash before child-map insertion.
3. Add bounded SQL reconciliation/inspection (separate progress module/tests).
   Only evidence-complete children advance contiguous coverage; unknown or
   unresolved work blocks a later cycle without fresh request budgets.
4. Add/test coordinator dispatch and serialized enable/pause against real Prefect.
   Serve coordinator and existing collector in one runner without waiting for
   children. Schedules are created inactive and explicitly activated only in tests.
5. Expose redacted CLI, update migration assertions/Compose CI and document usage.
   Verify real SIGKILL, pause races, changed reobservations and populated-v5 upgrade;
   mutate a guard, review five axes, run checks/audit and publish private PRs as
   StamKavid. Human merges only, no production deployment.

Work is sliced by tested boundaries; each slice uses red/green focused tests
before its implementation and commits. No new dependency or relaxed check.

## Completed increment: local Prefect KIMDIS workflow

The user approved docs/sources/kimdis-orchestration.md and selected self-hosted
Prefect on 2026-11-11. SQL evidence remains authoritative. No live provider calls.
PRs #22–#26 are merged into main at e80e23f; the tree matches tested 749b9ee.
The next source-refresh spec is separate; implementation planning follows review.

1. Add/test migration 0005 and an engine-independent request/dispatch ledger.
   Verify immutable parameters, stable run binding, concurrent submission, leases,
   persistent collection budgets, redacted inspection and populated-schema upgrade.
2. Add/test a stable prepare/resume adapter, per-provider source lease and request
   guard invoked before every provider attempt (including resume verification).
   Add run-scoped projection without changing global CLI behavior.
3. Pin/install Prefect and implement local flow/tasks, dispatch and CLI integration.
   Require an explicit self-hosted API/deployment; no ephemeral/cloud fallback.
4. Exercise real local server/process-runner delivery, duplicate/unknown dispatch,
   exceptions and actual SIGKILL before task acknowledgement after SQL commits.
   Retry/redispatch the same domain request and prove bounded repeat safety.
5. Pin local Compose services and required CI integration; retain all quality gates.
   Review five axes, mutate an identity/budget guard, run checks/audit and publish
   reviewable private stacked PRs as StamKavid. Human merges, no deployment.

Each task has failing tests before implementation, then its focused real-boundary
checks. Dependency changes may require a large generated lockfile; keep it separate
from domain behavior for review. Preserve all previous plans and pending access work.

## Previous increment: offline GEMI evidence persistence

The user approved docs/sources/gemi-persistence.md after reviewing the saved
proposal. Delivery branches are `feature/gemi-archive-verifier`, followed by
`feature/gemi-registry-storage`; no live key or API call.

1. Test and implement a bounded read-only archive verifier. Reconcile terminal
   manifests/attempts/outcomes and regenerate assertions from hash-verified bodies.
2. Test additive migration 0004 and one atomic import transaction on PostgreSQL 17.
   Preserve response versions/observations; serialize replay and verify reuse.
3. Test/expose `gemi import RUN_ID --archive-dir PATH` with redacted outcomes and
   no key/network dependency. Keep KIMDIS SQL/outbox behavior unchanged.
4. Verify real SIGKILL before/after commit, concurrent/rejected replay, populated
   v3 upgrade, bounds and archive immutability; mutation-test an integrity guard.
5. Complete five-axis review, checks/audit, and two private linked PRs as StamKavid
   with hosted CI. Retarget the dependent PR to main after #20 merges. Human merge
   only; live profile compatibility deferred.

Pure verifier tests precede SQL tests, then CLI/recovery. Use synthetic collector
archives and existing real PostgreSQL fixtures. Each task changes about five files;
keep validation separate from transaction orchestration and preserve prior plans.

## Previous increment: bounded GEMI profile evidence

PR #17 is merged (`1f45c70`); docs/sources/gemi.md is approved. Build on
`feature/gemi-profile-collector`, with no database/graph writes or new dependency.

1. Write failing pure-profile tests. Implement strict exact JSON decoding,
   requested registry identity, nullable fields, versioned KAD assertions with dates
   and existing field pointers. Preserve partial profiles and unknowns explicitly.
2. Write failing HTTP/archive tests. Implement explicit-ID/key validation before
   archive creation, bounded sequential GETs, pending/finished manifests, retry/
   rate/deadline/body bounds, raw-before-transform and visible 404/quarantine states.
3. Expose the explicit GEMI CLI and verify credential/error redaction. Test actual
   process termination during a request and at manifest publication boundaries.
4. Mutation-test an identity/budget guard, review five axes, run checks/audit and
   publish one private main-targeted PR as StamKavid with hosted CI. Human merge only.

Pure tests precede collector tests; the CLI depends on both verified boundaries.
Use synthetic fixtures and HTTPX MockTransport; record that no live profile/API-key
validation occurred. Reuse archive and public clock/retry utilities, keeping the
KIMDIS-specific SQL/outbox unchanged. First-release runs are fresh, archive-only
staging; no automatic resume or accepted company identity is implied.

## Previous increment: offline identity assessment

PR #15 is merged (`33115f0`); the user approved SPEC-entity-resolution.md.
Build the first release on `feature/identity-assessment`. No registry calls,
schema/dependency changes, automatic identity links or graph work are included.

1. Test and implement pure identifier assessment and source-scoped candidate
   groups. Keep raw fields, unsupported cases, namespace boundaries and issues.
2. Test and implement one repeatable-read, read-only SQL cohort. Require receipts
   and facts for all accepted observations; bound rows and raw input bytes before
   fetching labels. Preserve coverage, unknown suppliers and exact evidence.
3. Test and implement bounded canonical reports with private atomic publication.
   Use directory descriptors and no-follow opens; no-clobber publication and
   byte-verified reuse. Add the explicit `identities assess` CLI with redacted output.
4. Verify snapshot consistency, read-only operation, file hazards and real process
   interruption before/after publication; mutation-test a meaningful guard.
5. Run checks/audit, offline cached reconciliation and five-axis review; push one
   private main-targeted PR as StamKavid and verify hosted CI. Human merge only.

Each task depends on the preceding tested boundary. Focused tests live in
tests/test_identity_policy.py and tests/test_identity_report.py. Preserve older
plans/tasks. The report includes every occurrence, not a resolved company list;
format checks and reported country do not verify identifier jurisdiction.

## Previous increment: reported contract participation

PR #13 is merged (`14063bf`). Continue the approved ingestion/outbox contract on
`feature/participation-projections`. Build one local, bounded projection consumer;
entity resolution, graph databases, models and deployment remain later work.

1. Extend the accepted spec; define immutable versioned contract facts, party
   occurrences and per-observation receipts in additive migration 0003.
2. Write failing pure-mapping and real PostgreSQL tests. Preserve exact money,
   Greek text, unknown versus empty suppliers, repeated observations and evidence.
3. Implement bounded `outbox project` transactions: lock one event, validate,
   project and acknowledge together. Versioned receipts govern replay, including
   already acknowledged events when a future projection version is introduced.
4. Verify locked-event retries, concurrent consumers, poison-event rollback and
   actual process termination before/after commit. Run a guard mutation experiment.
5. Review five axes, run checks/audit, and publish one unmerged main-targeted PR
   after privacy, attribution and hosted CI verification. Record measured results.

Values belong to contract versions, never individual supplier edges. Every party
is a source-local occurrence, not a resolved business. A run-scoped evidence view
exposes reported relationships without allocating money. A batch cursor is local
to one invocation; locked or late-committing lower IDs remain eligible next time.
Invalid events stop visibly and stay pending; no automatic skip or dead-letter
policy. No external delivery or exactly-once cross-system guarantee is claimed.

## Previous increment: safe database-run resume

PR #12 is merged (`c80efc5`). Continue the accepted ingestion recovery contract on
`feature/safe-run-resume`. Add explicit `runs resume RUN_ID`, using the original
query, limits, versions and archive. No new dependency or schema migration.

1. Add bounded hash-verified archive reads; session advisory leases for both fresh
   and resumed managed runs; claim a new writer token under the run row lock.
2. Restore coverage from committed SQL page evidence. Replay the earliest finished
   successful collect response for the next uncommitted page, preserving its time.
   Revalidate all committed pages and that pending page against current source
   metadata/ordered full-record fingerprints before adding pages to an incomplete run.
3. Continue through the same collector acceptance/retry path, without duplicated
   observations/outbox. Journal verification requests separately. Each explicit
   invocation gets a fresh original time/retry budget; the total page limit stays fixed.
4. Expose CLI only after tests cover real SIGKILL/restart, pending-body replay,
   changed sources, missing/corrupt archives, active-worker exclusion and stale-token
   fencing. Complete archived runs reconcile without source requests.
5. Run checks/audit, review, and open one unmerged PR directly to main. Keep original
   file manifests/JSONL as initial-invocation projections; resumed truth is SQL.

Offset revalidation detects observed drift, not snapshot isolation. Unknown
historical started attempts remain unknown; distinguish them from current-owner
pending requests. Sessions hold an advisory lock while running; writer tokens
fence stale writers if the lock connection disappears. Drain older pre-lease
workers before using resume. Production deployment remains outside this change.

## Previous increment: durable HTTP collection and run inspection

PR #11 is merged into main (`65b08ea`). On `feature/durable-kimdis-runs`, connect
the existing collector to the accepted PostgreSQL persistence contract. First
ship fresh database-backed collection and read-only inspection. Keep HTTP resume
hidden until worker ownership, pending-response replay, drift verification, and
multi-page restart have been verified in a following increment.

1. Add migration 0002 without changing 0001: managed run settings/ownership/status,
   durable HTTP attempts, and per-page source IDs for honest coverage counts.
   Generalize checksum migration replay and test upgrading an existing v1 database.
2. Journal attempts before HTTP and finish their metadata after bounded body archival.
   Connect accepted pages to the page transaction; guard managed pages with owner
   identity and persist final state only after all page commits and reconciliation.
3. Add opt-in `ingest kimdis --database` and read-only `runs show RUN_ID`. Use only
   NIMA_DATABASE_URL for connection configuration; redact driver errors. Missing or
   outdated schemas fail before HTTP. Migration remains explicit via `db migrate`.
4. Test HTTPX plus real PostgreSQL, including retries, quarantine, incomplete runs,
   failed SQL, missing/corrupt evidence, ownership guards, and real SIGKILL during
   an HTTP request and after a page commit. Inspection reconstructs counts from SQL
   and never treats saved running state as proof of a live worker.
5. Run checks/audit, self-review, and open one unmerged PR directly to main. No new
   dependency or relaxed check is needed. Confirm private hosting and attribution.

## Previous increment: atomic archived-page persistence

PR #10 is merged into main (`e2314cd`). Continue the already-approved
PostgreSQL portion of SPEC-source-ingestion.md on `feature/postgres-page-persistence`.
This slice persists one archived KIMDIS page atomically: versions, observations,
quarantine, pending outbox events, and the next-page checkpoint. It does not expose
HTTP resume or claim full ingestion completion. Production hosting remains deferred.

1. Extend the accepted spec with transaction/schema details and review invariants.
   Choose direct Psycopg 3 SQL and a numbered, checksum-verified additive migration.
2. Write failing tests against disposable real PostgreSQL 17 databases. Add the
   isolated service to CI without weakening existing quality or coverage gates.
3. Implement migration and source-content fingerprints, then persist one page in
   one transaction. Prove A→B→A history, unchanged observations, exact money,
   idempotent replay, changed-page rejection, quarantine, and gap rejection.
4. Kill a real child worker before/after page commit and verify rollback/durable
   replay using a new connection. This proves page persistence, not HTTP resume.
5. Review, run make check/make audit, push as StamKavid to the private repository,
   and open one PR targeting main directly. Do not merge/deploy automatically.

A run row lock serializes page commits. A page identity is (run UUID, page number);
its first committed body cannot be replaced. Source-content versions exclude page
position/evidence so unrelated neighboring changes cannot create false versions.
Observation identity is (run, page, original record index); outbox references that
identity and is created in the same transaction. Filesystem objects precede SQL;
a failed SQL transaction may leave an unreferenced blob but never a committed
checkpoint whose page transaction rolled back. Recovery must verify archived bytes.

## Previous increment: bounded KIMDIS evidence collection

PR #5 was merged by the user on 2026-11-08. Build the next slice of the accepted
ingestion spec on `feature/kimdis-evidence-collector`: a CLI that collects one
explicit date window, preserves completed HTTP response bodies before parsing,
normalizes records, and reports coverage and failures. PostgreSQL history,
durable work handoff, and crash-resume remain the following increment.

### Implementation order and acceptance

1. **Page contracts:** decode each response once; validate pagination and preserve
   per-record quarantine/evidence locations. Existing normalization behavior stays
   compatible. Verify: source/page behavioral tests.
2. **Archive:** content-addressed immutable bodies, private directories/files,
   atomic run manifests, and derived normalized/quarantine JSONL artifacts. An
   existing corrupt blob or unrelated directory must fail visibly. Verify: real
   filesystem tests for reuse, corruption, privacy, and path safety.
3. **HTTP collection:** official fixed endpoint, date/buyer filters, request-rate,
   response-size, retry, page, and time budgets. Honor bounded Retry-After; do not
   follow redirects. Archive bounded completed responses including HTTP errors.
   Verify: HTTPX MockTransport tests for pagination, retries, errors, and budgets.
4. **CLI and coverage:** expose `python -m nima ingest kimdis` with a JSON summary.
   Validate options before network access. Successful raw collection with bad rows
   reports quarantine and exits nonzero; inconsistent/duplicate pagination never
   claims completeness. Verify: command tests and a bounded live one-day probe.
5. **Review and publication:** run `make check` and `make audit`, review the diff,
   push as `StamKavid` to the private repository, and open unmerged dependent draft
   PRs for page/archive, HTTP collection, and CLI/documentation. Each gets CI.

### Boundaries and evidence

The archive stores decoded HTTP entity-body bytes before JSON parsing, not a
capture of compressed wire bytes. Hash references must resolve to those exact
archived bytes. Original bodies and derived artifacts remain outside Git.
Manifests record collection and normalization completeness separately. They are
run evidence, not a substitute for transactional PostgreSQL checkpoints. A new
run may reuse body blobs; automatic resume is not exposed in this slice.

Use HTTPX with verified TLS and inherited proxy/CA settings. Documentation:
https://www.python-httpx.org/quickstart/#streaming-responses and
https://www.python-httpx.org/advanced/timeouts/ . Official source contract:
https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help . HTTPX is the only new
runtime dependency; structured ingestion still has no model dependency.

## Previous completed increment: Nima investigation foundation

The user reaffirmed the company/public-spending investigation concept, supplied
the original architecture as the project brief, and created `StamKavid/nima-ai`.
Keep the ingestion-first sequence while making graph, ML, AI, and investigative
insights explicit downstream capabilities. The election concept is a separate
idea and has no implementation tasks here.

GitHub authentication works, but the repository was initially public and the
integration cannot change visibility (403). Do not push before independently
confirming private visibility. Earlier private-hosting authorization remains in
effect. Keep local changes on `feature/nima-investigation-foundation`.

## Ordered increments

1. Install the complete skill snapshot and record provenance.
2. Establish locked Python tooling and behavioral tests for snapshot integrity.
3. Add CI, security checks, review conventions, and architectural context.
4. Rename first-party package metadata to `nima-ai` and import namespace to `nima`.
5. Implement one contract-normalization slice with exact money, unknown-value
   preservation, source references, and evidence pointers. Use standard-library
   JSON/Decimal; introduce no model dependency into the collection path.
6. Document graph ontology, model candidates, detector coverage prerequisites,
   and the investigation workflow, with acceptance gates for each stage.
7. Verify private GitHub visibility, connect the remote, push the existing
   bootstrap main and the feature branch, then open a draft PR. Run hosted CI
   and verify available branch controls. Never merge the PR without authorization.

The task state is in `tasks/todo.md`. Remote controls and hosted CI cannot be
marked complete from local evidence alone.

## Risks

| Risk | Handling |
|---|---|
| GitHub credential fails | Continue local work; use the authorized GitHub integration once connected |
| A skill update changes operating rules | Pin the source revision, preserve full references, and review updates separately |
| Bootstrap checks look like product validation | State exactly which behavior is tested; ingestion has its own acceptance criteria |
| Private repository plan lacks branch rules | Verify support and report limitations; never claim protection from configuration alone |

## Source-normalization acceptance

- Decode source decimals without a binary-float intermediate; reject duplicate
  keys, non-finite amounts, malformed shapes, and out-of-range record indexes.
- Preserve missing bidders/suppliers, leading-zero identifiers, multiple supplier
  participation, cancellation state, and raw source timestamps.
- Attach the original response hash and record JSON pointer. Preserve the meaning
  of source reference fields; do not infer ownership, transfers, or bid collusion.

Verify with focused behavioral tests followed by `make check` and `make audit`.
The raw collector, archive, database, checkpointing, and crash-recovery guarantees
remain open work; this increment does not satisfy the full ingestion spec.

## Next slices

KIMDIS HTTP collection and bounded pagination → raw archive → PostgreSQL
observations/versions/outbox → restart/reconciliation tests → document evidence →
Diavgeia linking → GEMI enrichment. See `docs/architecture.md` for the later graph,
model, and insights roadmap. Stage completion requires its acceptance tests.
