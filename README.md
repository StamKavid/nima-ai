# Nima AI

Nima is building Greece-focused company and market intelligence from traceable
public records. Its mission is to make covered commercial relationships,
procurement patterns and observed changes inspectable and reproducible. Company
and sector researchers, procurement analysts and journalists share the same
trusted data and metric definitions.

Start with the [versioned product roadmap](docs/roadmap/v1.0.md),
[v1.0 acceptance contract](SPEC-release-v1.0.md) and
[agent handoff](docs/roadmap/agent-handoff.md). They distinguish implemented
capabilities from proposed release work; the package is currently `0.0.1`.

The planned product combines a temporal relationship graph, sector comparisons,
explainable statistical/ML detectors, and AI-assisted research with citations.
Current code implements bounded KIMDIS contract collection, a private raw-evidence
archive, typed normalization, optional PostgreSQL collection, and durable run inspection.
It also projects reported participation and compares selected stored KIMDIS/GEMI
identifier assertions in private, reproducible review reports.
Self-hosted Prefect can execute explicitly requested KIMDIS workflows while SQL
preserves their identity, budgets and progress across retries.
Local operators can record reversible accept/reject/revoke decisions and export
private resolution snapshots with source provenance and audit history. The local
graph CLI now exports bounded links between selected reported occurrences, exact
contract versions, reviewed unclassified handles and evidence. Broader temporal
relationships, evaluated models and the investigation workspace remain later milestones.
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

## Review stored company matches

The [reviewed-decision runbook](docs/verification/reviewed-decisions.md) covers
explicit database setup, private request/report files, limited operator grants,
accept/reject/revoke, exact request replay and private resolution exports:

```bash
uv run --frozen python -m nima identities review --help
uv run --frozen python -m nima identities resolution --help
```

These offline commands use stored KIMDIS/GEMI facts and need no GEMI key. A
reviewed acceptance is an investigator's occurrence-scoped decision, not verified
issuer authority, corporate ownership or wrongdoing. Attribution remains
`database_principal_only`; no public/multi-user service is exposed. Live GEMI
compatibility, empirical matching quality and production deployment remain gates.

## Export a bounded investigation graph

The [graph runbook](docs/verification/investigation-graph.md) covers read-only setup,
private input/output, focus states, exact limits and measured recovery evidence:

```bash
uv run --frozen python -m nima graph snapshot --help
uv run --frozen python -m nima graph snapshot \
  --report-file data/registry-review/REPORT_SHA256.json \
  --output-dir data/investigation-graph
```

Replace `REPORT_SHA256` with an existing private comparison artifact's hash and
configure `NIMA_DATABASE_URL` privately. Optional `--entity-id ENTITY_UUID` adds a
view within selected review history. The artifact retains the full selection and
embedded comparison/resolution, including private notes. SQL closes before private
0700/0600 publication; identical state reuses identical bytes. No GEMI key or source
request is needed, and graph export changes no authoritative rows.

Source-reported participation, active reviewed links and unknown identity remain
distinct. Contract money is not allocated to joint suppliers or summed into spend.
Real-company source recovery and observed investigator tasks remain product gates;
the CLI's fixture correctness does not establish those outcomes.

## Development

Python 3.12, [uv](https://docs.astral.sh/uv/) and just 1.59.0 are the tested development baseline. Full checks also
require disposable local PostgreSQL 17; configure `NIMA_TEST_DSN` as below.

```bash
sh scripts/install-just.sh
export PATH="$PWD/.tools/bin:$PATH"
just setup
just check
just audit
```

`just check` verifies the installed skills, formatting, lint, types, behavioral
tests, package build, and source security. `just audit` checks locked third-party Python dependencies against
the Python Packaging Advisory Database. The unpublished project is checked
by first-party tests and static analysis rather than a public package database.
These checks cover first-party tooling and implemented collection/review behavior.
They do not prove full-source coverage, production recovery or model quality.
Measured process-kill/retry evidence and its limits are recorded in the runbooks.

## Stage manually captured GEMI evidence offline

The `evidence intake publicity` command preserves manually saved public PDFs or
screenshots in a separate private archive. `evidence verify REQUEST_UUID` checks
its hashes, metadata and completeness without source requests or a database.
Original files are stored as opaque evidence; they are not rendered or extracted.
Supplied company identifiers, origin and capture context remain unverified claims.

Follow the [manual intake runbook](docs/sources/gemi-publicity-fallback.md#manual-intake-runbook)
for the strict input manifest, commands, byte limits, exit codes and replay rules.
Manual acquisition must use a remote browser or a separately verified protected
connection. These offline commands do not deploy or verify that infrastructure.
No live Publicity scraper or automatic API fallback is enabled.

## Verify the controlled fixture boundary

The [fixture delivery runbook](docs/verification/source-worker-egress.md) describes
the Linux/Docker prerequisites and pinned image setup. Run the complete gate:

```bash
just source-worker-check
```

It runs all 12 Docker tests, including the 28-case HTTPX/Chromium matrix, observed
runtime/cleanup, actual failure controls and packet-rule mutation/restoration.
CI uploads one validated canonical full receipt only after the whole gate passes.
The separate runner's `--stage http` interface publishes an explicitly incomplete
18-case report. These tests collect no company data; deployed investigator IP
protection remains unverified.

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
across these CLI invocations is not implemented. The separate Prefect workflow
adds bounded task retries and explicit redispatch. Offset pagination can drift without observable
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
just check
just audit
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
the upstream revision and file hashes. `just skills-check` detects local drift;
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
transitively. The separate comparison command below adds reported registry
agreement; reviewed identity decisions remain later work.

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

## Compare stored procurement and registry evidence

With `NIMA_DATABASE_URL` configured, select a projected KIMDIS run and 1–10
completed GEMI import UUIDs. No GEMI key or source request is needed:

```bash
uv run --frozen python -m nima identities compare KIMDIS_RUN_UUID \
  --gemi-import GEMI_IMPORT_UUID --projection-version kimdis-participation-v1 \
  --output-dir data/registry-review --max-mentions 10000
```

Repeat `--gemi-import` for additional explicit imports. The command preserves
all occurrences, repeated/404 registry observations, conflicts, unknowns and dated
provenance in one private canonical report. Agreements reference a shared catalog;
automatic identity links remain zero. SQL input is bounded at a combined 8 MiB,
100 registry observations and the requested 1–10,000 occurrences; the exact output
ceiling is 32 MiB. Bounds fail without truncation.

Replay verifies and reuses identical bytes at `<report_sha256>.json`. Stdout is
IDs/counts/statuses/hash, with fixed redacted failures and exits 0/1/2/130. Completion
means selected assertions were compared; it does not verify companies or certify
source coverage. Follow the [operator runbook and measured verification](docs/verification/registry-comparison.md)
for setup, interpretation, private publication, interrupted replay and recovery.

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
downstream dispatch from this collector remain later work. Stored SQL imports can
already be reviewed and graphed offline. This collector has synthetic transport and
process-interruption evidence; credentialed live payload compatibility is unverified.
See [contract](docs/sources/gemi.md) and [verification](docs/verification/gemi-profiles.md).
For pending access, documented Swagger testing and a small credentialed pilot,
use the [access/pilot runbook](docs/verification/gemi-live-pilot.md).

## Import archived GEMI evidence offline

Configure NIMA_DATABASE_URL and explicitly migrate, then import one completed,
non-quarantined GEMI collector run. This command needs no API key or provider call:

```bash
uv run --frozen python -m nima db migrate
uv run --frozen python -m nima gemi import RUN_ID --archive-dir data/gemi
```

The importer verifies original bodies and reconciles all selected 200/404 outcomes
before one atomic database transaction. It regenerates assertions from raw JSON;
derived JSONL is not authoritative. Identical replay verifies and reuses the import;
changed evidence or archive location fails without replacing history. The archive
is read-only. Migration 0004 adds separate registry relations and leaves the
procurement outbox unchanged. Failed/incomplete/quarantined runs remain outside
this first import scope. A 404 is an observation, never an entity deletion.

See the [persistence contract](docs/sources/gemi-persistence.md) and
[verification](docs/verification/gemi-persistence.md). Live profile compatibility
still requires the personal-key pilot; synthetic success does not establish it.

## Data and privacy

Keep original JSON, PDFs, databases, credentials, and investigation workspaces
outside Git. `data/`, `work/`, and local environment files are ignored. Repository
privacy must be confirmed at the remote host; a local Git repository has no
public/private hosting setting.

## Local Prefect workflow

The Apache 2.0 Prefect server and runner use the same pinned version (3.9.2).
PostgreSQL holds Nima evidence; a separate SQLite control volume holds local
Prefect state. This is a development stack with loopback host ports and a private
Docker network. It registers a deployment without a schedule. Starting a fresh
stack creates no source request; explicitly submitted queued work can run when
its worker starts again. No cloud account or API key is needed.

```bash
docker compose -f infra/compose.orchestration.yml up --build -d --wait
docker compose -f infra/compose.orchestration.yml exec app python -m nima db migrate
```

Open the local Prefect UI at `http://localhost:4200`. The sample database uses
trust authentication and a loopback port 55433; keep this stack local. For hosts
without `/etc/ssl/certs/ca-certificates.crt`, set `NIMA_CA_BUNDLE` to your trusted
PEM CA bundle before building. TLS verification stays enabled. The hash-locked
image includes development tooling; regenerate its export with `just container-lock`
after a dependency update. Production packaging and operations need a separate review.

To authorize one bounded source collection, generate a new UUID and replace
`REQUEST_UUID` below. Run submission inside the app container so its saved
`/evidence` path is the same path the worker sees:

```bash
docker compose -f infra/compose.orchestration.yml exec app python -m nima workflows submit kimdis \
  --request-id REQUEST_UUID --from-date 2026-11-06 --to-date 2026-11-06
docker compose -f infra/compose.orchestration.yml exec app python -m nima workflows show REQUEST_UUID
```

A successful submit means delivery was accepted, not that collection completed.
`show` reads SQL and reports actual evidence flags separately from job status.
Reusing the UUID with different query/archive parameters fails. Transient task
errors retry automatically; after a killed process or unknown dispatch, inspect
and explicitly redispatch the **same** request UUID:

```bash
docker compose -f infra/compose.orchestration.yml exec app python -m nima workflows dispatch REQUEST_UUID
```

Redispatch can create another Prefect flow run while retaining the original Nima
collection run. SQL leases, checkpoints and receipts govern replay. Saved caps
are 300 provider-attempt reservations, four collection executions, 30 minutes
from first execution and 100 projection batches. Reservations survive crashes.
Exhausted budgets require review; redispatch does not reset them. This workflow does
not schedule graph exports or model execution; live GEMI validation remains separate. See the
[contract](docs/sources/kimdis-orchestration.md) and
[verification record](docs/verification/kimdis-orchestration.md).

Stop services with `docker compose -f infra/compose.orchestration.yml down`.
Volumes retain evidence and control state; deleting those volumes destroys it.

## Bounded daily refresh

The refresh coordinator uses the same local Prefect server and SQL evidence.
Fresh services register both deployments with no active schedules or policies.
A policy selects 1–10 buyer IDs and an explicit coverage start date; its identity,
query settings and archive root are fixed. Create it inside the app container:

```bash
docker compose -f infra/compose.orchestration.yml exec app python -m nima refresh create kimdis \
  --policy-id POLICY_UUID --start-date 2026-11-06 --buyer-id BUYER_ID
docker compose -f infra/compose.orchestration.yml exec app python -m nima refresh plan POLICY_UUID --as-of 2026-11-12
docker compose -f infra/compose.orchestration.yml exec app python -m nima refresh show POLICY_UUID
```

Replace the placeholders with a new UUID and your selected public-buyer ID.
Creation, preview and inspection make no provider request. SQL migration 0006
must be applied explicitly before using refresh commands. The existing manual
workflow commands remain available.

To authorize scheduled collection for that cohort, enable the policy explicitly:

```bash
docker compose -f infra/compose.orchestration.yml exec app python -m nima refresh enable POLICY_UUID
```

The schedule runs daily at 04:00 Europe/Athens. Each cycle reobserves the seven
most recent completed calendar days and selects up to seven oldest missing days,
clipped to the policy start: at most 14 one-day child windows. The coordinator
returns after dispatch; child workflows collect serially with their saved limits.
A worker restart preserves API-managed schedules. To request an immediate cycle
for the current Athens business date or stop new dispatch decisions:

```bash
docker compose -f infra/compose.orchestration.yml exec app python -m nima refresh tick POLICY_UUID
docker compose -f infra/compose.orchestration.yml exec app python -m nima refresh pause POLICY_UUID
```

Repeated ticks reuse their original request IDs. Unknown or failed children block
further dispatch and later cycles. Inspect `blocked_reason` and the child request
IDs; use `refresh recover POLICY_UUID --request-id REQUEST_UUID` for a bounded
retry of the same child while its original budgets permit. See the
[recovery runbook](docs/operations/refresh-recovery.md) for eligibility, unknown
delivery and dispatch caps. Exhausted budgets stay blocked. Audited terminal
resolution/policy supersession remains separately scoped work.

If pause reports `policy_busy`, retry after the short coordinator returns.
Already accepted/running children may finish after pause. `state=pending` means
the SQL gate is disabled and schedule acknowledgement needs reconciliation;
retry enable/pause after restoring the local server. Inspection reports the last
acknowledged schedule state, with worker liveness unknown.

`query_dates_through` reports contiguous completed query dates. `recent_status`
reports whether the current business date's overlap has been reobserved. Both
require complete collection, normalization and projection evidence; neither is a
provider-wide update watermark. Corrections older than the overlap can be missed,
and absence on a recheck is not proof of deletion. See the
[refresh contract](docs/sources/kimdis-refresh.md) and
[verification](docs/verification/kimdis-refresh.md). No policy has been enabled
or live cohort selected by this implementation.

Repository branch cleanup, main/dev protection status, and the Python 3.12/3.14
choice are documented in [repository settings](docs/repository-settings.md).
Opt-in [workflow diagnostics](docs/operations/workflow-diagnostics.md) correlate
application stages with SQL request/run IDs; private log supervision is an
operator responsibility.
