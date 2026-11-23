# GEMI AFM lookup, L6: first live search and profile check

Source: GEMI Open Data API (opendata-api.businessportal.gr), ODC-BY-1.0; data retrieved on 2026-11-23.
Spec: [SPEC-gemi-afm-lookup](../specs/SPEC-gemi-afm-lookup.md). Counts only; no AFM, name or registry
number is recorded here, and the archives stay outside Git (`data/`). Run by the owner with their own key,
each live step approved separately.

## Runs

| Run | What | Requests | Result |
|---|---|---|---|
| 1 | `ingest gemi-afm`, two AFMs: one personal AFM and the wrong-check-digit AFM `123456789` | 2 | 404 (3.7 s) and one `hit_single` (10.5 s) |
| 2 | `ingest gemi-afm`, three AFMs of large listed legal entities | 3 | three `hit_multiple`, 12 companies, all HTTP 200 (10.5, 9.2, 4.1 s; 108, 77 and 14 KB) |
| 3 | `ingest gemi`, the head-office profile of each AFM of run 2, by registry number | 3 | 3 found, none quarantined (2.4 to 6.1 s) |

Runs 1 and 2 verify offline with `nima gemi verify-afm`. One earlier attempt was refused before any request
because PowerShell had dropped the leading zero of unquoted AFMs; nothing was sent.

## Findings

- **The parser reads the live answer.** Every 200 answer parsed to a hit outcome; none was quarantined.
- **No match is a 404**, as documented, not an empty list.
- **Branches repeat the head office AFM.** Each searched AFM returned one head office and 1 to 4 branches (5, 2
  and 5 hits), and every hit reported the queried AFM. The spec's open question is answered.
- **Deleted registrations are returned.** 3 of the 12 hits carry a deletion status (one by merger). They are
  evidence of history, not a current company, and any comparison must keep their status.
- **No result was truncated** (`totalCount` at most the 20 requested).
- **Equivalence of a hit and its profile (D3):** for the 3 head offices, every normalized field is equal. In
  one company the title lists (`titles_el`, `titles_en`) hold the same 7 titles in a different order. As sets
  they are equal.
- **The probe was wrong.** I called `123456789` impossible because its check digit is wrong. The registry
  holds an active company (not a sole proprietor) under that AFM. The AFM check digit says nothing about
  whether a registry record exists, and no AFM should be sent as a "cannot exist" probe.
- **A personal AFM returned 404**, so no personal record came back. Personal AFMs are not to be queried.
- **Latency** is 4 to 10.5 s for a search and 2.4 to 6.1 s for a profile; no request came near the 60 s
  request timeout.

## Not shown

- Only three companies, all large and all listed; small companies and sole proprietors are unmeasured.
- Whether title order is stable between two calls of the same endpoint.
- No SQL import exists yet (slice L5).
