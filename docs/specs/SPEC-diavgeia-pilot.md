# Spec: Diavgeia second-source pilot (V1-06)

Module ID: `diavgeia-pilot`. Status: **decisions P1 and P3 to P6 recorded as recommended by the owner on 2026-11-21 ("recommended
for P1 and P3 to P6"); P2 was settled on 2026-11-22 (organisation `6`,
issue dates 2026-10-08 to 2026-11-06). D2 and the D3 command are delivered; the first real run and the
overlap measurement are recorded in [the run record](../verification/diavgeia-pilot-run.md).** Depends on [ADR-0008](../decisions/0008-diavgeia-second-source-measure-first.md), the
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

- `source_id` = `diavgeia:<ADA>`, the ADA exactly as published (Greek letters and digits). A value with
  whitespace or an odd shape is quarantined, not trimmed. **No Unicode normalisation and no Latin/Greek
  look-alike folding**: a citation resolves only on exact bytes, and mismatches are counted, not repaired.
- A record's content hash covers its parsed metadata, so a changed `versionId` or `status` is a new
  version of the same `source_id`, observed at the page's capture time.
- `PUBLISHED`, `PENDING_REVOCATION` and `REVOKED` are kept as observed statuses. A decision absent from
  a later capture is never read as revoked or deleted.

### Normalised record (closed set, personal data excluded)

`ada`, `decision_type`, `organization_id`, `issue_timestamp_ms` and `submission_timestamp_ms` (the
documented millisecond timestamps; no effective-date claim), `version_id`, `status`,
`corrected_version_id` (when present), `private_data` flag, `related_ada` (`textRelatedADA`, a typed
reference never a merge), and for awards `award_amount` as exact decimal text with `award_currency`.
**Persons: a count (`person_count`) and the distinct tax-number types (`person_types`) only; no
tax number, country or name.** The documentation's main Greek type reads "natural or legal person in
Greece", and the first real run showed short codes (`EL`, `EUP`) whose meaning is unverified, so a
legal entity cannot be told from an individual by type; until a written policy says how,
nothing person-level is projected (dossier decision 3, applied strictly). The cost is accepted for
the pilot, whose goals are adapter conformance and citation overlap, not supplier joins. Unknown stays
unknown; only `ada`, `status` and `versionId` are required, because the other fields are optional in
the documentation and absence is data, not an error. An amount with an extreme exponent is quarantined
rather than expanded.

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

**Ask first:** the first real run (organisation, window, date); any second type, window or
organisation; any PDF fetch; any change to the source worker's gateway allowlist.

**Never:** a request before the adapter change is merged; natural-person tax numbers or names in a
normalised record; fuzzy or normalised ADA matching; counting a decision and a KIMDIS record as one
economic event; real decisions or documents in Git.

## Slices

| Slice | Content | Done when |
|---|---|---|
| D1 | This spec approved with decisions P1 to P6 | P1, P3 to P6 decided 2026-11-21; P2 open |
| D2 | Synthetic samples (statuses, versions, persons, private data, amounts, empty and malformed pages), the `diavgeia` adapter and its registry entry; **no network** | The shared parser and engine conformance suites pass on the new adapter; 100% line and branch; every rule break caught. **Done in review.** |
| D3 | The `nima ingest diavgeia` command (**built**), then one owner-approved real run (P1 cohort) with the archive preserved | Run reconstructs from the archive; counts and status mix recorded in `docs/verification/`, no decision content |
| D4 | Measure how many of the four KIMDIS citations resolve to a collected decision, and how many collected ADAs any KIMDIS record cites | Counts recorded; V1-07 join spec can start. **Done 2026-11-22: 0 of 4 cited ADAs resolve; see the run record.** |

Each slice is one review-ready PR with the repository gates. D3 is the owner's live step.

## Decisions for the owner

P1 and P3 to P6 are decided as recommended (2026-11-21). P2 was decided on 2026-11-22: organisation `6`
(Ministry of National Defence), issue dates 2026-10-08 to 2026-11-06.

| # | Decision | Recommendation |
|---|---|---|
| P1 | Pilot shape: Δ.2.2 by one organisation and one window (fallback of dossier decision 4) | Yes. Fetching only the four cited ADAs is too few to test an adapter |
| P2 | Which organisation and window | You choose. A body with regular awards and a KIMDIS presence helps the overlap count; the Diavgeia `uid` and the KIMDIS buyer key coincide for the Ministry of National Defence (`6`); whether that holds for other bodies is unverified, so check a second body before relying on it |
| P3 | `status=all` rather than the default published-only | Yes, otherwise revocations stay invisible |
| P4 | Natural persons: count and flag only; `private_data` decisions carry no person fields | Yes, as dossier decision 3 |
| P5 | ADA matching on exact bytes only | Yes; measure mismatches before any rule |
| P6 | Issue-date windows of at most 30 days, page size 100 | Yes; small enough to rerun and compare |

## Found while building D2

- **No allowlist file exists to edit.** The standalone collectors (KIMDIS, GEMI) are bound to the host
  their adapter declares: `checked_request` refuses any request whose URL differs from the adapter's
  `provenance.endpoint`. The gateway allowlist belongs to the separate remote-worker pilot. So the
  adapter's endpoint is the allowlist for this pilot, and dossier decision 5 is met by that and by the
  rule that no request is made before D3 is approved.
- **The first run needs a command.** Registering the adapter did not give `nima` a way to run it; the
  D3 command below closes that.
- **Contract descriptors** (the machine-readable contracts KIMDIS has) are not written: shapes stay
  unverified until the first real response is recorded.

## Running D3 (owner)

The command is built and tested against a mock server; it has never contacted Diavgeia. After P2 is
decided and you approve the request, run it on Linux with the archive on a mounted folder, then copy the
folder out of the container:

```sh
uv run --frozen python -m nima ingest diavgeia --database   --organization <uid> --from-date 2026-01-01 --to-date 2026-01-30 --archive-dir /out/raw
```

It uses the engine's default limits (100 pages, 20 requests a minute, stop on any error) and stores
the run in the database named by `NIMA_DATABASE_URL`. Without `--database` it archives only. Record the
printed counts (pages, records, normalized, quarantined) and the status mix in
`docs/verification/`, with no decision content. The Diavgeia `uid` equals the KIMDIS buyer key for the Ministry of National Defence;
whether that holds generally is unverified.

## Deferred, with triggers

| Item | Trigger |
|---|---|
| Per-decision `versionlog` | A revoked or corrected decision needs its reason or history |
| PDF and attachment fetch (SHA-1 check) | An analyst needs a value the metadata lacks, and the owner approves bulk fetches |
| Other decision types (Β.1.3, Δ.1, Δ.2.1) | The Δ.2.2 pilot is accepted |
| Diavgeia organisation list and hierarchy | The hierarchy slices (SH1 to SH4) |
| Cross-check with Diavgis chains | The owner approves attribution wording and a network host |
