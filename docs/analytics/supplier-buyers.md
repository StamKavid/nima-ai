# Private supplier–buyer readout

This is a local, offline readout over explicitly selected captured KIMDIS contract
runs. It answers which reported buyer keys appear in those records for a selected
reported supplier identifier. It does not collect sources, start Prefect work,
migrate/project/repair SQL, contact GEMI or recover missing originals from a site.

The [metric contract](../semantics/participation.md) defines counts and exclusions.
The owner-approved [consumer scope](../specs/SPEC-market-analytics.md) defines bounds.
Delivery evidence and the current review checkpoint are in
[tasks](../../tasks/todo.md). This runbook does not establish real-market coverage
or an observed analyst-task benefit; that pilot remains separate.

## Prerequisites

Use Linux/POSIX, Python 3.12+, the locked application environment and PostgreSQL 17. The
database must already have the supported seven checksummed migrations and the
selected managed runs must be `complete`, without quarantined records. Every
observation needs its supported projection facts, mentions and receipt. The
command fails on incomplete selections; it never drains projections itself.

Keep request files, originals, credentials and outputs outside Git. Input and
archive directories must be owner-private (0700), with regular private files
(0600); descriptor-relative reads reject unsafe paths and symlinks. Supply each
archive binding explicitly: a path saved in SQL is not filesystem authorization.

Configure `NIMA_DATABASE_URL` through your private environment/secret mechanism,
using the dedicated read role below. Do not paste a connection string into a
command argument, shell history, issue or chat. No `--database-url` or API-key
flag exists. A GEMI key, proxy or VPN is unnecessary for this offline command.

## Read-role setup

An administrator performs setup separately. The command never creates roles or
changes grants. Adapt the database name `nima` and authentication to your private
deployment; the example deliberately contains no password:

```sql
CREATE ROLE nima_analytics_reader LOGIN;
GRANT CONNECT ON DATABASE nima TO nima_analytics_reader;
GRANT USAGE ON SCHEMA nima TO nima_analytics_reader;
GRANT SELECT ON
    nima.schema_migrations, nima.ingest_runs, nima.run_pages, nima.raw_objects,
    nima.observations, nima.record_versions, nima.quarantine,
    nima.projection_contracts, nima.projection_mentions, nima.projection_receipts
TO nima_analytics_reader;
```

Use a non-owner, non-superuser role without inherited/public write privileges,
schema CREATE, sequence mutation or column write grants. Do not grant a broad
writer group to this reader. Runtime preflight checks privileges in the Nima
schema, including inherited and column grants; this is not a whole-database
sandbox or a deployed multi-user authorization system. Existing development
compose credentials are not a suitable read-role substitute.

## Selection and execution

The following values are synthetic placeholders. Replace the UUID, reported
tax ID, UTC cutoff and absolute archive path with your actual selected capture.
The query window is retained from the run, not supplied or broadened here.

```json
{
  "version": "nima-participation-request-v1",
  "source": "kimdis.contract",
  "run_ids": ["11111111-1111-4111-8111-111111111111"],
  "observation_cutoff": "2026-11-16T23:59:59+00:00",
  "supplier_country": "GR",
  "supplier_tax_id": "012345678",
  "archive_bindings": [
    {
      "run_id": "11111111-1111-4111-8111-111111111111",
      "root": "/ABSOLUTE/PRIVATE/kimdis"
    }
  ]
}
```

Save this closed JSON object in a 0600 file under a 0700 private directory.
Duplicate/unknown/missing fields, malformed identifiers, non-UTC cutoffs and
unsafe bindings fail. Use distinct canonical UUIDs and exactly one binding per
run; the decoder canonicalizes run/binding order. `GR` is the only request
country. The identifier rule is syntactic, without checksum or legal verification.

From the project environment, with `NIMA_DATABASE_URL` already privately set:

```sh
uv run --frozen python -m nima analytics supplier-buyers \
  --request /ABSOLUTE/PRIVATE/readout-request.json \
  --output-dir /ABSOLUTE/PRIVATE/readouts
```

Success returns exactly `status`, `artifact_sha256`, `record_count`, `buyer_count`
and `outcome`. The private artifact is `<artifact_sha256>.json` in the specified
0700 directory, with mode 0600. Names, identifiers, dates, source values and
citations stay in that artifact. `buyer_count` excludes the separate unassigned
bucket; it is not a market or legal-company count.

| Outcome | Interpretation within the selected capture |
|---|---|
| `empty_capture` | No observations; original empty pages were verified |
| `no_observations_before_cutoff` | Captured records exist, all after the cutoff |
| `selection_unresolved` | No eligible match; unassessed/ambiguous candidates or unknown supplier lists remain |
| `no_observed_participation` | Pre-cutoff records exist without an eligible match or the unresolved cases above |
| `observed_participation` | Eligible matches exist; unresolved cases remain separately disclosed |

None establishes absence from the actual market. A future cutoff does not imply
data was observed through that date. Use the run query windows and first/last
page capture times to understand actual coverage.

## Verification and limits

One read-only, repeatable-read UTC transaction freezes complete selected SQL
facts and checks the reference SQL result. SQL closes before any original read
or output publication. Every selected page is recovered and re-normalized,
including empty, earlier-revision, nonmatching and after-cutoff pages. Full
projection fields and supplier/buyer ordinals are reconciled, not just digests.

| Bound | Ceiling |
|---|---|
| Private request | 16 KiB |
| Selected runs / observations | 10 / 500 |
| Selected pages / physical archive object locations | 32 / 32 |
| SQL payload | 8 MiB |
| Original object / combined recovered bytes | 8 MiB / 64 MiB |
| Canonical result | 1 MiB |
| SQL statement / lock timeout | 30 s / 5 s |

Exceeding a ceiling fails; nothing is truncated. Choose a smaller explicitly
documented cohort. Coverage reports count logical unique raw digests; physical
recovery work is separately bounded. Moving identical originals or deduplicating
their storage does not change report bytes. Request bindings, output paths,
connection details and current wall time are excluded from result identity.

Inspect `quality` dimensions separately: verified original bytes, reconciled
projections, reported-only identifiers, selected-run coverage, unestablished
source-current status, unverified legal identity and record-level lineage.
The metric definition remains `draft`; code approval does not certify a metric
or publisher truth. Source money stays exact text; this command computes no spend,
payment, concentration, ownership or wrongdoing signal.

## Failures and recovery

| Exit | Meaning |
|---|---|
| 0 | A verified result, including a legitimate zero/unresolved outcome |
| 2 | `analytics_configuration` or structurally invalid `analytics_input` |
| 1 | Private-file, SQL/schema/role, coverage/projection/evidence, archive, limit or output failure |
| 130 | Ctrl+C caught during command execution: `analytics_interrupted` |

Caught failures print only `status=failed` and a fixed `failure` code. SIGKILL
terminates the process without a summary; its shell status is platform-dependent
(often 137), rather than a command-generated error code.

Missing/corrupt originals and inconsistent SQL never become zero counts. Check
the selection, private permissions, explicit bindings and existing ingestion/
projection records through their separate operator workflows. Restore damaged
originals only from your independently verified backup; this command does not
fetch or repair them. Do not disable immutability triggers or edit evidence to
force a readout through. Privileged corruption in tests is fixture setup only.

After an interruption, stop the original process and retry the same command.
Verified identical input produces identical bytes and hash; an existing identical
final artifact is reused without replacement. A conflicting or unsafe output
fails without overwrite. A final artifact may already exist if termination
occurred after its atomic link but before the terminal summary; replay verifies it.

SIGKILL can leave private `.tmp-*` files containing the complete proposed result.
They are not published reports and retries do not automatically delete or repair
them. Keep them private; cleanup/storage policy is separate. Existing reports,
SQL rows and original bytes remain unchanged by the readout.

The tests exercise real SIGKILL and Ctrl+C before original verification and on
both sides of final publication, then replay the uninstrumented module command.
These checks establish offline command behavior, not backup/restore readiness,
normalizer-version migration/replay, refresh recovery or deployed monitoring.

```sh
uv run --frozen pytest tests/test_analytics_cli.py \
  tests/test_market_analytics_failures.py tests/test_market_analytics_crash.py
just check
just audit
```

Use only the disposable local PostgreSQL 17 test DSN for verification. A protected
real-data cohort and observed analyst task remain the product validation gate.
