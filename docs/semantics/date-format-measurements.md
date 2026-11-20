# Measured KIMDIS date formats and tax-ID classes

Running log for the V1-05 time model ([SPEC-semantic-model](../specs/SPEC-semantic-model.md), slice S2).
Numbers and shapes only: no date, name, tax number, amount or title is recorded here. A shape
replaces each ASCII digit by `9` and every character outside `9 / . : + , space -` by `A`
(`scripts/semantic_census.py`). The parser in S2b is written only for shapes that appear below.

## Capture provenance

The earlier pilot database lived in a ChatGPT cloud sandbox that is not reachable, so the
measurement was rebuilt from fresh captures. On 2026-11-20 the owner waived the rule that source
services must not see the investigator's home IP for **one small capture** of the public KIMDIS
API from this machine (no key involved). It was run through the existing bounded collector, inside
a Linux container, into a local PostgreSQL 17 database that Git does not track. The owner then
approved and ran a second, wider capture of the same public buyer on the same day (run 2). Both
are dated exceptions for those captures only, not a change to the rule.

## Measurements

| # | Cohort (bounded request) | Records | Run result |
|---|---|---|---|
| 1 | One calendar day, one public buyer (the README example), default limits | 4 | Complete, 1 page, 0 quarantined, count equal to the source's announced total |
| 2 | About 90 days (2026-08-08 to 2026-11-05), the same buyer, default limits, run by the owner | 199 | Complete, 4 pages in 6 attempts (two retried), 0 quarantined, count equal to the announced total |

A first attempt at run 2 failed with `invalid_page` and stored no page: the container saw CRLF line
endings in the packaged contract files. It is kept as failed evidence and is excluded from the
figures below.

### Census over runs 1 and 2 together (203 records, 203 stored versions)

| Field | Result |
|---|---|
| `source_submitted_at` | 203 of 203 present; two shapes: `9999-99-99A99:99:99.999` (188) and `9999-99-99A99:99:99.99` (15). Same layout; the fraction of a second has three or two digits. No zone suffix in either. |
| `source_updated_at` | missing or null in 172, present in 31; one shape, `9999-99-99` (a **date only**, a different shape from the submission date) |
| Supplier lists | 203 non-empty, 0 empty, 0 missing |
| Supplier tax IDs | 221 occurrences: 86 nine-digit with a leading zero, 132 other nine-digit; 3 needed whitespace trimming; 2 shorter than nine and 1 longer than nine; no all-zero, repeated-digit, sequential, non-ASCII or missing cases |
| Supplier countries | GR 220, CY 1 (so the three irregular-length IDs carry country GR) |
| Revisions | 203 versions for 203 records: no record changed between observations in this sample |

Run 1 alone (4 records) showed the first of the two submission shapes, no update dates, three
leading-zero IDs and the CY supplier.

## What follows for the time model

- The submission date is an ISO local date-time without a zone. Under decision D2 a zone-less value
  is read as Europe/Athens civil time and the result says so; nothing else is inferred about the
  instant it denotes.
- The fraction of a second has two or three digits in the sample. **Decision, 2026-11-20 (owner:
  "recommended"):** S2b accepts a fraction of one to three digits; anything else, including no
  fraction and four or more digits, stays `unparseable`, counted and never guessed.
- No value in the sample carries a zone suffix or offset, so S2b has no zone conversion: a
  zone-less value is read as Europe/Athens civil time and says so, and a value with a zone suffix
  or offset is `unparseable` until a measured shape justifies a rule. No time zone database and no
  daylight-saving logic are needed for the observed shapes.
- The update date is a different, date-only shape and is absent in most records. It is never an
  ordering key.
- A leading zero is common in real tax numbers (86 of 221), so it is a valid identifier shape and
  never a placeholder signal. Decision D4 needs no new rule from this sample: there are no all-zero,
  repeated-digit or sequential IDs in 221. Irregular-length IDs with country GR (3 of 221, about
  1.4 percent) are ineligible under the existing nine-digit rule and are disclosed, not dropped.
- A foreign (CY) supplier appears, so foreign identifiers must stay visible and outside the Greek
  nine-digit grouping rules.
- One buyer over about 90 days says nothing about other buyers. More buyers would show whether other
  shapes, empty supplier lists or more foreign identifiers occur.
