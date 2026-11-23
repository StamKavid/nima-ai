# Spec: importing GEMI AFM search runs into SQL (slice L5)

Status: **approved 2026-11-23; L5-1 to L5-5 decided as recommended. L5a built and in review: its migration SQL (`0014.sql`) is reviewed in its own PR before it merges or runs on any database.**
Part of [SPEC-gemi-afm-lookup](SPEC-gemi-afm-lookup.md); depends on its L1 to L4 and L6, all delivered.

## Objective

A verified AFM search run (`nima gemi verify-afm`) lives only as files. The registry comparison reads SQL, so a
search hit cannot yet be compared with a KIMDIS party, and a searched AFM that returned 404 cannot yet be told
apart from an AFM nobody looked up. L5 imports a verified search run into PostgreSQL, atomically and
re-verifiably, and teaches the comparison to read it. It adds evidence only: no identity is accepted, no hit is
chosen, no absence is read as proof that a company does not exist.

## What the existing tables cannot hold

Read from `0004.sql`, `storage/gemi.py` and `identity/registry_cohort.py`:

| Existing rule | Why a search run does not fit |
|---|---|
| `gemi_responses` is keyed by the registry number that was requested, and the number cannot start with zero | A search is requested by AFM, which keeps its leading zero, and one answer holds up to 20 registry numbers |
| `gemi_observations` has one row per registry number, tied to exactly one response row | One search response is the evidence of many observations |
| `gemi_imports` caps a run at 10 observations, 30 responses, and fixes `import_version = 'gemi-import-v1'` | A search run has up to 25 AFMs and 500 hits, and its own connector version |
| The comparison reads imports, observations and profile versions and requires counts to agree | It cannot see a run that is not in those tables |
| Identity review (`identity_review_events`, `identity_entities`) points at `gemi_observations` and requires `found` and 200 | A hit that is not an observation row cannot yet be reviewed |

What does fit: `gemi_profile_versions` (key: source id, normalizer version, response hash). The L6 pilot showed
a hit equals its profile field by field, so a hit can be stored there with the search response's hash as its
raw hash. `nima.raw_objects` already holds bodies by hash.

## Options

| | A: separate search tables (recommended) | B: reuse the profile tables |
|---|---|---|
| Storage | New immutable tables for the run, each request, each AFM outcome and each hit; hits reference `gemi_profile_versions` | Widen the existing constraints; write one `gemi_responses` row per hit, all pointing at the same body |
| Honest evidence | One response row per HTTP response; `response_count` stays true | The same response is counted once per hit, so counts overstate the requests made |
| Existing readers | The comparison reads both kinds of import; review does not see hits yet | Comparison and review work unchanged |
| Cost | Four new tables and a comparison query change | Alters four delivered constraints; any later fix must keep the lie consistent |

**Recommendation: A.** Counting one HTTP response as several is the kind of silent distortion this project
rejects. Review of a search-found match is deferred (decision L5-2).

## Behaviour (option A)

- **Import:** `nima gemi import-afm RUN_ID --archive-dir DIR`. It calls `verify_search_run` first, on every
  invocation, and writes only what the verifier recomputed. One transaction under an advisory lock; importing
  the same run again verifies that the stored rows are identical and changes nothing.
- **Tables (migration 0014, all immutable, no grants, no TRUNCATE):**
  - `gemi_search_imports`: run id, import version `gemi-search-import-v1`, manifest and its hash, connector
    and normalizer versions, license, counts.
  - `gemi_search_requests`: one row per attempt, keyed by AFM (kept as text with its leading zero), with status,
    failure, response hash, byte length and observation time.
  - `gemi_search_outcomes`: one row per AFM: the fixed outcome, the final request, and `truncated`.
  - `gemi_search_hits`: one row per returned company: AFM, position, registry number, `afm_matches`, and the
    profile version it points at.
- **Profile versions:** each hit's normalized payload is inserted into `gemi_profile_versions` (key: `gemi:<n>`,
  `gemi-company-v1`, the search response hash), the same way profiles are. Its payload keeps the pointer
  `/searchResults/<i>/...`, so the evidence location stays exact.
- **Not imported:** quarantined answers (counted, no rows), failed or incomplete runs, derived files.
- **Comparison (`registry-comparison-v1` successor):** `identities compare` accepts search imports beside profile
  imports, by the same explicit UUID list. A hit is a registry observation when `afm_matches` is true. A hit
  that reports a different AFM stays evidence and is never an agreement. A new outcome,
  `queried_not_found_at_observation`, replaces "no candidate" when the party's AFM was searched and answered
  404; a truncated search is reported as incomplete. The existing bounds stay (at most 100 selected
  observations, 10 imports) and fail visibly.

## Boundaries

**Always:** verify before writing; one transaction; compare stored rows with a re-verified run on reuse; fixed
failure reasons; counts only in output; keep AFM lists and responses out of Git; a 404 is a statement about one
observation.

**Ask first:** the migration itself (this document is the request), any change to the identity review tables,
any use of a hit to create or accept an identity.

**Never:** choose a hit; treat a matching AFM as a verified legal identity; filter out a deleted registration;
write a hit as an observation of a request that was not made for it; alter an existing GEMI table.

## Decisions for the owner

L5-1 to L5-5 are decided as recommended (owner, 2026-11-23).

| # | Decision | Recommendation |
|---|---|---|
| L5-1 | Storage shape | A: separate search tables, as above |
| L5-2 | Review of a search-found match | Defer. Comparison first; reviewing a hit needs the review tables to point at a hit and is its own migration. Trigger: you want to accept or reject a match that came from a search |
| L5-3 | Deleted registrations (3 of the 12 hits in the pilot) | Import and report them with their status, never filter them. Add no new rule until you decide what a deleted entry means for a comparison |
| L5-4 | Limits | At most 25 AFMs and 500 hits per import; the comparison keeps its 100-observation bound, so a larger selection fails visibly rather than truncating |
| L5-5 | Migration 0014 | Approve the table list above in principle; the SQL is reviewed in its own PR before it merges, and applied to your database only when you choose |

## Slices

| Slice | Content | Exit |
|---|---|---|
| L5a | Migration 0014, `import-afm` and re-import, tests first on PostgreSQL | Idempotent import; tampered or incomplete runs refused; immutability and grants tested; 100% line and branch; every guard mutated |
| L5b | Comparison reads search imports; `queried_not_found_at_observation`; incomplete-search flag | Existing comparison tests unchanged for inputs without search evidence; hand-calculated example passes |
| L5c | Offline run of both on the L6 archives against a synthetic KIMDIS cohort; record in `docs/verification/` | Counts recorded; no real AFM, name or number in Git |

Each slice is one review-ready PR. L5a stops for your review of the migration before anything runs on a real
database.

## Deferred, with triggers

| Item | Trigger |
|---|---|
| Review and identity acceptance from a search hit | L5-2 trigger above |
| Private AFM file input for `ingest gemi-afm` (decision D1) | The owner wants lists longer than a command line comfortably holds |
| Title lists compared as sets in the profile contract | A consumer needs them; the L6 pilot found the order unstable |
| Importing profile and search runs of the same company together | Both kinds are imported and the owner wants one deduplicated view |
