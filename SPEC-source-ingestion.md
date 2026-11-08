# Spec: KIMDIS contract ingestion

Module: `source-ingestion` in `CAPABILITIES.md`.

Status: draft for user review. This is the first application feature; its
implementation plan and code follow approval. The repository bootstrap is
separately authorized by the request to install skills and establish delivery.

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

Proposed application interface, to be implemented after this spec is approved:

```bash
uv run python -m hellenic_integrity ingest kimdis \
  --from-date 2026-11-06 --to-date 2026-11-06 \
  --archive-dir data/raw

uv run python -m hellenic_integrity runs show RUN_ID
uv run python -m hellenic_integrity runs resume RUN_ID
```

The PostgreSQL connection is configured through the environment, never a CLI
argument likely to be logged. Commands emit a run ID and a final structured
summary. An incomplete or failed collection exits nonzero. A successful HTTP
response alone does not make a collection successful.

## Pipeline

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

## Project structure

Implementation will grow from the existing package as the feature requires:

```text
src/hellenic_integrity/
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

The current 90% coverage gate applies to bootstrap tooling only. The ingestion
plan must explicitly extend coverage scope to implemented application modules
and define data-integrity checks; bootstrap coverage is not product coverage.

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

## Approval gate

The installed `.agents/skills/spec-driven-development/SKILL.md` says:
"Stop after writing the spec (CRITICAL)." It requires human review before
implementation planning. This application spec is therefore saved for review;
no KIMDIS collector implementation or implementation task plan is included yet.
