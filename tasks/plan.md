# Delivery plan

## Current increment: reported contract participation

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
