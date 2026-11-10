# Spec: KIMDIS contract ingestion

Module: `source-ingestion` in `CAPABILITIES.md`.

The implemented source in this specification is KIMDIS. The proposed source-specific
[GEMI registry evidence contract](docs/sources/gemi.md) supplements this provider
module and requires review before its first credentialed connector is implemented.

Status: staged direction reaffirmed by the user on 2026-11-08 through the supplied
architectural brief. Implement the contract-normalization slice first and keep
collection, persistence, and durability as later verified slices. This spec's
full acceptance criteria remain open until the complete collector meets them.
The bounded collector now supports opt-in PostgreSQL transactions, durable HTTP
attempts and pending outbox work, plus read-only run inspection. HTTP resume is
explicit and verified separately from downstream work delivery.

## Objective

An investigator can collect KIMDIS contract metadata for an explicit, inclusive
date range and inspect a reproducible record of the evidence, collection
coverage, and revisions. Restarting collection must not silently lose pages or
duplicate logical contracts.

The first slice covers the contract endpoint only. PDFs, other procurement
stages, Diavgeia linking, GEMI enrichment, identity matching, graph projection,
models, and the browser UI are subsequent separately reviewed increments.

## Assumptions

- The first users are journalists, independent investigators, and researchers.
- Python 3.12 and PostgreSQL are the initial implementation stack.
- A local content-addressed filesystem archive is sufficient for development;
  production object-storage and retention choices are decided before deployment.
- Collection requires no LLM, embedding service, or paid data source.
- Government publication frequency constrains freshness. KIMDIS documentation
  describes daily metadata/file updates, not a live transaction stream.
- The first pilot is bounded by dates and optionally public-buyer IDs. It does
  not claim complete coverage of Greek business activity or tax compliance.

## Verified source contract

- Official documentation: https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help
- Read-only search: `POST /khmdhs-opendata/contract?page=0`.
- Request body: `dateFrom` and `dateTo` in `YYYY-MM-DD`; optional buyer filters.
- Response: `content`, `number`, `size`, `last`, `totalPages`, and `totalElements`.
- Identity: `referenceNumber` is the source ADAM. Preserve it as text.
- References: retain fields such as `auctionRefNo`, `prevReferenceNo`,
  `noticeReferenceNumber`, and payment references with their source semantics.
- Search windows are limited to 180 days by current documentation. Split larger
  requested ranges explicitly; never accept silent truncation.
- Current documented rate limit: 350 requests/minute. Start conservatively at
  60 requests/minute or lower; make this configurable and honor `Retry-After`.
- License: official documentation states CC BY 4.0. Preserve source attribution.

The live feasibility probe on 2026-11-08 requested records registered on
2026-11-06. The API reported 1,118 records over 23 pages. Only the first 50 were
inspected. All 50 contained supplier lists and net amounts; bidder count was
populated in 3. This is a feasibility sample, not a completeness benchmark.

## Public command contract

Existing bootstrap commands, executable now:

```bash
make setup
make check
make audit
```

Implemented bounded command (see README for limits and exit codes):

```bash
uv run python -m nima ingest kimdis \
  --from-date 2026-11-06 --to-date 2026-11-06 \
  --archive-dir data/raw
```

Database-backed inspection (NIMA_DATABASE_URL required):

```bash
uv run python -m nima runs show RUN_ID
```

Explicit managed-run resume (original query/limits and NIMA_DATABASE_URL):

```bash
uv run python -m nima runs resume RUN_ID
```

The PostgreSQL connection is configured through the environment, never a CLI
argument likely to be logged. Commands emit a run ID and a final structured
summary. An incomplete or failed collection exits nonzero. A successful HTTP
response alone does not make a collection successful.

## Pipeline

### Local participation projection (next accepted ingestion slice)

`outbox project --max-events 100` uses NIMA_DATABASE_URL and an explicitly migrated
schema. Accept 1–1,000 events per invocation. Each event transaction locks its
outbox row with SKIP LOCKED, reads the immutable normalized version, writes a
versioned contract fact plus buyer/supplier occurrences, records a versioned
observation receipt, then acknowledges the event. All effects commit together.
Receipts, rather than delivered_at, determine eligibility for a projection
version; future versions can replay previously acknowledged observations.

One contract version carries its exact numeric amounts once. Occurrences retain
source order, original Greek text and identifiers without resolving identity or
allocating money. Null suppliers mean unknown; an empty list means reported empty.
A maximum of 1,000 suppliers bounds fan-out; larger records fail visibly, without
truncation. Unsupported normalizers or malformed persisted records also remain
pending. Stop on failure, preserve earlier committed events and emit only a
redacted reason, event ID and processed count. A pending bounded batch exits zero;
its summary includes remaining work as a snapshot, not a freshness guarantee.

Immutable projection facts and receipts coexist by version. A deterministic hash
detects changed mappings without a projection-version bump. A reported-edge view
joins receipts to observations, run state and original page hash/record pointer;
it deliberately contains no monetary columns. Queries must choose run and
projection version, because repeated observations are evidence, not new contracts.
No latest-state selection, company identity, ownership or wrongdoing is inferred.
The existing delivered_at marks first successful local projection, not delivery
to an external graph, queue or service. New consumers need their own receipts.

### Collection

1. Validate dates and configuration before any network request. Establish a run
   containing the exact query, connector version, and explicit window bounds.
2. Fetch one page using bounded timeouts and retries. Retry transient transport
   failures, rate limits, and selected server failures within a fixed retry
   budget. Permanent errors remain visible rather than entering an infinite loop.
3. Archive the original bytes before transformation. Record SHA-256, content
   type, retrieval time, redacted request metadata, status, and source attribution.
4. Validate the envelope and preserve all original fields. Decode monetary JSON
   values using Decimal rather than a binary-float intermediate.
5. Normalize contract identity, buyer, supplier participation, line items,
   net/gross amounts, source dates, statuses, and typed references. Keep missing
   fields unknown and preserve the original Greek text and identifiers.
6. In a PostgreSQL transaction, save observations, changed record versions,
   normalization results or quarantine entries, and a durable work handoff.
7. Checkpoint a page only after the raw evidence and database state are durable.
   Give each independently retryable operation a stable identity.
8. Reconcile retrieved unique IDs and pagination metadata. Offset-based results
   can change during collection; repeat bounded settled windows where needed.
   Report discrepancies explicitly. No unverified point-in-time snapshot guarantee.

## Data model and invariants

- `ingest_runs`: query, connector version, window, state, checkpoints, counts,
  timestamps, and structured failure details.
- `raw_objects`: content hashes and archive locations; repeated identical bytes
  reuse the stored object without losing their observation history.
- `source_records`: namespaced source identity, e.g. `kimdis:<ADAM>`.
- `record_versions`: source revision metadata or a content hash, with immutable
  normalized content and references to the original response and JSON location.
- `observations`: when a version was encountered. A return from content A to B
  and back to A must remain reconstructible even if A's bytes are reused.
- `contract_participations`: buyers and suppliers as reported. Participation
  does not imply validated company identity, ownership, or value allocation.
- `quarantine`: raw evidence, validation reasons, and replay state.
- `outbox`: durable pending work committed alongside the relevant record state.

Money includes amount basis, currency, and relevant units. A multi-supplier
contract does not allocate its full value to each supplier. Contract records are
not combined with later award/payment records into a single spend total.

Retain source event dates, publication/update dates, and observation time
separately. Do not fabricate an offset for a source timestamp without timezone
information. Document and verify any timezone assumption before conversion.

Collection completeness and normalization completeness are separate states. A
run containing quarantined rows must disclose the counts and cannot present a
fully normalized dataset without resolving or explicitly accounting for them.

## Archived-page persistence contract (2026-11-09)

This implements the approved PostgreSQL data model above before HTTP resume.
Use PostgreSQL 17 and pinned Psycopg 3.3.8 with parameterized SQL. Connection
strings stay in process memory/environment; never put credentials in arguments,
logs, or source control. Development tests use an isolated, disposable database.

`PageStore.start_run(run_id, query)` fixes the query and connector version.
`PageStore.commit_page(run_id, raw_body, observed_at=aware_time)` archives and
validates a response, then commits page metadata, valid-record versions and
observations, quarantine entries, pending outbox events, and `next_page` together.
Returns true for a new page and false for identical committed-page replay.
Run UUID/page number is the stable page identity. Changed bytes at a committed
page or a page gap are errors; the original committed page is never replaced.

Lock the run row while committing; reject changed pagination shape and duplicate
valid source IDs within a run. A checkpoint means the page transaction committed;
it does not assert complete source coverage. Unknown IDs/bad rows remain in
quarantine, and no fully normalized or snapshot-isolated claim follows.

Version identity is (source ID, normalizer version, canonical source-record hash).
Hash the entire parsed source record, including fields the normalizer does not
project. A typed canonical encoding distinguishes source strings/numbers and
preserves Decimal precision; object key order and unrelated page neighbors do
not affect it. Reject source nesting deeper than 128 levels before fingerprinting
can exhaust the call stack. Raw-body hashes/pointers retain original lexical evidence.
Version JSON excludes page evidence and stores exact amounts as decimal strings.
Observations bind each run/page/original row index to its version and observation
time. A→B→A reuses version A but retains three ordered observation events.

All successful normalized observations enqueue `record.observed` in the same
transaction, including unchanged records in a new run. Replay of a committed
page produces no duplicate observations/outbox entries. Events reference their
observation; an eventual consumer must be idempotent. Delivery/acknowledgement and
buyer/supplier relational projections are separate following slices.

An additive, packaged SQL migration has a stored SHA-256 checksum and version.
Migration is explicit, transactional, serialized, and rejects unknown or changed
migration history. No destructive down migration or automatic startup migration.
Version/observation updates and deletes are rejected. Deployment roles/backups,
production storage/retention, and major-version upgrades receive separate review.

Filesystem writes precede SQL, so rollback may leave an unreferenced blob. A
checkpoint never advances independently of its records/outbox. No transaction
spans filesystem and SQL. Test real SIGKILL before/after commit and replay through
a fresh connection. This acceptance proves the page API, not multi-page HTTP
resume; keep `runs resume` unavailable until the orchestrator is tested.

Verify locally with a disposable PostgreSQL service and
`NIMA_TEST_DSN='host=127.0.0.1 port=55432 dbname=nima_test user=postgres' make check`.
Tests must fail clearly if the test database is unavailable; no database mocks or
skips replace integration coverage. Existing `make audit` remains required.

Official patterns: https://www.psycopg.org/psycopg3/docs/basic/transactions.html ,
https://www.psycopg.org/psycopg3/docs/basic/params.html ,
https://www.postgresql.org/docs/17/explicit-locking.html , and
https://www.postgresql.org/docs/17/ddl-constraints.html .

## Durable collection and inspection contract

Opt in with `uv run python -m nima ingest kimdis --database` plus the existing
required dates/archive options. Read NIMA_DATABASE_URL from the environment only.
`uv run python -m nima db migrate` explicitly upgrades an existing schema;
`uv run python -m nima runs show RUN_ID` reads durable run metadata and counts.
Neither collection nor inspection applies migrations implicitly. Archive-only
collection stays available. Database errors emit sanitized codes, never driver
messages, connection strings, titles, or company tax identifiers.

A managed run fixes query, limits, connector/normalizer versions, archive root,
and a writer ownership token. Attempts are inserted before entering HTTP I/O;
finished receipts retain status, whitelisted headers, errors, and hashes of all
completed bounded bodies, including HTTP failures. A killed worker may leave a
started attempt with unknown outcome or an unindexed file; do not invent a result.
Transport journaling failure prevents a successful run. A failed database write
may leave the durable run's last saved state running; this is not a liveness claim.

Accepted pages retain source IDs, including identifiable quarantined rows, in the
same transaction as their checkpoint. Legacy page API calls cannot write a managed
run without its ownership token. Final completeness is saved only after committed
pages, unique IDs, counts, and quarantine reconcile. Inspection rebuilds counters
from committed SQL state, not from filesystem manifests or stale progress JSON.
It reports the stored run state with worker liveness unknown, pending attempt
count, checkpoint, query, and limits. It does not validate archive availability or
refresh source data; source coverage and archive integrity are separate properties.

A read-only inspection command exits zero when the run is found, even if its
collection failed. Missing configuration/invalid IDs exit 2; missing or unsupported
runs, database/schema failures exit nonzero. HTTP resume now requires the recovery contract below, including pending-response
replay and source-drift verification; an old offset checkpoint alone is not enough
to resume safely.

## Safe resume contract

`uv run python -m nima runs resume RUN_ID` resumes only managed database runs.
Read NIMA_DATABASE_URL from the environment; do not accept new query/archive/limit
flags. Validate the saved options, connector/normalizer versions and schema.
Require the original recognized archive to exist and verify each body hash within
its byte limit. Missing/corrupt evidence fails before fetching continuation pages.

Hold a nonblocking PostgreSQL session advisory lock for the whole invocation,
including fresh managed collection. A competing worker gets `run_busy` before
changing owner/status or requesting source pages. Under the run row lock, fence
the prior owner with a new UUID token. All page/attempt/finalization writes check
that token. A lost lock connection cannot let a stale writer overwrite a new one.
Drain pre-lease application workers before upgrading; do not infer their liveness.

Reconstruct coverage from committed page bytes/SQL checkpoints. For an incomplete
run, re-fetch every committed page and compare pagination plus ordered full-source
record fingerprints. Whitespace/object-key formatting alone may differ. A detected
change fails with `source_changed`, retains both responses, and accepts no new pages.
If a finished 200 collect response exists for the next uncommitted page, choose the
earliest, verify its archive hash, revalidate it, then commit its original bytes and
observation time. Verification responses do not create new observations/versions.
Started attempts with unknown outcome are never fabricated or silently rewritten.

An already fully committed run needs archive verification and reconciliation but
no source HTTP calls; this completes interrupted finalization without pretending
to refresh source data. Unchanged replay creates no duplicate observations/outbox.
Each user-invoked resume receives a new original time/retry budget; total run page
limit stays fixed. Saved page-limit/permanent data issues may require a fresh run.
Completed historical runs need a new collection to measure current source freshness.

The same transaction/coverage/retry path handles fresh and resumed pages. Resume
updates SQL and raw blobs; original file manifests/derived JSONL remain projections
of the initial invocation and are not complete resumed exports. Inspection reports
all attempts, historical unknowns, and current-owner pending attempts separately.
Revalidation is observational consistency, not a point-in-time source snapshot.
No scheduler, automatic retries across invocations, or deployment is included.

## Project structure

Implementation will grow from the existing package as the feature requires:

```text
src/nima/
  sources/kimdis.py       source-specific request/response handling
  ingestion/             run orchestration and replay
  storage/               raw archive and PostgreSQL persistence
  __main__.py            bounded command interface
tests/
  unit/                  money, dates, IDs, and normalization behavior
  integration/           HTTP boundary, archive, and real PostgreSQL tests
  fixtures/              synthetic or reviewed anonymized source fixtures
```

These are intended ownership boundaries, not a requirement to create empty
abstractions. Dependencies and migrations receive their own reviewed changes.

## Code style

Follow Ruff and strict mypy. Use explicit types at source boundaries and small
functions with observable failure behavior. For example:

```python
from decimal import Decimal


def net_amount(raw_value: str) -> Decimal:
    return Decimal(raw_value)
```

Validate missing or malformed fields at the boundary instead of assigning a
convenient zero. Keep the original representation with the evidence reference.

## Testing strategy

Ordinary CI uses deterministic synthetic/anonymized fixtures and a real local
PostgreSQL service for persistence tests. Live source probes are opt-in and
report source access independently from pipeline correctness.

Write behavioral tests before implementing the relevant slice. For durability,
terminate and restart a real worker against the archive and database; an injected
exception alone does not prove process-crash recovery. Verify both transaction
rollback and durable replay. Test concurrency once concurrent workers exist.

The current 90% line/branch coverage floor includes first-party tooling and all
implemented `nima` modules. Offline HTTP/archive tests verify collection failure
paths; live probes report source access separately. Crash/restart acceptance
still requires real process/database experiments in the next increment.

## Success criteria

1. A multi-page date window preserves all fetched raw responses and creates one
   logical record per source ID, with a reconciled collection summary.
2. Repeating an unchanged collection creates no duplicate logical records or
   content versions and retains a record of the new observation.
3. A changed, cancelled, or reverted source record preserves earlier evidence
   and temporal observation order.
4. A worker terminated mid-run resumes from durable state without losing pages,
   silently advancing a watermark, or creating duplicate downstream work.
5. Rate limiting, timeouts, invalid JSON, unexpected pagination, missing IDs,
   archive failures, and database failures produce bounded, inspectable outcomes.
6. Money remains exact; unknown values remain unknown; joint supplier totals
   are not inflated. Every normalized field can be traced to source evidence.
7. The command's summary distinguishes source coverage, quarantined records,
   processing failures, and freshness. No real-time or full-coverage claim is
   made solely because the ingestion job ran successfully.

## Boundaries

Always: preserve evidence, validate inputs, use parameterized SQL, redact logs,
document source attribution, and run meaningful tests and local checks.

Review before proceeding: this spec and its implementation plan; production
storage/retention; paid infrastructure or data; consequential source-access
changes; changes to the quality bar or public interfaces.

Never: commit raw records, personal data, credentials, or databases; bypass
source authentication/access restrictions; discard history to simplify replay;
treat a procurement signal or missing field as proof of wrongdoing.

## Open questions

- The exact production object-storage provider and retention policy are deferred
  until deployment. They do not block development of the bounded local archive.
- Choose the first buyer/category cohort after a small collection establishes
  source field coverage. First prove correctness for a one-day window.
- Verify a reliable strategy for old-record changes before claiming an update
  detection SLA. Recent-window polling alone cannot guarantee this.

## Current increment and review

The user's follow-up confirms the original company/public-spending concept and
the supplied ingestion-first architectural brief. This authorizes the staged
implementation direction; it is not approval to merge, deploy, publish findings,
or incur paid model costs. Review the bounded increments through pull requests.

The first slice decodes and validates one KIMDIS contract response, preserves
exact money and reported supplier participation, and attaches a raw-response
hash and source-field references. It does not fetch records, archive responses,
write PostgreSQL, or claim that the complete ingestion stage is implemented.
