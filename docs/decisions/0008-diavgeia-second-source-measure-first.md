# ADR-0008: Diavgeia is the second source, bounded and measured first

## Status

Accepted by the owner, 2026-11-20, for a bounded pilot. No adapter exists yet.

## Context

KIMDIS records cite Diavgeia decisions (`diavgeiaADA`), and Diavgeia carries the decision text,
versions and revocation state the KIMDIS records lack. Diavgeia is open (CC BY 4.0 with
mandatory attribution, Law 3448/2006), has a documented API (anonymous page cap 500) and states
no rate limit. Its decisions can contain personal data. A third-party linked dataset (Diavgis)
reports linking by estimate and no explicit-proof chains; its figures are unverified and may
not be relied on without our own measurement.

## Decision

1. Accept Diavgeia for a bounded pilot only.
2. Attribute as "Source: Diavgeia (diavgeia.gov.gr), CC BY 4.0; data retrieved on <date>".
3. Keep original documents only in the private archive; use synthetic fixtures; project tax
   numbers only for legal entities until a written policy exists.
4. Measure first. Run the read-only census (`scripts/diavgeia_link_census.py`) on our own
   KIMDIS data, then fetch exactly the ADAs one small cohort cites via `GET /decisions/:ada`
   and its version log. Fall back to the by-organisation, windowed search only if needed.
   Diavgis is at most a later cross-check.
5. Use the engine's default request rate. Add `diavgeia.gov.gr` to the source worker egress
   allowlist only for the pilot and only in the adapter change.

## Consequences

No Diavgeia request is made and no adapter spec is written before the census result is seen.
A decision cited by many records is treated as an umbrella reference, not a one-to-one chain
link. The adapter spec must settle ADA identity, `versionId`, status handling and
`correctedVersionId` before code. Evidence: `docs/sources/diavgeia-acceptance.md` (page hashes,
findings, unverified list).
