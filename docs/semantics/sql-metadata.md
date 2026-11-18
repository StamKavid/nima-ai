# Explicit SQL metadata snapshots

C3 adds durable serving to the [reported metadata contract](market-metadata.md).
Source observations remain in their original ledgers; one immutable JSONB document
is stored per explicitly selected canonical hash. The table and occurrence view
live in `nima_processing`, separate from the 26 original `nima` tables.

```sh
uv run python -m nima metadata promote kimdis --run-id "$RUN_UUID" \
  --archive-dir "$ARCHIVE_DIR" --snapshot-sha256 "$SNAPSHOT_SHA256"

uv run python -m nima metadata query --snapshot-sha256 "$SNAPSHOT_SHA256" \
  --output-dir "$OUTPUT_DIR" --dimension procurement_cpv --code 33141120-7
```

First export an unfiltered C2 metadata artifact. Deliberately select its full
64-character content hash; filtered artifacts cannot be promoted. Promotion rebuilds
and verifies canonical bytes from the source archive and frozen metadata, and
refuses a changed hash. No supplied metadata file is trusted. KIMDIS must be
complete/quarantined and its SQL scope is rechecked under the shared source lease.
GEMI additionally needs the completed archive's matching prior `gemi import`.
There is no implicit source collection, import, archive repair or live migration.

Promotion inserts one row in one READ COMMITTED transaction. Concurrent retries
reuse an identical committed document; conflicting content is refused. Existing
source rows and observation times are not changed. UPDATE, DELETE and TRUNCATE of
the derived snapshots are refused. Processing time and database principal describe
the derived insertion, not a newer source observation.

The read-only query validates the stored canonical hash and supported format in
one REPEATABLE READ snapshot. Parameterized SQL is checked against the shared pure
selection policy before publication. Missing/corrupt/unsupported selections fail;
no match retains full capture/quality coverage. The output reproduces C2's logical
filtered snapshot and canonical bytes. No automatic latest snapshot is selected.

SQL-only reads do not access the archive. Their evidence integrity was checked at
promotion; they do not re-attest current archive availability/integrity or source
freshness. Use the existing archive verification command when that is required.
A raw hash/source pointer remains a reference to evidence, not publisher or legal
identity authentication. Human review is still required for stronger claims.

`nima_processing.reported_market_metadata` exposes snapshot/source/run,
record/assertion positions, hashes, pointers, quality states, reported versions,
original observation time and separate processing time. Always select an explicit
snapshot; positions and repeated observations remain occurrences. Counters are
not company counts, spend, current-state classifications or complete market share.

The primary key is the initial snapshot lookup index. JSON expansion is bounded
at 5,000 records/10,000 assertions and the existing 32 MiB canonical report limit.
No national-scale latency or code-index benchmark is claimed. Materialized fact
indexes should follow measured query needs.

Migration 0009 is explicit. Apply it only after review using the configured owner.
A KIMDIS promoter needs SELECT on schema history/run/page/raw-object metadata and
SELECT/INSERT on the new snapshot table. GEMI also needs its import manifest row.
A serving reader needs schema history plus SELECT on the snapshot table/view and
schema USAGE; it does not need an archive or source-table write grants. Scope role
grants explicitly; there are no automatic broad grants or role membership changes.
Terminal summaries contain fixed status/counts/reuse only, never selected hashes,
source values, IDs or paths. Keep artifact selections and full documents private.

[Official taxonomy assessment](taxonomy-releases.md) remains a separate dictionary
increment. These queries retain `taxonomy_validation: not_checked`; they do not
convert KAD versions, validate CPV membership or infer supplier sectors.
