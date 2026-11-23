# Diavgeia R2: the three commitment runs, stored and replayed

Source: Diavgeia (diavgeia.gov.gr), CC BY 4.0; data retrieved on 2026-11-23.
Spec: [SPEC-archive-replay-sources](../specs/SPEC-archive-replay-sources.md). Counts only; the archives, the replay
files and the database stay outside Git.

## The runs

The three windows of [the C2 record](diavgeia-c2-commitments.md) were collected again with
`nima ingest diavgeia --database --decision-type commitment`, each approved separately by the owner, into a new
archive and the owner's local database. The first three archives stay as the original evidence. Each run was one
page, one attempt, complete, with nothing quarantined, unidentified or duplicated.

| Window | Organisation | Issue dates | Run ID | Records |
|---|---|---|---|---|
| a | `6057` | 2026-10-25 to 2026-10-27 | `64366eec-932b-4de9-ab64-4685528503f4` | 2 |
| b | `99221065` | 2026-10-04 to 2026-10-06 | `c455803b-be10-4537-8903-ea8f547b3c93` | 13 |
| c | `99221065` | 2026-08-17 to 2026-08-19 | `c31f3bb1-3b8b-4a76-a19c-44daa4b353b6` | 17 |

## Replay

`nima archive replay --source diavgeia-commitment` rebuilt each run offline from its archived originals, with no
request. Every replay reported all of its records normalised and none quarantined (2, 13 and 17).

| Check | Result |
|---|---|
| Replayed records equal the new run's own normalised records, field for field | All 32 |
| Replayed records equal the first archives of 2026-11-23 | All 32; the same ADAs and amounts at a second observation |
| Records with an unknown amount | 20 of 32 (10 in b, 10 in c); replayed as unknown, not zero |
| Each replayed record's source id | `diavgeia:<ADA>` |

The comparison leaves out the evidence block and `source_id`, which the file archive does not carry.

## What it shows

- Stored Diavgeia commitment data rebuilds from the original bytes through the same command as KIMDIS.
- Two observations of the same window, hours apart, gave the same records. That says the source did not change
  in that time, not that it never changes.

## What it does not show

- Nothing was promoted into the replay tables; that needs an owner-selected digest.
- No downstream reader (analytics, metadata, identity) accepts Diavgeia rows; that is the deferred item in
  [SPEC-source-neutral-collection](../specs/SPEC-source-neutral-collection.md).
