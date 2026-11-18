# Spec: KIMDIS contract ingestion

Module: `source-ingestion` in `CAPABILITIES.md`.

The database-backed source in this specification is KIMDIS. The approved source-specific
[GEMI registry evidence contract](docs/sources/gemi.md) supplements this provider
module with a bounded archive-only collector; live compatibility remains unverified.

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
just setup
just check
just audit
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
`NIMA_TEST_DSN='host=127.0.0.1 port=55432 dbname=nima_test user=postgres' just check`.
Tests must fail clearly if the test database is unavailable; no database mocks or
skips replace integration coverage. Existing `just audit` remains required.

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


## DataOps increment: committed-page archive verification

Owner authorization: on 2026-11-17 the owner accepted the technical pilot verdict
and requested the next DataOps batch. Extend `source-ingestion` with one offline
integrity check first; SQL/archive restore and normalizer replay follow separately.
Human pilot review remains pending and does not block this engineering increment.

Objective: an operator can check that every original body referenced by one
selected KIMDIS run's committed SQL pages exists and matches its recorded hash
and byte length. This is not source freshness, parsing/projection reconciliation,
a whole-database scan or a restore/backup claim.

```sh
uv run --frozen python -m nima archive verify --run-id RUN_UUID \
  --archive-dir /absolute/private/collector-archive
uv run --frozen pytest tests/test_archive_verify.py
just check
just audit
```

`NIMA_DATABASE_URL` is environment-only. Use a reader with schema USAGE and SELECT
on `schema_migrations`, `ingest_runs`, `run_pages`, `raw_objects`; the pilot's
existing reader already has these grants. The verifier creates no roles and does
not certify the configured principal's privileges. Its own SQL runs in one
read-only repeatable-read UTC transaction with existing connection timeouts.
Validate the supported migration history, freeze only the selected run's committed
page/hash/length metadata, then close SQL before reading files. Bind parameters;
never include connection strings, source values, paths or raw hashes in errors.

Accept one UUID and an explicit absolute private archive root; do not infer or
require its stored absolute location. A relocated byte-identical archive can be
checked without modifying immutable SQL identity. Missing runs, broken checkpoint
contiguity (`0..next_page-1`), missing blob metadata or changed byte lengths fail.
A partial/failed run can have verified committed pages; always disclose its stored
run status and the `kimdis_committed_pages_only` scope. Do not imply full source
coverage. A run with no committed pages has `no_committed_pages` outcome/exit 3;
no archive is created, repaired or claimed verified in that case.

Bounds: at most 32 committed pages/object locations, 8 MiB per object and 64 MiB
combined distinct objects. Preflight the entire SQL selection before body reads;
never silently truncate. Deduplicate identical locations, retaining page count.
Reuse public `graph.pilot_archive` recovery with descriptor-relative private
no-follow reads, marker/Git-exclusion validation, regular-file/privacy checks,
change detection, hash verification and existing byte limits. Existing hard-linked
body aliases remain supported when bytes/length match; this is not an isolation
guarantee against another local writer. Place the new
application composition in `nima.dataops.archive`; do not make ingestion/storage
import the graph or add another filesystem-security implementation.

Success returns only fixed scope/outcome, stored run status, page/object counts
and verified-byte total. Configuration errors exit 2, interruption 130, other
failures 1; sanitized fixed reasons only. No HTTP, missing-object fetch, archive
initialization/repair/chmod, migration, projection, SQL write, manifest rewrite or
source schedule. Unreferenced files, uncommitted HTTP-attempt responses, GEMI and
manual-evidence layouts remain outside this first scope. A result describes the
frozen SQL snapshot, not later concurrent commits or an atomic cross-store backup.

Tests use synthetic originals, actual PostgreSQL 17 and private files. Verify a
limited reader, unchanged contents of all 26 tables/files, relocation, empty and
partial runs, concurrent commits after snapshot close, corrupt/missing/unsafe
files, metadata/byte/page limits and fixed CLI errors. A hash-check mutation must
fail a regression. Run full local gates and all three hosted checks before merge.
No new dependency, migration or CI change. Example summary follows existing style:

```json
{"status":"complete","outcome":"verified_committed_pages","scope":"kimdis_committed_pages_only","run_status":"complete","page_count":2,"object_count":2,"verified_bytes":256}
```

Always preserve originals and unknowns; never repair during verification or treat
an empty scope as a passed audit. Schema/dependency/CI changes are outside this
approved increment. Python types/dataclasses, strict mypy and Ruff follow the
existing adapters; tests live in `tests/test_archive_verify.py`.

### Sector metadata boundary

KIMDIS original bytes retain authority classification/activity and object CPV
codes/labels. The current contract normalizer exposes buyer key/name but not a
curated buyer-sector or CPV dimension. GEMI's profile normalizer retains reported
KAD activity code/label/version/type/validity assertions when supplied; that is not
live coverage or a reviewed company-sector dimension. Keep buyer function (for
example defence), purchased category (CPV) and supplier economic activity (KAD)
distinct. A defence buyer purchasing food does not classify its supplier as a
weapons company. Future sector mappings need source paths, taxonomy/version,
validity, unknown/conflict states and explicit reported versus reviewed/inferred
status; this archive-verification increment adds no inferred sector labels.


## DataOps increment: offline KIMDIS normalization replay

This continues the owner-approved archive replay/version work after #125. Rebuild
one bounded committed-page capture as an immutable private dataset, using an
explicit installed normalizer. This is an executable reprocessing path; it does
not insert source observations, alter prior versions, advance refresh state or
promote results into analytical projections. Those SQL promotion/version-policy
contracts remain separate work. No new source access, dependency or migration.

Command (the reader DSN stays in private `NIMA_DATABASE_URL` configuration):

```sh
uv run --frozen python -m nima archive replay \
  --run-id RUN_UUID --archive-dir /absolute/private/originals \
  --normalizer-version kimdis-normalized-v1 \
  --output-dir /absolute/private/replays
uv run --frozen pytest tests/test_archive_replay.py tests/test_archive_replay_cli.py
just check
just audit
```

The target is explicit and finite: only the installed `kimdis-normalized-v1`
implementation is supported in this increment. Unknown targets fail before I/O;
never label current code as a requested unavailable version. Stored source-run
normalizer identity is retained as lineage, not compared to the target. A past
normalizer version therefore does not prevent replaying its original bytes with
the installed target. Only the known KIMDIS contract connector envelope is accepted.
No runtime plugin, arbitrary Python import or model execution.

Read run/page/blob metadata in one REPEATABLE READ, READ ONLY transaction; close
SQL before recovering files. Require a contiguous committed prefix matching the
checkpoint. Bounds: 32 pages, 8 MiB/object, 64 MiB/distinct bodies, 5,000 source
records and the existing private artifact encoder's 32 MiB output ceiling. Check
metadata bounds before body access. Explicit relocated archive roots work through
the existing descriptor-safe recovery API; orphan bodies are excluded. Missing,
unsafe, corrupt or wrong-length originals fail without repair/publication.

Normalize each committed envelope and check its page number, record count and
pagination shape against frozen SQL metadata. Retain original Greek text and exact
Decimal money as strings. Emit both normalized records and quarantined records,
with raw body hash, original capture time, page/index, JSON pointer and original
record content hash. Bad envelopes fail the whole replay; individual invalid rows
remain quarantine results. Preserve duplicate occurrences rather than claiming
entity resolution/deduplication. A failed/partial source run is explicitly labelled
as its committed subset; replay success does not certify source completeness.

Dataset shape: `artifact_version`, `source`, `scope`, `source_run` (original run,
connector/normalizer identity, status, original query and checkpoint/shape), target
`normalizer_version`, ordered pages and per-record results. No wall-clock replay
time, absolute archive path, DSN or credentials enter the dataset. Canonical bytes
and the existing private no-clobber publisher yield a deterministic hash-named
0600 file in an owner-only 0700 output directory. Equivalent relocation/replay
produces identical bytes. Failed or interrupted work publishes no partial result;
existing output is never overwritten. Zero committed pages is a distinct no-result
outcome (exit 3); one committed empty response produces an empty replay dataset.
CLI summaries contain only fixed labels/counts, not source values or private paths.
Output must be outside the input archive; replay cannot add files to originals.

Implementation: `src/nima/dataops/replay.py`, its two test modules and minimal
`dataops/archive.py` CLI routing. Reuse public connection/schema, archive recovery,
normalizer and private artifact APIs. Do not duplicate strict JSON or safe-file
primitives. Tests use real PostgreSQL, files and an actual CLI subprocess: limited
reader, historical-version replay, exact money/quarantine, frozen snapshot versus
later commit, relocation/idempotence, limits, invalid source/target, unsafe output
and failure sanitization. Mutate the raw-evidence hash guard and show rejection
fails. Verify the existing private pilot offline with unchanged 26-table state,
originals and original reader report; retain all source values/proof outside Git.


## DataOps increment: explicit SQL replay promotion

Continue the owner-approved SQL promotion follow-up after #126. Store a selected
replay as derived SQL data in `nima_processing`, not as a new source observation.
An additive eighth migration creates immutable replay batches/results and a
`replayed_contracts` view. Existing `nima` evidence, outbox, reviews, projections,
workflow freshness and metric queries are unchanged. No source requests or new
dependencies. Only the installed v1 normalizer is currently supported.

```sh
uv run --frozen python -m nima db migrate
uv run --frozen python -m nima archive promote \
  --run-id RUN_UUID --archive-dir /absolute/private/originals \
  --normalizer-version kimdis-normalized-v1 --replay-sha256 SELECTED_REPLAY_SHA256
uv run --frozen pytest tests/test_replay_promotion.py \
  tests/test_replay_promotion_cli.py tests/test_replay_promotion_crash.py
just check
just audit
```

Use a private `NIMA_DATABASE_URL`; no DSN flag. Migration is an explicit operator
step, never implicit in promotion. The owner authorizes this schema addition by
continuing the planned SQL promotion increment. Migrating creates objects under
the configured NOLOGIN owner. Grant the promoter SELECT on the existing migration,
run, page and blob metadata plus USAGE/SELECT/INSERT on only the two new processing
tables; reader SELECT alone cannot promote. No source-table write grant is needed.
The new schema grants no PUBLIC access. New tables reject update/delete/truncate.

Refactor the existing replay path to expose public `prepare_replay`, returning
canonical bytes and its bounded summary without publishing a file. Both replay
and promotion reuse the same snapshot, original verification and normalizer. An
explicit lowercase SHA-256 is required before I/O. Rebuild from originals and
require the generated hash to match the selected replay; no imported caller JSON
or arbitrary normalizer plugin is trusted. Only complete/quarantined captures may
be promoted in this increment. Running/failed/interrupted/unmanaged captures keep
the existing read-only replay path. No promotion turns partial collection complete.

On a fresh, explicitly READ COMMITTED write transaction, validate migration
history, take the shared transaction form of the collector's existing advisory
lease and compare its frozen query/status/checkpoint/version/shape
with the prepared manifest. A later concurrent collection or status change makes
promotion fail before insertion. Then atomically insert the content-keyed batch
and all results. A batch stores the bounded manifest, target version, counts,
database principal and `processed_at`; each result binds the same batch/run and
an original page/index, with its content hash and either normalized JSONB or a
quarantine reason. Exact money remains strings. Bulk-insert results, not one SQL
roundtrip per record. No insert into `observations` or `record_versions` occurs.

The view exposes the selected batch, normalized fields and original raw hash,
JSON pointer and `observed_at`, separately from `processed_at`. Consumers must
explicitly select batch/version; the view does not choose a new default or feed
existing metrics. Identical concurrent retries converge to one complete batch;
a committed retry must match stored manifest and every result. Conflicts fail
without overwrite. Process death before commit leaves no partial batch/results;
after commit, a retry returns the existing batch. Retries reverify originals and
current source scope; changed source scope requires a newly selected replay hash.

Tests use real PostgreSQL/files/CLI: v7 upgrade preserves all seven old checksums,
old evidence and projections, required new ownership/constraints/roles, exact
amounts, quarantine recovery, wrong hash, unavailable version, stale scope,
read-only denial, conflict, concurrent retry and actual SIGKILL transaction
boundaries. Remove hash selection guard and confirm its regression fails. Run
full gates. Verify a private migrated clone of the existing pilot with an actual
limited promoter/reader, identical original readout and no original database/file
or source-budget changes. Never migrate the live pilot with an unmerged branch.
Record actual results privately/redacted; no source records/credentials in Git.

Implementation: `storage/migrations/0008.sql`, migration registration, minimal
latest-version expectations in existing tests; `dataops/replay.prepare_replay`,
`dataops/promotion.py`, the shared public run lease key, archive CLI and three
promotion test modules. Retain
all pending request/refresh version-policy, metadata, model and human-review work.


## Checkpoint C1: operational replay and saved-intent compatibility

Owner authorizes automatic continuation to this checkpoint after merging #127 at
`ef2b438`. Build and verify through C1 without routine approval pauses. Retain the
PR review boundary; no automatic merge. Use the existing Python/PostgreSQL/Prefect
stack and fixed version-one formats; no new dependency, migration, source request,
schedule activation or model. The source-attempt allowance remains exhausted.

C1 is reached when the existing pilot is safely upgraded to reviewed migration 8,
its selected prior replays are promoted, saved request/policy identity no longer
depends on current constructor defaults, incompatible source execution fails
before effects, required local/hosted gates pass and a reviewable PR records results.
Metadata and model work remain after this checkpoint. Unsupported old algorithms
are not silently upgraded; linked intent replacement and format-v2 support are
explicit later work rather than being implied by inspection compatibility.

For private pilot maintenance, quiesce and inventory the source, retain a new native
snapshot dump paired with original archives/request/readout/configuration and a
separately anchored manifest. Restore that backup into an owned disposable database
and verify contents, native CHECK reparse equivalence, migration 8, archived bytes
and identical readout before touching the pilot. Then migrate under its configured
NOLOGIN owner. Grant a dedicated promoter only four source metadata SELECTs and
SELECT/INSERT on the two processing tables; grant the existing reader USAGE and
SELECT on the derived view. Promote only previously selected verified hashes.
Check idempotency, distinct capture/processing clocks, source rows/counters/schema,
old role grants, original bytes/readout and the three HTTP guards. Only the journal
and new derived tables/explicit grants may change. Keep credentials, full proof,
rollback/restore details and all source values outside Git. Do not remove the
original evidence or mislabel a local clone as off-host recovery.

Add a small pure saved-intent codec in `src/nima/intent.py`, reusing Query/Limits.
Version-one request/policy formats have frozen field sets and canonical shape.
Validate each JSONB value against its own stored SHA-256 and schema. Decode recorded
limits rather than reconstructing current defaults; validate finite types and
apply the original fixed v1 workflow ceiling (100 pages, 3 attempts, 8 MiB/page,
20 requests/minute, 20 s request timeout, 300 s run and 60 s retry delay) at the
execution boundary. A new default cannot change an existing intent. Unknown
processing pins remain inspectable; malformed/unknown formats fail with fixed
reasons. No filesystem or HTTP write occurs while decoding.

Submission with an existing UUID and the same explicit query/root reuses its
validated immutable intent, including recorded pins/limits. Different explicit
inputs conflict. Concurrent creation remains first-writer-wins; never rewrite
old JSON/hash or copy new defaults into it. Keep the public execution-options
method strict: current connector/normalizer support and v1 limits must be valid.
Expose recorded version/pin/compatibility diagnostics in existing status surfaces.
Prepared manifests also retain the recorded request format. Refresh `enabled`
keeps its stored-state meaning; additive `execution_enabled` combines that state
with current compatibility.
Gate source leases and new dispatch before owner/budget/dispatch writes or RPC.
Existing absolute archive binding/resume restrictions are not removed here.

Refresh inspection/planning uses the recorded, supported v1 policy profile and
own hash, rather than comparing to today's processing pins. Existing same-ID
creation reuses identical explicit policy inputs. A historical policy can still
be paused. Enable, active tick, new cycle/child and sending transitions require
compatible connector/normalizer/profile before state changes or RPC. A mismatch
must not enable the SQL gate, create a child with new pins or consume source
budget. Disabling still closes the gate before reconciling the local schedule.
No implicit replacement, altered cron, enlarged budget or new source freshness.

Use real PostgreSQL for default/pin-change, concurrent reuse, immutable hash,
malformed intent, bounded limits, blocked side effects and pause/enable/tick tests;
reuse recorded fixtures and existing local Prefect tests. Demonstrate a mutation
that drops a pin guard is caught, then restore it. Verify the private upgraded
pilot offline; original readout must remain byte-identical. Commands:

```sh
uv run --frozen pytest tests/test_intent_compatibility.py tests/test_workflow_requests.py \
  tests/test_refresh_store.py tests/test_workflow_pipeline.py
just check
just audit
```

After local checks, publish a focused PR and verify all three exact-head hosted
jobs, repairing failures within the same batch. The owner reviews at C1 before
metadata/model work; this checkpoint is not human metric certification or a live
capture deployment.


## Checkpoint C2: structured market metadata

Continues owner-merged #128 (`bd7fec4`) under the existing metadata roadmap and
authorization to build through a review checkpoint. Deliver a read-only, bounded,
queryable private snapshot before SQL indexing or model enrichment. No source
requests, dependency/CI changes, migrations, scheduled activation or metric change.

KIMDIS contract responses expose `contractingAuthorityActivity`,
`classificationOfPublicLawOrganization`, `typeOfContractingAuthority` and object
`objectDetailsList[].cpvs[]` as reported key/value pairs. Source: the retained
official contract at https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help.
GEMI's retained Company schema/normalizer exposes activity code, label, KAD version,
type and validity dates: https://opendata-api.businessportal.gr/api-docs.
Do not fetch either source or assume a code dictionary/version not supplied.

Commands: `uv run python -m nima metadata kimdis --run-id UUID --archive-dir
/ABS/ARCHIVE --output-dir /ABS/OUTPUT`; SQL uses `NIMA_DATABASE_URL` with SELECT
access to the same four metadata tables as archive replay. `metadata gemi` takes
the same explicit paths/run ID and verifies the completed archive without SQL or
an API key. Both accept `--dimension NAME` and optional `--code EXACT`; code needs
a dimension. All source values and result hashes stay in private artifacts;
terminal JSON contains only fixed outcomes and counts. Output must be outside the
input archive. No init, repair, SQL write, credential lookup or network fallback.

Dimensions are buyer function, buyer legal classification, buyer type, procurement
CPV and reported supplier KAD. Buyer function never becomes supplier activity;
CPV never becomes KAD. No entity join or implied defence-industry classification.
Statuses distinguish reported, missing, null, empty and invalid source shapes.
Reported means structurally usable, not taxonomy membership/checksum verified,
reviewed identity or effective current activity. CPV checks ASCII format only;
KAD retains the reported version and dates, including unknowns. Invalid optional
metadata stays visible and does not alter the existing contract normalizer.

Each assertion retains exact usable code/Greek label, expected source path,
actual pointer when present, raw response hash and parent record pointer. Context
retains source/run, original observation time, source-content hash where available,
record normalization status and original capture status. Repeated observations and
CPV positions remain occurrences; this is not a deduplicated company, current-state
or spend metric. Missing/empty/no-match coverage is explicit and cannot establish
absence in the real market. Filtered artifacts retain full-scope quality counts.

Reuse replay's frozen closed SQL snapshot and safe hash-verified archive recovery;
expose one public capture API instead of a parallel evidence loader. Existing replay
bytes remain identical. Reuse strict source decoding, GEMI archive verification and
canonical private no-clobber publication. Preserve the existing page/body/record
limits, cap metadata assertions at 10,000 and encoded output at the existing report
limit. Verify pagination against frozen metadata before extracting. Unknown capture
formats and damaged evidence fail before output publication. No processing timestamp
may replace observation time; deterministic retries and relocated archives agree.

Acceptance: pure shape/unknown/path/Greek/code tests; real PostgreSQL SELECT-only
KIMDIS and completed synthetic GEMI archive through CLI; optional metadata quality,
filtering, duplicate positions, boundedness, corruption/refusal and original-state
preservation. Mutation must break a meaningful regression. Full `just check`,
`just audit` and all exact-head hosted jobs precede handoff. Then owner review;
no automatic merge or human taxonomy certification. SQL metadata projections and
Greek-model evaluation remain following work, not delivered by this checkpoint.


## Checkpoint C3: explicitly selected SQL metadata snapshots

Owner merged #129 at `6051d41`; continue the same metadata roadmap. C3 delivers
PostgreSQL serving first, with an official taxonomy source/version assessment.
Dictionary installation/matching is C4, not an implicit claim in this checkpoint.
No new company lookup, dependency/CI change, live migration or model activation.

Expose public `prepare_metadata` to generate the existing canonical unfiltered
C2 bytes without publication. Existing exports/filters/bytes remain compatible.
`metadata promote SOURCE --run-id UUID --archive-dir /ABS --snapshot-sha256 HASH`
uses `NIMA_DATABASE_URL`, verifies original archives again, and requires the exact
selected unfiltered canonical hash. KIMDIS must be complete/quarantined and is
rechecked under the shared run lease. GEMI requires the explicitly completed
archive to have been imported already, with matching immutable import manifest.
No implicit source import or archive-file trust. Caller-supplied metadata JSON
is not an ingestion path.

Add reviewed migration 0009: one immutable `nima_processing.metadata_snapshots`
table containing full verified metadata documents, separate KIMDIS/GEMI source
foreign keys, extraction version, diagnostic counts, processing time and database
principal. Preserve all previous migrations and the 26 original `nima` tables.
Reject UPDATE/DELETE/TRUNCATE; primary-key lookup is the initial serving index.
`reported_market_metadata` flattens assertion occurrences with source/run, field
pointers, hashes, original observation time and separate processing time. Unknowns,
duplicate positions and all C2 meaning/coverage boundaries remain intact.

Promotion is one explicit READ COMMITTED transaction, idempotent under concurrent
retries, with existing-row comparison and conflict refusal. A fresh selected hash
is required when source scope changes. Only SELECT on source metadata/imports and
SELECT/INSERT on the one derived table are needed; a reader has SELECT only.
Source bytes/rows, original metrics and schedules remain unchanged.

`metadata query --snapshot-sha256 HASH --output-dir /ABS [--dimension NAME]
[--code EXACT]` is REPEATABLE READ/READ ONLY, with fixed connection timeouts and
no archive or network requirement. An absent/unsupported/corrupt snapshot is an
error, not zero. Validate the selected stored canonical hash before querying.
Parameterized SQL preserves source-specific dimension rules and full quality
coverage. Compare SQL output with the shared pure assertion-selection policy
before private canonical publication. Output equals the C2 logical filtered
snapshot. Integrity is verified at promotion time; SQL-only reading does not
re-check a subsequently lost or damaged archive. It is not fresh source data.

Bounds stay 5,000 records/10,000 assertions/32 MiB canonical output; no truncated
success or automatic latest-snapshot selection. Terminal output remains fixed
status/counts only, including a reuse flag for promotion. Source IDs, values,
paths and selected hashes stay private.

Acceptance: explicit migration upgrade/ownership/old checksum checks; source FKs
and immutability; real restricted roles; KIMDIS/GEMI imported-source paths;
selected-hash/stale/partial/corrupt/missing refusal; SQL/Python exact filter parity,
zero-assertion records, relocation and deterministic retry; concurrent retries
under both role isolation defaults; real process death at SQL commit boundaries.
A meaningful guard mutation must fail. Full `just check`/`just audit`, built SQL
resources and all exact-head hosted jobs precede C3 handoff. Private pilot schema
stays at reviewed 8; any migration-9 pilot proof uses an owned disposable clone.
Owner review/merge is the checkpoint; no automatic live deployment.


## Checkpoint C4: reviewed pilot deployment and pinned CPV reference

Owner merged #131 at `7bdf5da` after #130; continue the authorized data foundation
work. First deploy only reviewed migration 9 after a fresh native backup/restore
and unchanged-source checks. Scope existing promoter/reader grants to the new
snapshot table/view, promote prior explicitly selected C2 metadata, verify reuse,
reader refusal and original readout/source preservation. Keep credentials, archive
bytes, operational details and proof outside Git. No new company-source request or
schedule/model activation is authorized by reference-dictionary work.

Then build an offline versioned CPV reference loader and separate dictionary-match
output. Pin the official source/release, language, raw hash and reuse attribution.
Inspect an actual official distribution before freezing its parser. Refuse empty
HTTP acknowledgements, corrupt/malformed archives/XML, unsupported versions,
conflicting codes, absent selected language and truncated success. Reference data
and original reported metadata remain separate. No automatic KAD conversion,
buyer-function-to-supplier classification, source-label overwrite or certification
of company sectors. KAD crosswalk installation stays a subsequent bounded scope.

Dictionary source/format details and matching grain must be recorded after direct
inspection and before implementation. If a source supplies base codes without a
check digit, that match scope must be explicit; it cannot claim full-code checksum
validation. No silent source, language or version fallback. Any added parser
package must have pinned versions, reviewed licensing, strict types, regenerated
locks and the full existing security/audit gates. Work through a review checkpoint;
no automatic merge of new parser/reference features.

### C4 CPV contract frozen after inspecting the publisher release

Use the OP-TED eForms SDK **1.15.1** `codelists/cpv.gc` captured from
`https://raw.githubusercontent.com/OP-TED/eForms-SDK/1.15.1/codelists/cpv.gc`.
The repository's tagged LICENSE is CC BY 4.0. Retain publisher, source and licence
URLs, capture time, exact raw SHA-256 and selected language in every derived
reference/match. This is an explicitly selected release, not a latest-version
claim. Its genericode Identification names `cpv_2008_core`, Version `2008`, and
CanonicalUri `http://publications.europa.eu/resource/dataset/cpv`. SDK release and
taxonomy version are separate. Reject the earlier empty TED HTTP-202 response.

The inspected file has 9,454 rows, eight-digit `code`, optional `parentCode`, and
`ell_label` / `eng_label`. Reader v1 supports these two explicitly selected
languages, with no fallback. Input is bounded to 64 MiB, 10,000 rows, depth 12,
1,000,000 elements and 4,096 characters per leaf. Require the genericode 1.0 root,
Identification/version, declared unique columns, unique rows and one nonempty
selected label per code. Reject malformed XML, DTD/entities/external references,
missing/duplicate cells, unknown columns, invalid parent links/cycles and exceeded
bounds; never publish a partial dictionary. All row ordinals remain traceable.
Use defusedxml 0.7.1 with explicit DTD/entity/external refusal; declare the already
locked library as a runtime dependency and add its development-only type stubs.

Pure preparation takes selected raw bytes, their expected SHA-256, capture time
and language. Canonical reference JSON records the source and derived-format
versions; exact case/Unicode text is retained, codes sorted, original zero-based
row ordinals attached. No source data in Git. An offline CLI reads a private,
no-follow regular file, validates all input before no-clobber publication, and
prints fixed counts/status only. No downloader, database migration or scheduler.

A separate command takes an explicit stored metadata-snapshot hash and the same
selected captured reference, using the existing read-only SQL query. It writes a
versioned annotation artifact, retaining the full reported record/assertion and
original evidence lineage unchanged. Annotate only CPV occurrences. A reported
`########-#` is compared by its first eight digits; outcomes distinguish base-code
match, not found in the selected release, ineligible source value and explicit
version conflict. Never validate or repair the check digit, populate an unknown
reported taxonomy version, substitute source labels, infer supplier sectors, or
certify source correctness. Match scope and unchecked check digit are explicit.
Dictionary version/hash/language and original metadata hash pin every result.
Reader/matcher tests use synthetic labels; real-release and retained pilot proof
stay private. KAD crosswalks, ontology, models and human validation remain later.


## Checkpoint C5: source acceptance and analytics readiness

Continue after owner-merged #132/#133. Main contains #132; #133 targeted its
feature base, so #134 promotes the reviewed command files without content changes.
Do not declare main delivery until that promotion merges. Keep the previously
tested tree and new integration CI evidence distinct.

This increment records a capability-weighted [foundation assessment](docs/roadmap/analytics-readiness.md)
and [KAD source acceptance](docs/sources/kad-reference.md). The roughly 60% estimate
uses an explicit 100-point single-operator analytics-core denominator; it is not
Greek data coverage, test coverage or an update to the historical investigator
product percentage. Source code, tested-but-unpromoted work and live validation
are separate states.

Actual AADE catalogue/correspondence/terms captures stay private. Respect the
source's transitional identifier column, exact historical code strings, release
amendments and reuse restrictions. No runtime KAD parser/crosswalk, new dependency,
schema, schedule, company-source request or model is installed at this checkpoint.
Runtime acceptance requires resolved reuse scope and complete bounded extraction/
reconciliation tests as specified in the source contract. Meanwhile prioritize
DataOps health/freshness and descriptive metrics without activating new sources.
