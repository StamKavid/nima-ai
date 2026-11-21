# Diavgeia pilot: first real run (D3) and overlap measurement (D4)

Source: Diavgeia (diavgeia.gov.gr), CC BY 4.0; data retrieved on 2026-11-22.
Spec: [SPEC-diavgeia-pilot](../specs/SPEC-diavgeia-pilot.md). Counts only: no decision content, names or
tax numbers are recorded here, and the archive stays outside Git (`data/`).

## The run

| Item | Value |
|---|---|
| Command | `nima ingest diavgeia --database --organization 6 --from-date 2026-10-08 --to-date 2026-11-06` |
| Request | `GET` search, organisation `6`, type `Δ.2.2`, `status=all`, issue dates 2026-10-08 to 2026-11-06, page size 100 |
| Run ID | `0f00b10c-2d6f-4b92-8f65-39ddd30c51e7` |
| Pages / requests | 3 pages, 3 requests, engine defaults (20 a minute, stop on error) |
| Records | 262 of 262 expected; collection complete; no duplicates, none without an identifier |
| First outcome | 252 normalised, 10 quarantined (exit 3) |
| After the adapter fix below | **262 normalised, 0 quarantined**, re-run offline on the preserved archive |
| Archive | preserved at `data/local-pilot/diavgeia-raw`; the engine's archive-first rule held |

## What the real data showed

- The documented response shape matched. The production path prefix and the `org`, `type`, date and
  `status` parameters worked as documented; every record returned belonged to organisation `6` and
  type `Δ.2.2`. Organisation `6` is the Ministry of National Defence (its name and tax number
  agree with the KIMDIS records for key `6`).
- Status mix: 238 `PUBLISHED`, 24 `REVOKED`, none `PENDING_REVOCATION`. The default search would have
  hidden the 24 revoked, so `status=all` was needed.
- 255 of 262 carry an award amount. 66 list persons; their tax-number type is a short code (`EL` in 65,
  `EUP` in 1), not the descriptive text the documentation suggests. What the codes mean is unverified, so
  the strict no-person-fields rule stands.
- No decision is flagged `private_data`. 9 carry a `correctedVersionId`. 11 name a related ADA.
- Rule 1 of the spec held: absent data is data. Two real shapes had been treated as errors:
  `awardAmount` with a currency and no amount (7 records) and an empty `textRelatedADA` meaning "none"
  (3 records). The adapter now reads both as unknown.

## Reconstruction from the archive

On 2026-11-22 the run was replayed offline from its preserved originals (private 0700 and 0600 copy, no
request) with the replay function and the Diavgeia adapter:

| Adapter | Pages | Records | Normalised | Quarantined | Second replay |
|---|---|---|---|---|---|
| As first run (strict) | 3 | 262 | 252 | 10 | identical digest |
| With the fix in this change | 3 | 262 | 262 | 0 | identical digest |

Both replays use the same 3 original pages as the database, and the fixed replay contains the content hash
of every one of the 252 records stored from the first run. So the stored data can be rebuilt from the
originals, and the first-run quarantine was reprocessed from the raw bytes, not copied from SQL.

**Finding:** `nima archive replay` always normalises with the KIMDIS adapter, so it refuses a Diavgeia
run with a version error. The replay above called the function with the adapter directly. Making the
command choose the adapter from the run's stored connector version means resolving the run before the
input checks, which today fail before any database access (11 existing tests pin that). It needs its own
small design, and is recorded here, not done. Promotion of a replay into SQL is likewise KIMDIS-only.

## Overlap with KIMDIS (D4)

| Measure | Result |
|---|---|
| KIMDIS records stored locally | 1,317 (2026-11-06 capture), 4 cite a Diavgeia ADA (0.3%) |
| KIMDIS records of buyer `6` that cite an ADA | 0 of 77 |
| Cited ADAs that are one of the 262 collected awards | 0 |
| Related ADAs on collected awards that KIMDIS cites | 0 of 11 |

There is nothing to resolve for this body: the KIMDIS explicit key is not used by its records, and the
four cited ADAs belong to other buyers. That is not evidence about other bodies. The result also fits the
expectation that `diavgeiaADA` points at commitment decisions, not at award decisions.

## What this does and does not show

It shows the adapter, the engine and the archive work on a real second feed, that the normalised
records are usable and that the run reconstructs from its originals. It does not show a link between the two sources, national coverage, or that other
organisations or decision types look the same. The next questions, each for the owner, are whether to try one more body, whether the commitment type
(Β.1.3) is worth a second pilot, since that is what KIMDIS cites, and whether to make the replay command
source-aware.
