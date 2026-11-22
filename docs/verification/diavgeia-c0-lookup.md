# Diavgeia C0: what type are the ADAs we already hold

Source: Diavgeia (diavgeia.gov.gr), CC BY 4.0; data retrieved on 2026-11-22.
Spec: [SPEC-diavgeia-commitments](../specs/SPEC-diavgeia-commitments.md). Counts only; the archive stays outside Git
(`data/`).

## The run

| Item | Value |
|---|---|
| Command | `nima ingest diavgeia-decisions` with 15 `--ada` values (the 4 ADAs KIMDIS cites and the 11 related ADAs on the collected awards) |
| Run ID | `19603f07-7cd0-443a-9952-5ef93030bf55` |
| Requests | 15, all HTTP 200; 15 found, 0 not found, 0 quarantined; collection complete |
| Kept per decision | type, organisation, status only |

## Result

| Group | Decisions | Type | Organisation | Status |
|---|---|---|---|---|
| ADAs cited by KIMDIS (`diavgeiaADA`) | 4 | **Β.1.3** (commitment) | 2 under `6057`, 2 under `99221065` | all `PUBLISHED` |
| Related ADAs of the collected awards (`textRelatedADA`) | 11 | **Δ.2.1** (tender summary) | all `6` | all `PUBLISHED` |

## What it shows

- **The inference is confirmed for these four:** what KIMDIS's `diavgeiaADA` pointed at in this sample is a Β.1.3
  commitment, not an award.
- **The dossier's reading of an award's related ADA was wrong:** it says Δ.2.2 `textRelatedADA` points at the
  expenditure approval. In all 11 real cases it points at a Δ.2.1 tender summary. The chain
  award → tender summary → commitment (the dossier's Δ.2.1 row) is consistent with this, but only the first link is
  observed here.
- **The cited commitments belong to other bodies:** none is under organisation `6`, the body of the first pilot. A
  Β.1.3 run for organisation `6` could not resolve any of the 4 citations. Resolving them needs organisations `6057`
  and `99221065` (and the window in which each was issued, which the lookup did not keep).
- Four decisions are too few to say how KIMDIS cites in general.
