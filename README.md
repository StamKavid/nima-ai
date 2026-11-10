# Nima AI

Nima helps journalists, investigators, and researchers trace Greek company
relationships and public spending, then develop evidence-backed investigative
leads. Its mission is to make relationships, spending patterns, and changes over
time inspectable and reproducible.

The product combines a temporal relationship graph, sector comparisons,
explainable statistical/ML detectors, and AI-assisted research with citations.
Current code implements bounded KIMDIS contract collection, a private raw-evidence
archive, typed normalization, optional PostgreSQL collection, and durable run inspection.
It also projects reported participation and creates offline identifier-review reports.
Reviewed identity resolution, a graph store, trained
models, and the investigation workspace are subsequent milestones.
An investigative signal is not a finding of wrongdoing.

## Investigator questions

- Which buyers repeatedly award work to this company, and how does it compare
  with similar suppliers in the same sector, region, and period?
- Which source-supported directors, shareholders, or corporate changes connect
  companies during the period being investigated?
- Which repeated awards, amendments, prices, or bidding patterns deserve review,
  given the data actually available?
- Which documents support a lead, what changed, and what evidence is missing?

The practical deliverable is a reviewable case with an evidence trail. Read the
[architecture and model strategy](docs/architecture.md) for the stages and gates.

## Development

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required. Full checks also
require disposable local PostgreSQL 17; configure `NIMA_TEST_DSN` as below.

```bash
make setup
make check
make audit
```

`make check` verifies the installed skills, formatting, lint, types, behavioral
tests, package build, and source security. `make audit` checks locked third-party Python dependencies against
the Python Packaging Advisory Database. The unpublished project is checked
by first-party tests and static analysis rather than a public package database.
These checks cover first-party tooling and collection behavior. They do not
prove full-source coverage, crash recovery, or model quality.

## Collect a bounded KIMDIS window

```bash
uv run --frozen python -m nima ingest kimdis \
  --from-date 2026-11-06 --to-date 2026-11-06 \
  --archive-dir data/raw
```

Dates are explicit and inclusive, with at most 180 calendar days per run. Add
`--buyer-id 100015981` to filter a public buyer; repeat it for multiple buyers.
Use `ingest kimdis --help` for limits. Defaults: 100 pages, three attempts/page,
8 MiB/body, 20 requests/minute, 20-second HTTP inactivity timeout, and a
300-second cooperative run budget. Oversized windows are rejected, never truncated.

The command emits a JSON summary without record titles or tax identifiers.
Exit codes: `0` complete, `1` failed/incomplete, `2` invalid options, `3` collected
with quarantined rows, `130` interrupted. Inspect the run's manifest for query,
limits, individual attempts, timestamps, counts, and raw-response references.
An HTTP 200 or a page-limit stop does not imply complete coverage.

The archive must be a new/empty directory or a recognized Nima archive. It uses
owner-only directories/files and a local Git exclusion. Its layout is:

```text
data/raw/
  objects/<sha256-prefix>/<sha256>.body
  runs/<run-id>/manifest.json
  runs/<run-id>/normalized.jsonl
  runs/<run-id>/quarantine.jsonl
```

Bodies are exact decoded HTTP entity bytes before JSON parsing. The collector
requests identity encoding and rejects compressed responses to keep memory use
bounded. Completed bounded responses, including HTTP errors, are archived;
partial/oversized bodies have failure metadata without a complete-body hash.
Normalized amounts are exact decimal strings. A record's hash and JSON pointer
resolve to the original evidence. Identical bodies reuse storage; each invocation
creates a separate run. Use one local collector owner; concurrent/hostile archive
writers and network filesystems are outside this slice's guarantees.

The source is [KIMDIS Open Data](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help)
(CC BY 4.0); its documentation describes daily updates. Live requests encountered
429 responses below the published 350 requests/minute ceiling. The conservative
default is therefore 20/minute, with a 30-second initial backoff when a 429 has
no `Retry-After`. A retry requiring more than the configured budget stops visibly.

Timeouts are checked between waits, response chunks, and pages. A blocking read
may overrun the cooperative budget by an inactivity timeout; filesystem I/O has
no hard deadline. Manifests use atomic writes but are **not database checkpoints**.
Archive-only runs require a fresh bounded collection after interruption. Managed
PostgreSQL runs support explicit `runs resume RUN_ID`; automatic scheduling/retry
across invocations is not implemented. Offset pagination can drift without observable
count changes; successful reconciliation is not a point-in-time snapshot proof.

## Normalization API

`nima.sources.kimdis.normalize_contract` accepts original JSON response bytes and
a record index. It preserves exact Decimal amounts, reported supplier
participation, missing data, cancellation state, and raw source timestamps. It
returns a SHA-256 response reference and a record JSON pointer. Currency remains
unknown when reported line-item currencies are missing or mixed.

The function performs no network call, database write, graph inference, or ML
prediction. It does not allocate a joint contract's full value to each supplier.
`normalize_page` decodes once, validates pagination, and quarantines malformed
rows with original evidence locations. The full ingestion milestone is specified in
[SPEC-source-ingestion.md](SPEC-source-ingestion.md).

## PostgreSQL page persistence

`nima.storage.postgres.migrate(dsn)` explicitly applies the checksum-verified
additive schema. `PageStore(dsn, archive).start_run(run_id, query)` fixes a run's
query, connector/normalizer versions, and archive location. Its `commit_page`
method accepts original response bytes and an aware `observed_at` timestamp.
It archives before SQL, then commits versions, observations, quarantine, pending
outbox work, and the next-page checkpoint in one transaction. Identical replay
returns false; changed committed evidence or page gaps raise `CheckpointError`.

Source versions hash the full source record and exclude page position/evidence.
Observations retain run/page/index/time, so A→B→A reuses version A and preserves
all three observations. Monetary values remain exact decimal strings in JSONB.
Join observations to `run_pages` for the raw hash and original `/content/<index>`
pointer. The archive root is fixed per run. SQL triggers reject evidence edits.

Add `--database` to the HTTP command to persist attempts and accepted pages in
PostgreSQL. Configure `NIMA_DATABASE_URL` in the environment, then explicitly apply
migrations before collection:

```bash
uv run --frozen python -m nima db migrate
uv run --frozen python -m nima ingest kimdis --database \
  --from-date 2026-11-06 --to-date 2026-11-06 --archive-dir data/raw
uv run --frozen python -m nima runs show RUN_ID
```

Without `--database`, ingestion remains archive-only. No command except
`db migrate` applies schema changes. Migrations 0002 and 0003 upgrade earlier schemas
without changing their original SQL/checksums or historical evidence. Standalone page-API runs from
v1 remain unmanaged and are not inspectable with `runs show`.

Inspection reconstructs counters from committed SQL rows and exits zero when the
managed run is found, including failed runs. It reports stored status and
`worker_liveness: unknown`; a saved running state does not prove a live worker.
An interrupted request can remain started with an unknown outcome. SQL/journal
errors stop collection and preserve its run ID in the sanitized failure output.
Inspection does not read archive bodies or refresh source records, so it cannot
establish archive integrity or current source freshness.

Local supplier/buyer projections are described below; external outbox delivery
remains future work. SIGKILL/restart tests cover collector recovery and the page transaction
boundary; database-server/storage-device crash recovery remains unproven. Keep
connection strings in environment/memory and redact driver errors before exposing
them in an interface.

Resume a managed run with its original query, limits, versions and archive:

```bash
uv run --frozen python -m nima runs resume RUN_ID
```

Fresh/resumed workers hold a session advisory lease; an active writer produces
`run_busy`. Ownership claims use that exact connection, and writer UUID checks
fence stale page/attempt/finalization writes after takeover. Drain older pre-lease
application workers before upgrading. Resume itself needs no additional migration.

Resume verifies saved body hashes, reconstructs the SQL checkpoint, and recovers
the earliest complete successful response for the next uncommitted page. It
revalidates the committed prefix and that pending response against source page
metadata and ordered source fingerprints before continuing. Saved responses keep
original bytes and observation times; verification does not duplicate observations
or outbox events. Detected drift returns `source_changed` without accepting new
pages. Start a fresh bounded run if the source or required options have changed.

Each explicit resume gets a new original time/retry budget; its total page limit
stays fixed. Fully committed runs verify archives/reconcile without source HTTP;
use a new collection to measure freshness. Unknown old started attempts remain
unknown. `active_pending_attempts` counts current-owner unfinished attempts and
still does not establish worker liveness.

Resume updates SQL and raw evidence. Initial file manifests/JSONL are preserved
as initial-invocation projections and may be incomplete after a crash; they are
not complete resumed exports. Use SQL/`runs show` for resumed state. Revalidation
cannot establish a point-in-time snapshot from offset-based source pagination.

For full tests on Linux, start a disposable database (Docker required):

```bash
docker run --rm -d --name nima-postgres-test \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=nima_test \
  -p 127.0.0.1:55432:5432 \
  postgres:17-bookworm@sha256:665dc7b37ac52a17e298511414c21d23ffa4e6a6ef6225b3e5d59c7afb35e994
docker exec nima-postgres-test pg_isready -U postgres -d nima_test
export NIMA_TEST_DSN='host=127.0.0.1 port=55432 dbname=nima_test user=postgres'
make check
make audit
docker stop nima-postgres-test
```

Wait for `pg_isready` to succeed before testing. This passwordless service is
loopback-bound and disposable. Tests require the base database name `nima_test`
and a role allowed to create/drop databases; each test creates and removes only
its own UUID-named database. Missing test configuration fails visibly. CI runs
the same tests with a digest-pinned PostgreSQL service. Production roles, encrypted
remote connections, backups, and retention are decided before deployment.

## Delivery workflow

Specification → small tasks → failing behavioral tests → implementation → local
checks → pull request → review → merge → staged release.

Read [AGENTS.md](AGENTS.md), [CONSTRAINTS.md](CONSTRAINTS.md), and
[CONTRIBUTING.md](CONTRIBUTING.md). The capability map is in
[CAPABILITIES.md](CAPABILITIES.md); task state lives in [tasks/todo.md](tasks/todo.md).

The remote is [StamKavid/nima-ai](https://github.com/StamKavid/nima-ai).
Preserve private visibility. A draft PR is a review checkpoint, not authorization
to merge or deploy.

## Installed skills

All 25 skills from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
are installed project-locally in `.agents/skills/`. Shared references, supporting
documents, and the MIT license are preserved. `.agents/skills.lock.json` records
the upstream revision and file hashes. `make skills-check` detects local drift;
it is an integrity check against the recorded snapshot, not signature verification.

Codex discovers project-local skills when a session starts in this repository.
In an existing session, read the relevant `SKILL.md` directly. Installation does
not add slash commands or register a global plugin.

## Reported participation

After explicit `db migrate`, process a bounded batch from NIMA_DATABASE_URL:

```bash
uv run --frozen python -m nima outbox project --max-events 100
```

The limit is 1–1,000 events. The JSON summary reports projection version, processed
and remaining events, and `complete` or `pending`. Exit 0 means the batch succeeded;
remaining work is a snapshot and may include locked events. Invoke again to drain.
The worker does not schedule itself or refresh source data. Failures stop the batch,
keep the affected event pending and redact source/driver details; prior commits survive.

Migration 0003 adds immutable, versioned `projection_contracts`, `projection_mentions`
and `projection_receipts`. Amounts are exact PostgreSQL numeric values on contract
facts. Mentions preserve source order and unknowns; matching names/tax IDs are not
merged. Unknown versus reported-empty suppliers remain distinct. A contract with
over 1,000 supplier occurrences fails visibly without truncation.

For a selected run, this psql query exposes evidence-linked reported relationships:

```sql
SELECT source_id, buyer_name, supplier_name, supplier_ordinal,
       raw_sha256, json_pointer, observed_at, run_status
FROM nima.reported_procurement_edges
WHERE run_id = :'run_id'::uuid
  AND projection_version = 'kimdis-participation-v1'
ORDER BY observation_id, supplier_ordinal;
```

The view has no monetary columns: joint suppliers must not each receive the entire
contract value. Unknown/empty suppliers create no edges; inspect contract facts for
those counts. For amounts, join observations to projection_contracts using
`(source_id, normalizer_version, content_sha256)` and filter one run and projection
version. Repeated runs are observations of contracts, not additional spending.
Check run coverage, currency, cancellation and unknown amounts before aggregation.

Projection writes, an observation receipt and outbox acknowledgement share one
transaction. Receipts govern eligibility per projection version, including replay
of already acknowledged events for a future version. `delivered_at` records first
successful local projection; it does not mean external graph delivery. A changed
mapping requires a version bump. Actual SIGKILL tests prove worker rollback/retry,
not database-server or storage-device crash recovery. See
[verification](docs/verification/participation-projection.md).

## Offline identity assessment

After projecting every accepted observation of a selected run, create a private
review report using NIMA_DATABASE_URL:

```bash
uv run --frozen python -m nima identities assess RUN_ID \
  --projection-version kimdis-participation-v1 \
  --output-dir work/identity-review --max-mentions 10000
```

This command reads one repeatable-read, read-only database snapshot and makes no
HTTP requests. It rejects missing projection receipts/facts/mentions and enforces
10,000 occurrences plus a 32 MiB report limit without truncation. It preserves
partial/unmanaged run coverage and unknown/empty supplier lists.

Reports contain every original party occurrence, comparison fields, candidate
groups, review issues and exact evidence pointers. Reported GR/EL country/tax
keys and KIMDIS buyer keys remain distinct; unknown/foreign cases stay explicit.
Nine ASCII digits mean a format match, with checksum and authority checks marked
`not_checked`. Name/tax variations merit review; no company identity is accepted.
Candidate groups can overlap and must not be counted as companies or joined
transitively. Registry corroboration and reviewed identity decisions are later work.

The summary prints only counts, policy and report hash. Exit 0 means assessment
succeeded; it certifies neither collection completeness nor archive integrity.
Configuration errors exit 2; incomplete/unsupported inputs, budget, SQL and output
failures exit 1 with a redacted reason. Original source data is unchanged.

The artifact is `<report_sha256>.json` under the output directory. Identical inputs
produce identical bytes; verified existing artifacts are reused without overwrite.
Directories/files are private (0700/0600), symlinks and Git internals are rejected,
and an atomic `.gitignore` protects outputs even inside a checkout. Publication is
atomic on the supported Linux/POSIX filesystem. Killed workers can leave private
temporary files; these are not completed reports. Hashes do not anonymize tax IDs.
See [policy](SPEC-entity-resolution.md) and
[verification](docs/verification/identity-assessment.md).

## GEMI registry snapshots

Configure a personal `NIMA_GEMI_API_KEY` in environment settings, then explicitly
select up to 10 registry numbers:

```bash
uv run --frozen python -m nima ingest gemi \
  --gemi-id REGISTRY_NUMBER --archive-dir data/gemi
```

Repeat `--gemi-id` for multiple numbers. Original input is retained and equivalent
numeric IDs are fetched once per run. The archive-only collector uses the fixed
official HTTPS route, private content-addressed bodies and fresh run manifests.
The API key stays in its request header. Missing/invalid configuration fails before
client/archive creation. Redirects and document/website URL following are disabled.

Profiles retain original text, unknowns, legal/status labels, partial-registration
flags and versioned KAD activities with field pointers. No company/person identity
or active-status mapping is accepted. A 404 is only `not_found_at_observation`.
Exit 0 accounts for every selected ID (200/404); 3 reports quarantine, 1 failure,
2 configuration errors and 130 interruption. Console output is counters/reasons only.

Client bounds are 3 attempts per ID, 20 requests/minute, 20-second HTTP inactivity,
8 MiB bodies and a cooperative 300-second run budget. Projected arrays have a 1,000
entry cap. Limits fail visibly without truncation; Retry-After is honored or the run
stops. After abrupt termination, manifests/derived JSONL may be incomplete: trust
verified raw bodies for reprocessing and start a fresh run. Automatic resume and
SQL/graph integration are later work. This collector has synthetic transport and
process-interruption evidence; credentialed live payload compatibility is unverified.
See [contract](docs/sources/gemi.md) and [verification](docs/verification/gemi-profiles.md).
For pending access, documented Swagger testing and a small credentialed pilot,
use the [access/pilot runbook](docs/verification/gemi-live-pilot.md).

## Data and privacy

Keep original JSON, PDFs, databases, credentials, and investigation workspaces
outside Git. `data/`, `work/`, and local environment files are ignored. Repository
privacy must be confirmed at the remote host; a local Git repository has no
public/private hosting setting.
