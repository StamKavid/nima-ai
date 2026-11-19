# PostgreSQL and original-evidence restore drill

This operator procedure continues the owner-authorized DataOps work after #123.
It verifies a bounded private pilot restore on an isolated local PostgreSQL 17
cluster. It is not a scheduled backup service, off-host recovery, point-in-time
recovery or an automatic source/workflow failover command.

## Contract and acceptance

Use the existing native PostgreSQL 17 `pg_dump` and `pg_restore` tools. No new
Python application dependency, schema migration or CI job is required. Keep
credentials, dumps, originals, comparison data and native logs outside Git in
0700 directories/0600 files. Services/credentials belong in a private
`PGSERVICEFILE`; pass service aliases, not credential-bearing DSNs, to tools.

Success requires all of the following, recorded privately:

- A source snapshot, native custom dump, all referenced original bytes and a
  hash manifest whose identity is retained separately from the bundle.
- Restore into a fresh, differently identified local PostgreSQL cluster/database,
  with a NOLOGIN application owner and recreated scoped daily roles. Never restore
  over the source or an existing populated destination.
- Equivalent application table contents, sequence state, columns/constraints,
  indexes, views/functions/triggers and the packaged migration history. Record
  empty tables; copying an empty table does not exercise populated history.
- Archive verification for every captured run under explicit relocated roots,
  and an identical private readout using a SELECT-only reader and relocated
  request bindings. Source SQL and original files remain unchanged.
- Actual wrong-password/write-denial and immutable-row checks on the destination;
  deliberate missing/corrupt destination evidence must prevent a valid result.
  A deliberately incomplete dump must fail restoration, not become success.
- Stop only the newly owned destination cluster; verify the source remains
  reachable. Retain private proof and the backup; do not delete evidence to clean up.

An incomplete check yields an incomplete drill, not a successful restore. Keep
human/source-authority and market-usefulness validation separate.

## Prepare a private case

Record exact source/destination identity, PostgreSQL/native-tool versions, approved
archive locations, selected request, original readout and expected schema scope.
This procedure covers the pilot's `nima` schema. Inventory non-system schemas,
extensions and external dependencies before using a schema-only dump elsewhere;
reject unexpected dependencies rather than silently omitting them. This drill
exercises KIMDIS collector originals; any additional archive-bearing source/manual
records need their own complete bindings/copy checks before a whole-deployment
recovery claim.

Quiesce application writers and schedules for this drill. Export a read-only
repeatable-read snapshot with `SELECT pg_export_snapshot()` and keep its exporting
transaction open during `pg_dump --snapshot`. Compute table/counter/schema
comparisons against that same snapshot. Sequences are not snapshot-isolated:
compare their values before/after and require the stated quiescent interval.

Copy all pilot collector archives, including incomplete discovery and unindexed
files, into the private bundle. Verify every SQL `raw_objects` digest/length has
its matching bytes there; retain explicit archive/run bindings. Copy the request
and frozen report. Hash every bundle file and keep the manifest hash in a separate
private control record. Recheck the bundle before restoration. A hash establishes
consistency with retained bytes, not publisher truth or authenticated off-host custody.

Example native command shape; paths, aliases and snapshot are private operator
configuration, not missing values the project silently guesses:

```sh
umask 077
export PGSERVICEFILE=/absolute/private/control/pg_service.conf
NIMA_PG_BIN=/absolute/path/to/postgresql-17/bin
NIMA_BACKUP_DIR=/absolute/private/backup
"$NIMA_PG_BIN/pg_dump" --dbname=service=nima_source --format=custom \
  --schema=nima --strict-names --no-owner --no-privileges \
  --snapshot="$NIMA_EXPORT_SNAPSHOT" --file="$NIMA_BACKUP_DIR/nima.dump"
"$NIMA_PG_BIN/pg_restore" --list "$NIMA_BACKUP_DIR/nima.dump" \
  > "$NIMA_BACKUP_DIR/contents.txt"
```

Set `NIMA_EXPORT_SNAPSHOT` from the exporter’s returned ID. Hold that transaction
in its operator process until the dump finishes.
Check exit status and retain stderr privately. Never execute a dump from an
untrusted source as though it were inert data.

## Restore into an isolated destination

Initialize a fresh owned data directory with SCRAM authentication on loopback,
its own socket/port and a unique cluster identity. Keep bootstrap credentials
separate from the backup. Precreate an empty database from `template0` and a
NOLOGIN nonsuperuser application owner. A database dump does not recreate cluster
roles. Recreate reader/ingest/project roles with new credentials and approved
scoped grants; do not copy source passwords or assume ACLs were restored. Confirm
actual schema/table/sequence/function owners in the catalog. The earlier drill
found that connector timeout options replaced the requested migration role. The
role-preservation increment below fixes connection setup; existing object owners
still require explicit maintenance. Native restore uses explicit role selection.
After recreating each role, run `dataops access-grants` for its profile, review and
apply the output, then run `dataops access-audit` against the restored database and
keep the report with the rehearsal record. See the
[access audit](access-audit.md). It checks catalogue privileges and evidence
triggers only; it does not replace the byte, row and archive checks below.

```sh
"$NIMA_PG_BIN/pg_restore" --dbname=service=nima_restore \
  --role="$NIMA_RESTORE_OWNER" \
  --no-owner --no-privileges --exit-on-error --single-transaction \
  "$NIMA_BACKUP_DIR/nima.dump"
```

Do not use `--clean`, `--create`, `--disable-triggers` or a populated destination.
Restore the entire controlled schema-scoped dump. Do not repeat a restore-time
`--schema=nima` filter: in the tested PostgreSQL 17 tool it omits the SCHEMA entry
and fails on a fresh destination. Restore all sections, including post-data
constraints/indexes/triggers. Run
`ANALYZE` on the destination after a successful restore. Restore credential/grant
configuration separately; bootstrap/owner access is not a daily reader identity.

## Verify application behaviour

Compare all `nima` tables by row count and an ordered full-row digest, using UTC
and deterministic C ordering. Compare sequence `last_value`/`is_called` plus
sequence definitions; compare catalog definitions independently of OIDs/owners.
Native SQL roundtrips can change harmless CHECK expression grouping. Accept a
difference only when reparsing the exact source CHECK on matching temporary
column types reproduces the target definition, with retained boundary/truth-table
checks; otherwise stop. Do not drop constraints or ignore mismatched definitions.
Ownership is intentionally remapped and grants are checked against the recreated
policy, not byte-compared with omitted source ACLs. Compare effective table and
column permissions, sequence/function privileges and schema/database boundaries
for each daily role. The reader grant list is in the
[readout runbook](../analytics/supplier-buyers.md). Validate packaged migration
checksums without applying migrations to repair a failed restore.

Copy originals into new private archive locations. Keep the source bundle
unchanged. Under the destination reader configuration:

```sh
uv run --frozen python -m nima archive verify --run-id RUN_UUID \
  --archive-dir /absolute/private/restored-archive
uv run --frozen python -m nima analytics supplier-buyers \
  --request /absolute/private/restored-request.json \
  --output-dir /absolute/private/restored-readouts
```

Only archive bindings change in the private request; run IDs, cutoff, supplier
selection and frozen metric remain the same. Compare actual output bytes with the
original report, not just its count. Exercise missing and same-length corrupt
files only in the disposable restored copy, require verification/readout failure,
and restore those test bytes from the immutable bundle before a final good replay.
Never edit original SQL/evidence or invent a passing result.

The restored SQL retains historical absolute paths. Explicit bindings permit
these offline checks at new locations; they do not implement path-independent
source resume. Do not run `runs resume` during this drill: it can fetch sources.
A blob-store port, normalizer-version replay and refresh recovery remain separate.

## Limits and continued operation

This is one bounded local restore. It does not prove an off-host copy, encryption
policy, retention schedule, disaster RPO/RTO, production volume, operating-system
recovery or restored external orchestration state. Quiescence is an operational
precondition, not a new backup coordinator. A future deployment needs separately
owned off-host retention and periodic drills before relying on it for recovery.

Primary references: [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html) and
[SQL dump recovery](https://www.postgresql.org/docs/17/backup-dump.html).


## Connection roles and existing-owner repair

The connector honours ordinary PostgreSQL startup settings from the DSN,
`PGOPTIONS` or a private service. PostgreSQL authenticates and checks the requested
role; an invalid or unauthorized role is an error, never a fallback. Connection
setup then applies `SET statement_timeout = 30000` and `SET lock_timeout = 5000`
in autocommit mode before returning it. The existing 5 s connect timeout remains.
Setup failures/interruption close the connection and propagate. These are session
settings; they do not update role/database defaults or application rows. Caller
startup limits can cause setup to fail; no unbounded connection is returned.

A fresh migration with an authorized NOLOGIN owner in startup `options` creates
schema/tables/sequences/functions under that role. Role membership and CREATE
privileges must already permit the operation; the connector grants nothing.
Do not assume migration replay changes old object owners automatically.

For an existing bounded pilot, first retain and verify the native backup, quiesce
writers, record current owners and require the expected bootstrap owner plus the
already-configured NOLOGIN database owner. Use a migration advisory lock and one
transaction with the standard timeouts. Change only `nima` schema/project tables,
views, sequences and functions through qualified identifiers; table-owned indexes
and sequences move with their table. Stop on unexpected owners/dependencies.
Do not use cluster-wide `REASSIGN OWNED`, alter unrelated roles or rewrite rows.
Record inverse ownership statements privately for a rollback plan. Verify actual
catalog owners, all table/counter contents, effective daily grants, archived bytes
and byte-identical readout afterward. The prior drill remains evidence for its
original snapshot; an ownership repair is a separate recorded maintenance action.

Regression commands: `uv run --frozen pytest tests/test_connection.py tests/test_postgres.py`,
`just check`, `just audit`. The database tests use disposable local PostgreSQL 17;
they do not touch the private pilot. New deployments must check actual ownership,
not merely configuration. No source requests or model dependencies are needed.

References: [Psycopg connections](https://www.psycopg.org/psycopg3/docs/api/connections.html)
and [PostgreSQL session SET](https://www.postgresql.org/docs/17/sql-set.html).


The bounded private pilot repair was performed after #124: the verified native
backup was retained, expected project owners were changed in one advisory-locked
transaction, and all 26 table data/counters, logical schema, archived originals,
daily-role capabilities and reader-result bytes stayed unchanged. Role-bound
migration replay and archive checks pass. Private prior-owner/inverse records and
full proof remain outside Git. This resolves that pilot's ownership gap; it does
not silently reassign existing deployments or certify a general production role
policy. The dated restore record remains its historical pre-repair assessment.

The role-preservation increment passes eleven new connection cases and the five
migration regressions; full local gates pass 1,995 tests/93.04% with a clean audit.
Restoring the old options override fails the ownership regression. Hosted status
is recorded with its delivery PR. No CI job accesses the private repair proof.
