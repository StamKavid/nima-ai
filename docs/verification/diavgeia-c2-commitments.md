# Diavgeia C2: three commitment (Β.1.3) runs

Source: Diavgeia (diavgeia.gov.gr), CC BY 4.0; data retrieved on 2026-11-23.
Spec: [SPEC-diavgeia-commitments](../specs/SPEC-diavgeia-commitments.md). Counts only; the archive stays outside Git
(`data/`).

## The runs

Command: `nima ingest diavgeia --decision-type commitment`, one organisation and one window of issue dates per run,
each approved separately by the owner. Every run was one page, one attempt, complete, with nothing quarantined,
unidentified or duplicated, and the record count equal to the count the source reported.

| Run | Organisation | Issue dates | Run ID | Records | Cited ADAs found |
|---|---|---|---|---|---|
| A | `6057` | 2026-10-25 to 2026-10-27 | `5241cf25-3158-4696-a8b6-1a0a9f11bc77` | 2 | 2 |
| B | `99221065` | 2026-10-04 to 2026-10-06 | `e2e77687-2d7a-436e-9de7-88a81c2c1ae1` | 13 | 1 |
| C | `99221065` | 2026-08-17 to 2026-08-19 | `28807e87-6b9b-4474-ab7d-61145e11a04a` | 17 | 1 |

32 records, 32 distinct ADAs.

## Result

- **All 4 ADAs that KIMDIS cites resolve** to a collected, `PUBLISHED` Β.1.3 commitment (C3 overlap: 4 of 4).
- All 32 records are Β.1.3 and `PUBLISHED`; all have document type ΠΡΑΞΗ.
- **Amounts are often unknown:** 12 of 32 have an amount (EUR); in the other 20 the source gives `amountWithVAT`
  as null (run B 10 of 13, run C 10 of 17, run A none). They stay unknown, not zero.
- None has KAE lines, a supplier, a related partial ADA or the partial flag, so those adapter paths are unexercised
  by real data.

## What it does not show

- A window holds every commitment of that body on those days, so this proves that these citations resolve. It says
  nothing about coverage or about how KIMDIS cites in general.
- Whether commitments carry KAE lines or suppliers in other bodies or periods is unknown.
