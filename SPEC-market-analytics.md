# Spec: cited supplier–buyer readout

Module ID: `market-analytics`. Status: **bounded CLI readout implemented;
human product validation remains open**. See [current delivery](docs/progress.md).
This original slice contract remains authoritative; broader insights/serving
are proposed in the [v1.0 release contract](SPEC-release-v1.0.md).
Follows the owner-approved [capability map](CAPABILITIES.md), merged in
[#108](https://github.com/StamKavid/nima-ai/pull/108). Depends on the provider
contract in [SPEC-semantic-layer.md](SPEC-semantic-layer.md); that module owns
metric meaning. These two narrow specifications form one data-to-readout slice.
The owner merged [#109](https://github.com/StamKavid/nima-ai/pull/109) at `70e06d6`
on 2026-11-16 and requested continuation. The subsequent
[implementation plan](tasks/plan.md) subsequently delivered this bounded readout.
Original proposal wording below describes its scope, not current delivery state.

## Objective and scope

A company/market researcher selects a reported Greek supplier and captured
KIMDIS runs, then receives a private, reproducible buyer readout with inspectable
contributing records and original evidence. The first question is: **which public
buyers repeatedly appear in these captured records reporting this supplier?**

Success means one command produces the provider's tested counts, revision
decisions and coverage disclosures. A protected real-data pilot and one observed
analyst task then test whether it saves manual work. No success claim follows
from fixtures or PR counts. No web service, AI, graph store or new source is needed.

## Proposed interface

This command is a future interface, not an existing executable feature:

```sh
uv run --frozen python -m nima analytics supplier-buyers \
  --request /PRIVATE/readout-request.json \
  --output-dir /PRIVATE/readouts
```

Connection comes from `NIMA_DATABASE_URL`, never a command-line secret or echoed
value. The private request is a closed JSON object of at most 16 KiB:

| Required field | Rule |
|---|---|
| `version` | Exact `nima-participation-request-v1` |
| `source` | Exact `kimdis.contract` |
| `run_ids` | 1–10 distinct canonical UUID strings |
| `observation_cutoff` | Explicit UTC ISO-8601 timestamp, inclusive |
| `supplier_country` | Exact `GR` |
| `supplier_tax_id` | Provider's nine-ASCII-digit nonzero rule |
| `archive_bindings` | Exactly one `{run_id, root}` per selected run; absolute private archive root |

Reject duplicate keys, unknown/missing fields, malformed types, unsafe paths and
unsupported versions. Bindings are explicit operator inputs; stored archive paths
do not authorize arbitrary filesystem reads. Source values, identifiers, private
paths and driver exceptions stay out of terminal errors. This is a local trusted
operator tool, not an authentication or multi-tenant boundary.

## Snapshot, completeness and bounds

Read through bound SQL parameters in one read-only, repeatable-read UTC
transaction. Preflight counts/byte sizes before fetching payloads; apply a
30-second statement timeout and 5-second lock timeout. Close SQL before reading
archives or publishing output. No source request, workflow dispatch, migration,
projection drain, SQL mutation or archive repair occurs.

The first version accepts managed `complete` runs using the provider's supported
versions. Validate run/page/checkpoint totals, unique source IDs, quarantine
absence, observations/versions and every selected observation's projection
receipt, facts and party ordinals. A complete collection status is not proof of
national or market completeness. Reject missing/partial/quarantined/unsupported
runs or incomplete projections; never turn them into a plausible zero count.

The cutoff limits observation eligibility, not run completeness. Record each
run's query window and all captured page times, including observations after the
cutoff. A future cutoff does not imply data was observed up to that date. All
selected runs/pages are verified even if a cutoff excludes their records.

| Resource | First-slice ceiling |
|---|---|
| Selected runs | 10 |
| Observations across those runs, before cutoff/filtering | 500 |
| Selected pages / archive object locations | 32 each |
| SQL snapshot payload | 8 MiB, including normalized records, facts, mentions and provenance |
| Original bytes | 8 MiB per object, 64 MiB combined |
| Canonical result | 1 MiB |

Bounds fail with a fixed reason; do not truncate results or raise source limits.
They bound this pilot rather than claim a production latency/scale target.
Select a smaller explicitly documented cohort when a bound is exceeded.

## Original-evidence reconciliation

Recover every selected committed page, including empty responses, from explicitly
bound archives. Use existing descriptor-relative, owner-private, no-follow reads,
archive marker checks, hash/byte verification and changed-file detection.
Directories/files remain 0700/0600; do not initialize an archive while reading it.

Re-normalize recovered bytes with the supported public normalizer. Compare page
metadata, record hashes, source IDs, normalized values and JSON pointers with SQL;
derive the projection again and compare fact/mention contents and digest. Validate
all cohort records, not only matching suppliers: otherwise corrupted records can
disappear from a result. Hash agreement alone does not establish source truth.

Reuse `graph.pilot_archive.recover` and public normalizer/projection interfaces
where their contracts fit. A narrow shared evidence helper extraction may be
planned if necessary; do not duplicate the verifier or introduce cross-module
private imports. The semantic provider stays independent of these adapters.

Missing/corrupt/changed originals or inconsistent SQL end in a fixed failure with
no result artifact. Successful reconciled outcomes distinguish:

| Outcome | Meaning |
|---|---|
| `empty_capture` | Selected complete runs contain no observations; original empty pages verified |
| `no_observations_before_cutoff` | Runs contain records, but none were observed by the cutoff |
| `selection_unresolved` | No eligible match, but a same-tax unassessed/ambiguous candidate or unknown supplier list remains |
| `no_observed_participation` | Pre-cutoff records exist, with no eligible match or the unresolved cases above |
| `observed_participation` | At least one eligible match; unresolved candidates remain separately disclosed |

None implies company absence from the actual market. Invalid/unusable identifier
occurrences and all other coverage limitations remain visible in every outcome.

## Result and reproducibility

Publish `nima-supplier-buyers-v1` canonical JSON into an explicitly private output
directory, with SHA-256 content naming and atomic no-clobber behavior. Reuse an
identical artifact; conflicting/partial/unsafe output fails without overwriting or
repair. Terminal success contains only the artifact hash, counts and fixed states.
All source labels and evidence details remain in the private artifact.

The artifact includes:

- Metric ID/definition hash/review status; source/stage and transformation versions.
- Canonical request identity (source, sorted run IDs, cutoff and supplier key),
  selected cohort/windows, selected observations and a deterministic snapshot
  digest. Archive bindings/paths are local access configuration, excluded from
  that identity and the result; relocating identical inputs preserves the result.
  No database connection string or credential is serialized.
- Buyer rows with distinct record counts and cancellation breakdowns, unassigned
  records, matching ordinals, unassessed keys/lists and revision ambiguities.
- Evidence index for counted, superseded and unresolved records: source/version,
  observation/time, run/page/index, raw SHA-256 and JSON pointer. Retain selected
  observations so filtering and latest-version decisions can be audited.
- Explicit coverage, byte/projection reconciliation and reported-only identity
  status, plus the provider's interpretation limits.

Stable ordering and semantic input bytes determine the result. Exclude random IDs,
current wall time and output paths from its hashed payload. A later capture,
definition or projection version produces a different input/result identity.
Re-running against unchanged input reproduces byte-identical results.

## Database access and structure

Use a dedicated non-owner, non-superuser read role with schema usage and SELECT
only on required relations. Reject owner/superuser or write-capable sessions for
this new command. Validate privileges, including inherited/public access, against
the Nima schema; this is not a claim of whole-database sandboxing. Operator setup
documents exact grants; the command never creates roles or changes permissions.
Existing commands and their privilege assumptions remain unchanged.

Expected read relations are `schema_migrations`, `ingest_runs`, `run_pages`,
`raw_objects`, `observations`, `record_versions`, `quarantine`, `projection_contracts`,
`projection_mentions` and `projection_receipts`. No schema migration is required.
Test that all existing 26 tables are unchanged by success and failure paths.

Use existing Python 3.12+, PostgreSQL 17, Psycopg and private artifact primitives.
Place query/reconciliation/command code in `src/nima/analytics/`, delegating from
the root CLI; put operator instructions in `docs/analytics/` and focused tests in
`tests/test_market_analytics.py` and focused `tests/test_analytics_*.py` modules.
Keep domain semantics in the provider module.
Do not put calculation logic in the CLI dispatcher. A narrowly public connection
interface can be planned without a broad storage/kernel/package rewrite.

## Commands, style and verification

Existing full gates (use only the disposable PostgreSQL 17 test DSN):

```sh
just check
just audit
```

Proposed focused command after implementation:

```sh
uv run --frozen pytest tests/test_semantics.py tests/test_market_analytics.py
```

Follow locked Ruff, strict mypy and existing frozen typed result conventions.
Bind values rather than interpolate SQL, for example:

```python
row = connection.execute(
    "SELECT status FROM nima.ingest_runs WHERE run_id = %s",
    (run_id,),
).fetchone()
```

Pytest must exercise real disposable PostgreSQL 17 and real private files, not
mock away transactions, privilege checks or filesystem failures. Reproduce the
provider's hand-calculated answer (B1=3, B2=1, unassigned=1), then verify cutoff,
empty capture, no match, incomplete projections, missing/changed originals,
malformed input, privilege refusal, bounds and deterministic retries. Confirm SQL
is closed before archive work and no source/network route is invoked. Reuse
existing adversarial publication tests; test interruption at this command's
boundary without duplicating the whole storage harness. Coverage stays at least
90%; all existing required CI jobs remain.

## Product validation and approval boundaries

After offline delivery, run one bounded real-data cohort from authorized protected
archives. Sample identity grouping, revisions, counts and citations against
originals. Observe one consenting analyst (the owner may be first) completing the
same supplier/buyer task manually and with the readout. Record time, errors,
missing information and whether each result is understandable. No target speedup
is claimed before measurement. No automatic contact with another person is implied.

- Always: preserve evidence/history, return explicit coverage, keep originals
  outside Git, and run required verification before proposing merge.
- Ask first: source activation, changed metric semantics, new dependencies,
  migrations, CI or a shared/live service. Preserve the operator's IP requirement.
- Never: fetch missing originals directly, treat missing data as zero, make
  legal-identity/fraud claims, mutate historical requests or silently broaden a
  selected cohort. GEMI, egress and reliability backlogs retain their own scopes.

Next gate: owner review of the proposed implementation plan. Protected pilot
archives are not assumed available; if absent, record that pilot as blocked rather
than substituting synthetic data for product validation. No live run is implied.
