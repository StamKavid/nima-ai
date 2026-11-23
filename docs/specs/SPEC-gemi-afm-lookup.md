# Spec: GEMI lookup by reported tax number (AFM)

Module ID: `gemi-afm-lookup`. Status: **decisions D1-D6 recorded as recommended by the owner on
2026-11-20 ("recommended for D1 to D6"); L2 may start, L5 still needs its own migration approval.** Depends on the delivered [GEMI profile contract](../sources/gemi.md), the
[GEMI persistence contract](../sources/gemi-persistence.md) and the approved
[registry comparison](../identity/registry-comparison.md). It extends, and does not replace,
`GET /companies/{arGemi}` collection (`nima ingest gemi`).

## Objective

A KIMDIS supplier or buyer carries only a reported tax number (ΑΦΜ); the GEMI profile is keyed
by the registry number (`arGemi`). Today a person must find the registry number by hand before
anything can be collected, so the KIMDIS-to-GEMI comparison cannot start from the data we
already hold. This module looks up a small, explicitly chosen set of AFMs in the GEMI Open Data
API, archives every response, and records which registry profiles the registry itself returns
for each AFM. It adds **evidence and candidates, never a decision**: no identity link is
created, no hit is chosen for the investigator, and no absence is read as proof that a company
does not exist.

Success looks like: given up to 25 AFMs, one command produces a verifiable private archive and a
per-AFM outcome table; the existing comparison can then use the returned profiles unchanged.

## Verified facts about the endpoint

From the provider's published OpenAPI document (`/api-docs`, retrieved 2026-11-20) and the first
live checks the same day:

- `GET /companies` returns the companies that meet all given criteria (logical AND); at least one
  criterion is required. `afm` is a string of exactly nine characters; leading zeros must be
  supplied. `resultsSize` is 1-200 (default 10), `resultsOffset` starts at 0, default sort is
  `+arGemi`.
- A 200 answer has `searchMetadata` (`totalCount`, `resultsOffset`, `resultsSize`) and
  `searchResults`, an array of complete `Company` objects. The schema declares `resultsSize` as a
  string although the request parameter is an integer.
- Provider status codes: 400 (client input), 404 (no company), 500, 503. **No company is a 404, not
  an empty list.** The provider's message adds 401 for a bad key and 429 above 8 requests per
  minute.
- Observed live: a name search returned complete profiles, including activities, persons, capital
  and branch registry numbers, and `arGemi` as a JSON **string**. A single large profile needed
  about 29 s to the first byte and 33 s in total. Search latency for small companies is not yet
  measured.
- The same AFM can belong to more than one registry record (a head office and its branches carry
  separate registry numbers); branches repeat the head office AFM (verified in L6).

## Assumptions (correct me before I proceed)

1. One operator, key in `NIMA_GEMI_API_KEY`, collection on Linux (the archive code does not run on
   Windows). The home-IP waiver recorded on 2026-11-20 covers the keyed API only.
2. Only AFMs that the existing identifier policy treats as eligible are queried: reported
   country GR or EL, nine ASCII digits, not `000000000`. No other value is sent.
3. A search hit has the same fields as `GET /companies/{arGemi}`. This is **unverified** and is
   checked in the live pilot (L6) before the hit is trusted as profile evidence.
4. Searching never discovers companies by name and never lists a registry; there is no "all
   companies like this" feature.

## Behaviour

### Request

One request per AFM: `GET /companies?afm=<AFM>&resultsSize=20`, header `api_key`, over the
existing GEMI transport (HTTPS, no redirects, identity encoding, body size cap, retry rules). The
AFM is validated before any network call and sent exactly as given, with its leading zeros.
Requests share the 8 per minute budget and run strictly one at a time. Duplicate AFMs in one run
are sent once and keep their input provenance.

### Archive before parse

The complete response body, including 404 and error bodies, is stored and hashed before it is
parsed, in a private archive outside Git, with the same manifest discipline as `ingest gemi`
(attempt `started` before the request, one attempt per state change, fixed failure codes).
Connector version `gemi-afm-search-v1`; normalizer reuses `gemi-company-v1` for each hit.

### Outcomes per queried AFM (fixed vocabulary)

| Outcome | Meaning |
|---|---|
| `hit_single` | HTTP 200, one company, its reported `afm` equals the queried text |
| `hit_multiple` | HTTP 200, several companies, all returned, every reported `afm` equals the queried text |
| `truncated` | `totalCount` is larger than the number of hits returned; the returned hits are kept, eligible for comparison, and marked incomplete so no agreement is read as the whole answer |
| `afm_mismatch` | A returned company reports a different or missing `afm` than queried; the hit is archived, flagged, and never counted as agreement |
| `not_found_at_observation` | HTTP 404; says nothing about whether the company exists or ever existed |
| `failed_<code>` | 400, 401, 429 after retries, 5xx or a transport failure, using the existing fixed failure codes |
| `quarantined` | The body does not match the expected shape; raw evidence kept |

A hit is never selected for the investigator: with several hits all are kept side by side.
`hit_multiple` and branches are reported, not resolved.

**Precedence.** One response gets one outcome, chosen in this order: `quarantined`, then
`afm_mismatch` (any returned company with a different or missing `afm`), then `truncated`, then
`hit_multiple`, then `hit_single`. Each hit also carries `afm_matches`, so matching hits stay
eligible when another hit of the same response mismatches, and `truncated` is also kept as a
separate flag. An HTTP 200 with an empty `searchResults` contradicts the documented 404 and is
`quarantined` (`empty_results`) so the real behaviour is seen, not guessed.

### Registry number type

Each hit's `arGemi` is accepted as an integer or a canonical decimal string (already supported by
the parser) and stored as `gemi:<number>`. The queried AFM, the registry number, and the
company's own reported AFM are three different fields and are kept separately.

### Use by the existing comparison

The registry comparison already joins a KIMDIS party to a registry profile by exact reported AFM
and reports `multiple_registry_numbers_for_reported_afm`. Hits returned here become registry
observations through the existing import, so the comparison needs no new matching rule. What is
new is a distinct comparison outcome for an AFM that was queried: `queried_not_found_at_observation`
instead of "no candidate in the selected imports", so a never-looked-up AFM and a looked-up one
without a result are not confused.

## Boundaries

- Always: validate before sending; archive before parsing; keep the queried AFM, registry number
  and reported AFM separate; report 404 as a statement about one observation; keep AFM lists and
  originals out of Git.
- Ask first: any schema migration (slice L5), any change to rate or run budgets beyond this spec,
  querying more than 25 AFMs per run, adding another search criterion, using hits as profile
  evidence if the L6 equivalence check fails.
- Never: pick a hit for the investigator, treat equal AFM as a verified legal identity, infer
  ownership or control, send a name search, enumerate or crawl the registry, print or log the key,
  paste responses (they contain named individuals) into issues or pull requests.

## Hand-calculated example (synthetic)

Queried AFMs A, B, C, D, E, one request each.

| AFM | Answer | Outcome |
|---|---|---|
| A | 200, one company, same AFM | `hit_single` |
| B | 200, two companies (head office and branch), both with AFM B | `hit_multiple` |
| C | 404 | `not_found_at_observation` |
| D | 200, one company reporting a different AFM | `afm_mismatch` |
| E | 200, `totalCount` 3, two returned | `truncated` |

Expected run summary: requested 5, requests 5; companies archived 1 + 2 + 0 + 1 + 2 = 6; outcomes
one each of the five kinds above; hits eligible for comparison: A (1), B (2) and E (2, marked incomplete); D's hit is archived but not eligible.
With two KIMDIS parties reporting A and B, the comparison reports agreement for A and
`hit_multiple` context for B; a party reporting C reports `queried_not_found_at_observation`.

## Commands

```bash
uv run --frozen python -m nima ingest gemi-afm --afm 012345678 --archive-dir data/gemi-afm
just check
just audit
```

The `ingest gemi-afm` command is proposed here and does not exist yet. Collection and the Docker
test runner need Linux; on Windows use the project container.

## Project structure

```
src/nima/sources/gemi_search.py     pure: response envelope, hits, outcomes
src/nima/ingestion/gemi_search.py   collector reusing the GEMI transport and limits
src/nima/storage/gemi_archive.py    read-only verification gains the search run kind
tests/test_gemi_search*.py          synthetic and hand-calculated cases
docs/sources/gemi.md                gains a "search by AFM" section when implemented
```

The parser must not import the collector, the database layer or the comparison. A search hit and
a profile response share one normalizer, not two copies.

## Testing strategy

- Recorded synthetic responses for every outcome in the table, each including the type quirks
  (string `arGemi`, string `resultsSize`, missing fields) and the example above.
- The existing GEMI crash, retry, 401, 429 and body-limit tests are reused by parameterizing the
  transport tests over both request kinds, not copied.
- Property checks: permuting the input AFM list does not change outcomes; duplicates are sent once;
  a response is stored byte-identically before any parse.
- Mutation-check each new rule; 100% line and branch for new code; no live call in the suite.
- One live pilot (L6): three AFMs that exist, one that returns 404, and an equivalence check that
  the normalized fields of a hit equal those of `GET /companies/{arGemi}` for the same company.

## Slices (one PR each; each stops for review)

| Slice | Content | Exit |
|---|---|---|
| L1 | This spec | Owner approves or edits; decisions D1-D6 recorded |
| L2 | Pure search response parser and outcome rules | All outcomes proven on synthetic bodies |
| L3 | Collector `ingest gemi-afm`, archive-first, shared transport | Crash, retry and budget tests pass; no migration |
| L4 | Read-only archive verification of search runs | A run verifies from original bytes alone |
| L5 | Import of hits and the `queried_not_found_at_observation` outcome | **Migration, owner approval first**; comparison tests unchanged for existing inputs |
| L6 | Live pilot on the owner's machine | Equivalence result recorded; latency measured; budgets confirmed or amended |

## Success criteria

Every outcome in the table is reachable and tested; a verified archive reproduces the per-AFM
table from original bytes; the existing comparison produces identical results for inputs that
contain no search evidence; no hit is ever selected automatically; the live pilot records the
equivalence and latency findings honestly, including a failure if there is one.

## L6 findings (2026-11-23)

Recorded in [the L6 record](../verification/gemi-afm-l6.md). They settle the following:

- **Assumption 3 holds for these three companies.** A search hit equals the profile fetched by registry number
  in every normalized field; the title lists (`titles_el`, `titles_en`) can differ in order only. Under D3 a hit
  can be used directly as profile evidence. Titles must then be compared as sets, not as sequences.
- **Branches repeat the head office AFM** (verified on three AFMs: one head office plus 1 to 4 branches), so
  `hit_multiple` is the normal answer for a company with branches, not an exception.
- **Deleted registrations are returned** in a search; their status is kept and a deleted entry is never a
  current company.
- **D4 run budget, measured:** search 4 to 10.5 s, profile 2.4 to 6.1 s. At 7.5 s spacing a 25-AFM run of
  large companies takes roughly 190 to 260 s, close to the 300 s ceiling. Recommendation: keep 25 AFMs and the
  300 s run budget; a stop on `time_budget` is clean and the remaining AFMs can be searched in a second run.
  Not changed; the owner can raise it.
- **Not a safe probe:** a wrong-check-digit AFM can exist in the registry. Personal AFMs must not be queried.

## Decisions (recorded 2026-11-20)

The owner answered "recommended for D1 to D6". Recorded as follows.

- **D1 Input:** AFMs given explicitly, one to 25 per run, from flags or a private file. No cohort
  export in this module.
- **D2 Hits:** request up to 20 hits and keep all of them; `truncated` is visible.
- **D3 Hits as profile evidence:** use a hit directly if the L6 equivalence check passes; otherwise
  follow each hit with `GET /companies/{arGemi}`.
- **D4 Run budget:** cap 25 AFMs; set the run limit in a spec amendment after L6 measures latency.
- **D5 Personal data:** archives and AFM lists stay private; normalized records keep the existing
  projection; anything published excludes natural-person legal forms and lists no individual's AFM.
- **D6 Storage:** one small migration in L5 for search observations, as a separate PR with its own
  approval.
