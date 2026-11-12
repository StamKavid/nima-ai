# Delivery plan

## Current increment: private manual Publicity evidence intake

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
