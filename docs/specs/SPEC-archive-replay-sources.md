# Source-aware archive replay and promotion

Status: approved 2026-11-23; R1 to R4 decided as recommended. R1 delivered in review; R2 next.

## Objective

`nima archive replay` and `nima archive promote` rebuild normalised records from committed original bytes and store
a chosen rebuild in SQL. Both only work for KIMDIS runs. The two Diavgeia pilots (awards, commitments) were
collected through the same engine and page store, but their runs cannot be replayed or promoted from the command,
so their stored data cannot be shown to rebuild from the originals the way the contract requires.

This spec makes both commands work for any registered page-store source, starting with `diavgeia` and
`diavgeia-commitment`, with KIMDIS behaviour and bytes unchanged.

## What is known

Read from the code on 2026-11-23:

| Fact | Where |
|---|---|
| The replay functions already accept an adapter (`read_capture`, `prepare_replay`); the two entry points `replay_run` and `promote_run` do not pass one, so they use KIMDIS | `dataops/replay.py`, `dataops/promotion.py` |
| A run of another source is refused with `replay_source` because its stored connector version differs | `replay._snapshot` |
| The archive recovery is typed by page-store layout, labelled `kimdis`, and is shared by every adapter that writes through the page store | `PAGE_ARCHIVE` in `dataops/replay.py` |
| The replay and promotion tables do not name a source; only the artifact carries `source` and the source run's connector version | migration `0008.sql` |
| `nima archive verify` checks page hashes only, but reports its scope as `kimdis_committed_pages_only` | `dataops/archive.py` |
| The command validates its input before any database access; 11 tests pin that order | `tests/test_archive_replay_cli.py`, `tests/test_replay_promotion_cli.py` |
| Both Diavgeia adapters have the name `diavgeia`, so their replay artifacts share `artifact_version` and `source`; the connector version in `source_run` tells them apart | `dataops/replay._dataset` |
| **Replay needs the run in SQL.** The three commitment runs of 2026-11-23 were collected with `--archive-dir` only, so they exist as file archives, not as `nima.ingest_runs` rows | run records in `docs/verification/` |

Found while building R1: promotion requires `normalized.source_id` to equal the record's source id (a database
check, `0008.sql`). KIMDIS records carry that key; Diavgeia records keep the id beside the record. The replay
now adds `source_id` from the adapter's own record id when the key is absent. KIMDIS replay bytes do not change
(their records already carry it, pinned by a test); Diavgeia replay artifacts gain that one key. This is the only
change to a replay layout and is called out for the owner at review. Before it, promotion of a Diavgeia run
failed with a missing key.

Not known (settled by R1: `adapter_for` builds an adapter that can normalise without a query): whether `adapter_for("diavgeia")` builds an adapter that can normalise a page without a query. The first
pilot's replay called the adapter directly. Slice R1 settles it with a test before any other work.

## Behaviour

- `archive replay` and `archive promote` take `--source <registered key>`, default `kimdis`. The key is checked
  against the registry before any database access, so the input-check order and the 11 pins are unchanged.
- The chosen adapter's connector version must equal the run's stored one, else the existing `replay_source` failure.
  The normaliser version must equal the adapter's, else `replay_version`, as today.
- A KIMDIS run replays to the same bytes and the same digest as before. This is a characterisation test taken from
  unmodified `main` before any change.
- Replay of the same run twice gives the same digest; promoting the same selected digest twice stores nothing new
  (existing behaviour, tested for the new sources).
- Failure reasons stay the fixed set already used. No source value, path or driver text is printed.

## Boundaries

**Always:** characterise KIMDIS first; tests before code; synthetic fixtures; fixed reasons; promotion only of an
explicitly selected digest; unknown stays unknown (the 20 null amounts replay as null, never zero).

**Ask first:** any live request, any migration, a change to the replay artifact layout, any downstream reader
(analytics, metadata, identity) of promoted Diavgeia rows.

**Never:** change the bytes or digest of an existing KIMDIS replay; guess the source from file contents; merge
award and commitment records into one economic event; real decisions in Git.

## Slices

| Slice | Content | Done when |
|---|---|---|
| R1 | Characterise KIMDIS replay and promotion. Add `--source` and pass the adapter through `replay_run` and `promote_run`. Tests with synthetic award and commitment runs: replay, repeat digest, promotion, repeat promotion, wrong source, unknown source key | Gates pass, 100% line and branch on new code, every new guard caught by a mutation check, KIMDIS tests unchanged |
| R2 | Owner-approved: collect the three commitment windows again with `--database`; replay each; check that the replayed records equal the file archive's normalised records; promote only if the owner selects a digest. Record counts in `docs/verification/` | Replays reproduce the 2, 13 and 17 records; counts recorded, no decision content |

Each slice is one review-ready PR. R2 contains the owner's live steps and needs a local database.

## Decisions for the owner

R1 to R4 are decided as recommended (owner, 2026-11-23).

| # | Decision | Recommendation |
|---|---|---|
| R1 | How the command picks the adapter | An explicit `--source` flag, default `kimdis`. The alternative, reading the stored connector version, needs a database read before input checks and changes the 11 pinned tests; it also hides which source the operator meant |
| R2 | How the three existing commitment runs reach SQL | Collect them again with `--database` (about 3 requests in total, each approved). The alternative, an offline import of a file archive into `nima.ingest_runs`, is a new write path and a new trust boundary to save 3 requests. The first three archives stay as the original evidence |
| R3 | The two Diavgeia replay artifacts share a name and `source` label | Leave as is. Changing `artifact_version` would alter the digest of the award replay already recorded; the connector version in the artifact already separates them |
| R4 | `archive verify` reports scope `kimdis_committed_pages_only` for any source | Leave in this change; it is a pinned output string and only a label. Revisit when a third source is verified |

## Deferred, with triggers

| Item | Trigger |
|---|---|
| Offline import of a file archive into SQL | A source whose runs cannot be re-collected (a closed source, or a one-off capture) |
| Downstream readers of promoted Diavgeia rows | The owner names a dataset to consume (see the deferred row in SPEC-source-neutral-collection) |
| Renaming the `verify` scope string | A third source passes through `verify` |
| Choosing the adapter from the stored connector version | Operators run replay without knowing the source |
