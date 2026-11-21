# Spec: Diavgeia second-source pilot (V1-06)

Module ID: `diavgeia-pilot`. Status: **draft for owner review; no code, no request, no allowlist change
until approved.** Depends on [ADR-0008](../decisions/0008-diavgeia-second-source-measure-first.md), the
[acceptance dossier](../sources/diavgeia-acceptance.md) (owner decisions 1 to 5), the
[source boundary](SPEC-source-boundaries.md) and its [collection extension](SPEC-source-neutral-collection.md).
Release gate served: R1 (two validated source adapters) and the join work of V1-07.

## Objective

Collect a small, explicit set of Diavgeia decisions through the existing acquisition engine, archive
every response before parsing, and keep their `ADA` identity, version and status as observed. The pilot
answers two questions with evidence: can the adapter run the full conformance suite on a real second
feed, and how many of our KIMDIS `diavgeiaADA` citations resolve to a collected decision. It creates no
identity link, no join and no metric.

Success looks like: one bounded real run that reconstructs from its archive, with counts reported
(decisions, statuses, personal-data flags, matched citations) and no decision content in Git.

## Measured starting point

The census (`scripts/diavgeia_link_census.py`, 2026-11-20) over 1,317 stored KIMDIS records found
**4 records citing a Diavgeia ADA, none shared** ([lifecycle page](../semantics/lifecycle-references.md)).
Decision 4 of the dossier said to revisit the plan if the key was sparse. It is sparse, so fetching only
the cited ADAs would yield about four decisions: not a pilot. The fallback it names, **Δ.2.2 award
decisions by organisation and window**, becomes the pilot shape (decision P1). The four cited ADAs are
used only as a small check, not as the cohort.

## Assumptions (correct me before I proceed)

1. One operator; public, anonymous, read-only access (page size cap 500); no account, no key.
2. The documented search parameters work as the dossier reads them. **Unverified** until the first
   recorded sample: the production path prefix, the exact value that selects type Δ.2.2, and whether
   `status=all` returns revoked decisions as documented.
3. No rate limit is stated; the engine's default request rate applies and the run stops on any error
   status.
4. Collection runs on Linux like the other adapters. Originals stay in the private archive.

## Behaviour

### Query and request

One run is one explicit query: organisation (one Diavgeia organisation `uid`), decision type Δ.2.2, an
**issue-date window of at most 30 days**, `status=all`, page size 100, `GET` on `search`. The adapter
refuses any query without all four, and checks the window the server reports as applied (the server
rewrites windows over 180 days). Issue date is used rather than last modification because the default
order is most recently modified first, which shifts pages when a decision is modified mid-run; the
engine's existing `pagination_changed` stop is kept and its frequency is a pilot measurement.

### Identity, version and status

- `source_id` = `diavgeia:<ADA>`, the ADA exactly as published (Greek letters and digits), trimmed of
  ASCII space only. **No Unicode normalisation and no Latin/Greek look-alike folding**: a citation
  resolves only on exact bytes, and mismatches are counted, not repaired.
- A record's content hash covers its parsed metadata, so a changed `versionId` or `status` is a new
  version of the same `source_id`, observed at the page's capture time.
- `PUBLISHED`, `PENDING_REVOCATION` and `REVOKED` are kept as observed statuses. A decision absent from
  a later capture is never read as revoked or deleted.

### Normalised record (closed set, personal data excluded)

`ada`, `decision_type`, `organization_id`, `issue_date_text` (source text kept; no effective-date claim),
`submission_timestamp_ms`, `version_id`, `status`, `corrected_version_id` (when present),
`private_data` flag, `related_ada` (`textRelatedADA`, as a typed reference never a merge), and for awards
`award_amount` and `currency` as exact decimal text. Persons: for a legal entity in Greece, `afm`,
`afm_country` and `name`; for a natural person, **only the count and a flag**, no `afm`, no name
(dossier decision 3). A decision with `private_data` true is kept in the archive and its normalised
record carries no person fields at all. Unknown stays unknown; the three award fields are optional in
the documentation, so absence is data, not an error.

### Provenance and attribution

Manifest provenance records the endpoint, the documentation URL and licence "CC BY 4.0 (Law 3448/2006)".
Every export or display carries: "Source: Diavgeia (diavgeia.gov.gr), CC BY 4.0; data retrieved on
`<date>`".

### Not collected

PDF documents and attachments, the per-decision `versionlog`, other decision types, other
organisations and the organisation list. Each is deferred with a trigger below.

## Boundaries

**Always:** archive the response before parsing; one organisation and one window per run; fixed error
reasons with no source text; synthetic fixtures only; stop on any non-success status.

**Ask first:** the first real run (organisation, window, date); adding `diavgeia.gov.gr` to the source
worker allowlist (it goes in the adapter change and nowhere else); any second type, window or
organisation; any PDF fetch.

**Never:** a request before the adapter change is merged; natural-person tax numbers or names in a
normalised record; fuzzy or normalised ADA matching; counting a decision and a KIMDIS record as one
economic event; real decisions or documents in Git.

## Slices

| Slice | Content | Done when |
|---|---|---|
| D1 | This spec approved with decisions P1 to P6 | Owner decisions recorded |
| D2 | Synthetic recorded samples (one page of mixed statuses, a revoked version, a natural person, a private-data decision, an empty page, a malformed record), the `diavgeia` adapter, registry entry and egress allowlist entry; **no network** | Full conformance suite passes on the new adapter; allowlist change reviewed and merged |
| D3 | One owner-approved real run (P1 cohort) with the archive preserved | Run reconstructs from the archive; counts and status mix recorded in `docs/verification/`, no decision content |
| D4 | Measure how many of the four KIMDIS citations resolve to a collected decision, and how many collected ADAs any KIMDIS record cites | Counts recorded; V1-07 join spec can start |

Each slice is one review-ready PR with the repository gates. D3 is the owner's live step.

## Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| P1 | Pilot shape: Δ.2.2 by one organisation and one window (fallback of dossier decision 4) | Yes. Fetching only the four cited ADAs is too few to test an adapter |
| P2 | Which organisation and window | You choose. A body with regular awards and a KIMDIS presence helps the overlap count; the Diavgeia organisation `uid` is not the KIMDIS buyer key, so it must be read from Diavgeia's organisation list once (a live request that needs your approval) |
| P3 | `status=all` rather than the default published-only | Yes, otherwise revocations stay invisible |
| P4 | Natural persons: count and flag only; `private_data` decisions carry no person fields | Yes, as dossier decision 3 |
| P5 | ADA matching on exact bytes only | Yes; measure mismatches before any rule |
| P6 | Issue-date windows of at most 30 days, page size 100 | Yes; small enough to rerun and compare |

## Deferred, with triggers

| Item | Trigger |
|---|---|
| Per-decision `versionlog` | A revoked or corrected decision needs its reason or history |
| PDF and attachment fetch (SHA-1 check) | An analyst needs a value the metadata lacks, and the owner approves bulk fetches |
| Other decision types (Β.1.3, Δ.1, Δ.2.1) | The Δ.2.2 pilot is accepted |
| Diavgeia organisation list and hierarchy | The hierarchy slices (SH1 to SH4) |
| Cross-check with Diavgis chains | The owner approves attribution wording and a network host |
