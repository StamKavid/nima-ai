# Nima AI

Nima helps journalists, investigators, and researchers trace Greek company
relationships and public spending, then develop evidence-backed investigative
leads. Its mission is to make relationships, spending patterns, and changes over
time inspectable and reproducible.

The product combines a temporal relationship graph, sector comparisons,
explainable statistical/ML detectors, and AI-assisted research with citations.
Current code implements bounded KIMDIS contract collection, a private raw-evidence
archive, typed normalization, and an independent transactional PostgreSQL page API.
HTTP run inspection/resume, entity resolution, graph projection, trained
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
There is no automatic resume: after interruption, start a fresh bounded run and
retain the prior run's evidence. Offset pagination can drift without observable
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

The existing HTTP command remains archive-only. Database orchestration, HTTP
attempt history, run inspection/resume, supplier/buyer relational projections,
outbox delivery, and complete-run reconciliation are following increments.
SIGKILL tests verify the page transaction boundary; they do not prove HTTP resume
or database-server/storage-device crash recovery. Keep connection strings in
environment/memory and redact driver errors before exposing them in an interface.

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

## Data and privacy

Keep original JSON, PDFs, databases, credentials, and investigation workspaces
outside Git. `data/`, `work/`, and local environment files are ignored. Repository
privacy must be confirmed at the remote host; a local Git repository has no
public/private hosting setting.
