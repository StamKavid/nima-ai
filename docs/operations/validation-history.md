# Explicit readout validation history

This is the first V1-01 boundary: verify a private, already-published
`nima-supplier-buyers-v1` report and record an immutable outcome in PostgreSQL.
It does not change publication, certify the draft metric, activate a source or
establish publisher accuracy. Other dataset checks and scheduled health
aggregation remain later work. See the [contract](../../SPEC-validation-history.md).

## Setup and access

Schema 0010 adds only `nima_validation.attempts` and `nima_validation.outcomes`.
Existing migration bodies and source tables are unchanged. Apply the reviewed
migration through the existing explicit migration/backup procedure under the
migration owner; this code does not automatically migrate the private pilot.
The package's schema check now requires migration 10.

Keep `NIMA_DATABASE_URL` as the existing source reader. Configure a separate
`NIMA_VALIDATION_DATABASE_URL` through private environment/service settings.
Never put credentials in arguments, request files, logs or Git. The journal
writer must be a non-owner, non-superuser role, with no project-schema CREATE,
source/processing mutation or journal UPDATE/DELETE/TRUNCATE privileges. Direct,
column-level and inherited privileges are considered by the database checks.

After an operator creates the intended roles, its narrow grants are:

```sql
GRANT USAGE ON SCHEMA nima,nima_validation TO VALIDATION_WRITER;
GRANT SELECT ON nima.schema_migrations TO VALIDATION_WRITER;
GRANT SELECT,INSERT ON nima_validation.attempts,nima_validation.outcomes TO VALIDATION_WRITER;

GRANT USAGE ON SCHEMA nima,nima_validation TO VALIDATION_READER;
GRANT SELECT ON nima.schema_migrations,nima_validation.attempts,nima_validation.outcomes TO VALIDATION_READER;
```

Role names are placeholders. No role/grant is created by the application.
For inspection, configure `NIMA_VALIDATION_DATABASE_URL` with the SELECT-only
variant; the source connection is not used. Inspection itself is a read-only
transaction. A source reader with no journal access remains usable for the
unchanged analytics command after the explicit migration.

## Check and inspect

First obtain the existing readout through `analytics supplier-buyers`. Use its
actual lowercase 64-hex artifact hash as the report filename. Then choose a new
canonical UUID and run:

```sh
uv run --frozen python -m nima dataops validate-readout \
  --attempt-id 4ecdf589-b49d-4965-a919-38de6d6ebffe \
  --request /PRIVATE/request.json --report /PRIVATE/reports/SHA256.json
uv run --frozen python -m nima dataops validation-show \
  --attempt-id 4ecdf589-b49d-4965-a919-38de6d6ebffe
```

Replace `SHA256` and the example UUID for a real check. Reports/requests must
remain owner-private, under no-follow private directories. The report is at most
1 MiB; source reconstruction retains all existing cohort/resource limits.
Symlinks, hardlinks, unsafe modes, corruption and changed files are refused.
No report/original is published, replaced, fetched or repaired by these commands.

The journal intent binds semantic request and declared artifact hashes, ODCS
ID/version/hash and validator version. A pass also records verified snapshot and
counts. Start/completion times and effective database principals are stored
separately and stamped by PostgreSQL. No source labels, paths or DSNs are retained
in journal payloads or terminal results. Fixed stage events go to stderr.

## Retry and interpretation

An intent without a terminal row is **pending**. A worker death releases its
session lock; retry the same ID/intent. A concurrent invocation gets a fixed busy
error. Different intent with the same ID is a conflict.

A completed ID returns its original result with `reused: true`. This is an old
attestation, not a fresh file/source check; its recorded time is preserved. Use a
new UUID to check again. Equal fresh results share a deterministic outcome hash
while retaining separate attempt IDs/times. A later missing/corrupt artifact or
unavailable evidence cannot erase an earlier pass.

**Failed** means artifact digest, contract or exact reconstructed bytes disagree.
**Blocked** means the necessary artifact/evidence/SQL inputs cannot be checked.
Only a pass carries a verified snapshot/count claim. Invalid request/name/policy
configuration before a usable intent is not represented as a dataset check.
Successful SQL lookup of a pending record is not a passed validation.

Exit codes: 0 passed (or successful pending inspection), 3 failed/blocked result,
2 configuration, 1 operational/conflict/busy/unavailable, 130 interruption.
A database failure never silently becomes a recorded success. Artifacts predate
this operation; there is no distributed SQL/filesystem commit claim.

History is append-only with no automatic pruning. Source freshness, metric review,
identity uncertainty and coverage remain separate trust dimensions. Passing this
validator does not make captured data national, source-current or legally verified.

## Health of an explicitly selected artifact's journal

With the same restricted journal reader, inspect recorded-check health:

```sh
uv run --frozen python -m nima dataops validation-health \
  --artifact-sha256 SHA256 --max-check-age-hours 24 --max-pending-age-minutes 30
```

Replace `SHA256` with the actual report hash. Both thresholds are required
operator settings: 1–8,760 hours and 1–10,080 minutes. They are not source SLAs.
The command needs only `NIMA_VALIDATION_DATABASE_URL`; it neither runs a new
validation nor reads the report, originals or source database. Its explicit scope
is `recorded_validation_history_only`. Current file integrity and source freshness
remain separate checks.

The complete selected history is read in one repeatable-read read-only snapshot,
with a maximum of 1,000 attempts and 8 MiB of stored JSON. Exceeding a bound fails
without truncation. Cohort queries have a five-second statement/two-second lock
limit; connection/schema/role setup retains the existing limits. Stored hashes
and associations are checked for every row, including older ones. Corrupt history
prevents a verdict rather than being hidden behind a later pass.

`checks_passed` means the latest-started attempt passed under the current bound
contract and validator, its completion is within the age threshold, and no pending
attempt is overdue or clock anomaly present. Earlier failures remain counted;
a later valid pass can resolve their attention. An older late-finishing check
cannot mask a newer failure. Equal latest start times are ambiguous and all tied
IDs are exposed. A cached result does not acquire a new timestamp.

`attention` explains no checks, pending/failed/blocked latest checks, stale checks,
old policy, overdue pending attempts, tied latest starts or clock anomalies.
Exactly-at-threshold ages are fresh/not overdue. Counts, SQL sample time, current
policy, latest IDs/state/times and last current-policy pass time stay visible.
No history exists for a selected hash does not mean its artifact is absent.
Exit 0 means checks_passed; 3 attention; configuration/operational/interruption
codes retain their existing meaning. Output is at most 64 KiB.

This first health view is per declared artifact, not a source-wide or per-run
assessment. It does not change history, certify the draft metric or activate any
schedule. Live journal setup and other dataset boundaries remain separate work.
