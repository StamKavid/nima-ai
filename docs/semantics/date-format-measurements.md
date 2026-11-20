# Measured KIMDIS date formats and tax-ID classes

Running log for the V1-05 time model ([SPEC-semantic-model](../specs/SPEC-semantic-model.md), slice S2).
Numbers and shapes only: no date, name, tax number, amount or title is recorded here. A shape
replaces each ASCII digit by `9` and every character outside `9 / . : + , space -` by `A`
(`scripts/semantic_census.py`). The parser in S2b is written only for shapes that appear below.

## Capture provenance

The earlier pilot database lived in a ChatGPT cloud sandbox that is not reachable, so the
measurement was rebuilt from a fresh capture. On 2026-11-20 the owner waived the rule that source
services must not see the investigator's home IP for **one small capture** of the public KIMDIS
API from this machine (no key involved). It was run through the existing bounded collector, inside
a Linux container, into a local PostgreSQL 17 database that Git does not track. A wider capture
needs its own approval. This is a dated exception for that capture only, not a change to the rule.

## Measurements

| # | Cohort (bounded request) | Records | Run result |
|---|---|---|---|
| 1 | One calendar day, one public buyer (the README example), default limits | 4 | Complete, 1 page, 0 quarantined, count equal to the source's announced total |

### Run 1

| Field | Result |
|---|---|
| `source_submitted_at` | 4 of 4 present; one shape, `9999-99-99A99:99:99.999` (ISO date and time with milliseconds, no zone suffix) |
| `source_updated_at` | missing or null in 4 of 4 |
| Supplier lists | 4 non-empty, 0 empty, 0 missing |
| Supplier tax IDs | 4 occurrences: 3 nine-digit with a leading zero, 1 other nine-digit; no all-zero, repeated-digit, sequential, other-length, non-ASCII or whitespace cases |
| Supplier countries | GR 3, CY 1 |

## What follows for the time model

- The submission date seen so far is an ISO local date-time without a zone. Under decision D2 a
  zone-less value is read as Europe/Athens civil time and the result says so; nothing else is
  inferred about the instant it denotes.
- A leading zero is common in real tax numbers (3 of 4), so it is a valid identifier shape and
  never a placeholder signal. Decision D4 still stands: only the all-zero rule excludes a key.
- A foreign (CY) supplier appears even in four records, so foreign identifiers must stay visible
  and outside the Greek nine-digit grouping rules.
- Four records of one buyer on one day prove one format and nothing about variety. S2b stays open
  until a wider capture shows whether other shapes, missing submission dates or irregular tax
  IDs occur.
