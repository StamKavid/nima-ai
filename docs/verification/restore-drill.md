# Native PostgreSQL and evidence restore — 2026-11-17

**Result: passed for the bounded private pilot on a fresh local cluster.** This
executes the [operator procedure](../operations/backup-restore.md) after the owner
merged #123 at `3e35bc4` and requested continuation. All three exact-head jobs for
#123 passed in run 44098176598. No application, migration, dependency lock, CI,
source schedule or source-worker implementation changed.

This is native SQL-plus-file recovery, distinct from the earlier JSON checkpoint
and archive relocation check. Both the source and destination are in the same
managed-cloud workspace; no off-host recovery or production RPO/RTO is claimed.

## Method and retained proof

The tools and both servers were PostgreSQL **17.11**. The missing client package
was extracted into user-owned workspace tools after verifying the Debian signed
release, package-index digest and package digest with the installed Debian archive
keyring. No system repository or Python runtime dependency changed.

The source pilot had no running collection and no activated schedule. A privileged
backup operator exported a read-only repeatable-read snapshot, kept it open during
`pg_dump --snapshot`, and computed the source inventory against that snapshot.
The custom dump covers the `nima` schema. Inventory rejected unexpected non-system
schemas/extensions; this method does not silently claim other deployments' scope.
Sequence state and source rows/files were compared before and after the quiescent
operation because sequence counters are not snapshot-isolated.

The private bundle retains the native dump/TOC, all pilot collector archives,
request, original readout, SQL inventory and every-file hash manifest. Nested
collector `manifest.json` files are included; only the bundle's own manifest is
excluded from its member list. The manifest identity is retained separately in
private control evidence. Every SQL raw-object hash/length has corresponding
copied original bytes. The bundle is rechecked before and after restoration.

The destination used a fresh data directory, loopback port/socket and different
PostgreSQL system identifier, SCRAM authentication, an empty `template0` database
and a NOLOGIN nonsuperuser application owner. Native restore used
`--no-owner --no-privileges --role=... --exit-on-error --single-transaction`.
Daily ingest/project/reader roles received new credentials and explicit grants;
source roles/passwords were not restored from global SQL.

Private proof retains native stdout/stderr, source/restored full-row and catalog
comparisons, explicit archive mappings, role matrices, constraint proof, original
and restored reports, failure checks and cleanup observations. Source-derived
counts, identifiers, records, evidence hashes, credential/configuration files and
one-off operator helpers remain outside Git.

## Observed checks

| Check | Observed result |
|---|---|
| Entire application contents | All 26 tables have equal row counts and ordered full-row digests; populated and empty tables are listed privately |
| Sequences | Definitions and `last_value`/`is_called` agree |
| Schema | Columns, constraints, indexes, views, functions, triggers and packaged migration history agree under the documented native CHECK reparse proof |
| Destination ownership | Database/schema, tables, sequences and functions belong to the explicit NOLOGIN application owner |
| Effective daily roles | Source/restored ingest, project and reader policies agree at database/schema, table, column, sequence and function levels |
| Authentication and writes | Wrong reader password rejected; reader UPDATE denied; owner UPDATE rejected by the restored immutable-row trigger |
| Original evidence | Every captured run passes the archive command at its relocated private root, retaining stored complete/partial status |
| Readout | Actual module CLI and programmatic path reproduce the original report byte-for-byte under the destination reader |
| Missing/corrupt evidence | Missing and same-length corrupt destination bodies fail verification; corrupt evidence produces no readout; no missing-body repair occurs |
| Incomplete dump | TOC still parses; native restore fails and leaves no `nima` schema in the separate empty failure-test database |
| Source preservation | Original SQL inventory, sequence state and archive files remain unchanged; no additional source HTTP request |
| Cleanup | Only the new owned destination is stopped; status confirms it is stopped and the source reader still connects |

## Findings resolved or retained

**Source ownership gap, retained as a follow-up.** The earlier private bootstrap's
NOLOGIN role owns its database, but its schema/relations are owned by the bootstrap
principal. The connection helper replaces DSN `options` with its timeout settings,
so the requested migration role did not take effect. This was confirmed through
the actual connector and catalog, not inferred from configuration alone. The
source was not altered during the drill. Explicit native `--role` establishes the
intended ownership in the restored destination. Refine migration/bootstrap role
selection before shared deployment; daily scoped grants are separately verified.
Do not claim the source schema already had the intended owner.

**Restore-time filter, corrected in the procedure.** Repeating `--schema=nima` on
`pg_restore` omitted the SCHEMA TOC entry in the tested native tool, causing
function creation to fail on the fresh destination. The dump is already scoped;
restoring its whole controlled archive creates the namespace and dependencies.
No precreated application schema or ignored restore error masks the problem.

**CHECK representation, proven rather than ignored.** Native restore flattens one
associative AND tree in the `identity_review_events` rationale constraint. Raw
catalog strings therefore differ. The exact source CHECK DDL was reparsed by
PostgreSQL on a temporary table with the same column types; its resulting
definition equals the restored constraint. Ten null/blank, byte-boundary and Greek
text cases give identical three-valued results for both expressions. All other
catalog definitions are exact comparisons. No constraint was removed, relaxed or
skipped to pass the drill; the original/restored/reparsed forms are retained.

Earlier failed preparation/comparison attempts are retained privately. Only the
completed assessment, including deliberate failures and verified cleanup, is
labelled passed. Native restore success alone was not treated as acceptance.

## Limits and next work

The backup and source remain on the same workspace. No off-host copy, encryption/
retention service, scheduled backup, independent-machine failure, production-scale
restore time or external Prefect-state recovery was tested. Some application tables
are empty in this pilot; the drill does not exercise populated history for them.
Role policy was recreated and checked, not recovered from cluster-global backups.

Historical absolute paths remain in SQL. Explicit bindings allow archive/readout
checks at new locations; old workflow/source resume at a new path remains separate.
No source continuation, normalizer-version replay, freshness/correction sweep,
Greek-model evaluation, sector projection or user task was performed by this drill.
The metric remains draft and PV10 human validation remains open.

Next: refine the ownership/version/replay contracts, then expose structured buyer
activity/CPV/reported KAD metadata before isolated model enrichment. The owner’s
GLiNER/Decide direction remains a candidate evaluation, not production adoption.

Full local `just check` passes **1,984 tests/93.03%** combined coverage, with clean
lint/types/build/security/secret/skill/lock checks; `just audit` reports no known
advisories. No tests were added to mirror prose. Actual native restore and failure
checks are the separate private operational proof above. Exact-head hosted status
is recorded with the delivery PR; CI does not execute this private native drill
or access its originals.
