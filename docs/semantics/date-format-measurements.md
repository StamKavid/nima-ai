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
| 3 | One calendar day (2026-11-06), **all buyers**, default limits, run by the owner | 1,118 | Complete, 23 pages in 29 attempts, 0 quarantined, count equal to the announced total and to the 1,118 records over 23 pages recorded in `SPEC-source-ingestion.md` for the same day |

A first attempt at run 2 failed with `invalid_page` and stored no page: the container saw CRLF line
endings in the packaged contract files. It is kept as failed evidence and is excluded from the
figures below.

### Census over runs 1 and 2 together (203 records, 203 stored versions)

Superseded by the larger census below; kept because it is what the first S2b decision was based on.

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

### Census over runs 1 to 3 (1,317 records, 1,317 stored versions)

Four of run 1's records fall on the same day as run 3, so 203 + 1,118 - 4 = 1,317 distinct records.

| Field | Result |
|---|---|
| `source_submitted_at` | 1,317 of 1,317 present; four shapes, all `9999-99-99A99:99:99.` followed by a fraction of three digits (1,198), two (102), one (13) or **six** (4). No zone suffix in any. |
| `source_updated_at` | missing or null in 1,195, present in 122; one shape, `9999-99-99` (date only) |
| Supplier lists | 1,317 non-empty, 0 empty, 0 missing |
| Supplier tax IDs | 1,374 occurrences: 610 nine-digit with a leading zero, 748 other nine-digit; 4 needed whitespace trimming; 2 nine characters that are not all digits, 6 shorter and 8 longer than nine; no all-zero, repeated-digit, sequential, non-ASCII or missing cases |
| Supplier countries | GR 1,357, CY 6, CH 5, US 3, BG 1, ES 1, ZA 1 |
| Revisions | 1,317 versions for 1,317 records: no record changed between observations |

Irregular tax IDs (16 of 1,374, about 1.2 percent) are ineligible under the nine-digit rule and are
disclosed. Seventeen occurrences carry a non-GR country, so foreign identifiers are real but rare.

A defence buyer found in run 3: the Ministry of National Defence, source key `6`, 77 records that day.
No buyer with an army or general-staff name appeared that day. Validating `--buyer-id 6` against a
filtered capture is a separate step (it must return exactly those 77 records).

## What follows for the time model

- The submission date is an ISO local date-time without a zone. Under decision D2 a zone-less value
  is read as Europe/Athens civil time and the result says so; nothing else is inferred about the
  instant it denotes.
- The fraction of a second has one, two, three or six digits. **Decision, 2026-11-20 (owner:
  "recommended"):** S2b accepts a fraction of one to three digits. After the 1,317-record census
  showed six digits on 4 records, the parser accepts one to six, as the plan allowed for any newly
  observed shape; seven or more digits and no fraction stay `unparseable`, counted and never
  guessed. The owner is told of this extension in the PR.
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
