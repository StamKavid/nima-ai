# U3 official-source and retained-data checkpoint

Executed 2026-11-28 on the unchanged application from main `0ae4e36` (merged
#243). The [source mapping](../semantics/u3-source-mapping.md) separates publisher
meanings from Nima's draft conventions. Verdict: **the retained publication metric
is reproducible; business certification and lifecycle interpretation remain open.**

## Method and boundaries

Reused the sealed [owner packet](u3-owner-review-packet.md), ID
`706f69e83aaae7a92dac4436946be128ac8cbe55bf87a3bc4890a9fc2f88e098`.
Verified manifest-bound parent/card hashes and every original-page digest/length.
Re-normalized each page with existing source and producer contracts; compared
publication ID, buyer, supplier order/tax/country/name, cancellation, source dates,
exact decimal amounts, reference links and record-level evidence against originals.
Compared original content hashes and normalized fields with every saved citation.

Reconstructed observations from those verified originals. Fresh Python and native
PostgreSQL 17 reference SQL reproduce the entire saved metric payload. SQL ran in
read-only repeatable-read transactions. Separately counted original fields using
ordinary Python, without Nima's normalizer, selection or metric helpers for the
arithmetic, and reconciled record, supplier, joint, unresolved and top-share counts.
This automated cross-check is not an independent human hand reconciliation.

The three scenarios contain 125 observation occurrences, not 125 distinct records
or three independent datasets. The repeated scenario reuses the primary source
IDs across two captures. No government-data request, new capture, source retry,
schedule, metric/status/profile change, database write or human sign-off occurred.
Public documentation reads are separate from government-data acquisition.

## Measured results

| Scenario | Observations | Selected publications | Resolved / unresolved | Supplier groups | Joint records | Overlapping participations | Top fraction |
|---|---:|---:|---|---:|---:|---:|---|
| Primary | 16 | 16 | 16 / 0 | 16 | 6 | 24 | 4/16 |
| Eligibility comparison | 77 | 77 | 75 / 2 | 57 | 5 | 80 | 9/75 |
| Repeated capture | 32 | 16 | 16 / 0 | 16 | 6 | 24 | 4/16 |

Every selected publication in these scenarios reports `cancelled: false`.
An original-field sensitivity calculation restricted to that state therefore
returns the same counts. This establishes **no real-data positive cancellation or
unknown-status case** and does not implement a second metric.

The eligibility comparison contains two foreign supplier occurrences that remain
outside the Greek grouping policy. Those two publications are unresolved under
that policy; the foreign values are not labelled malformed or corrected to Greek.

## Field coverage and consequences

| Observed in selected records | Primary / repeated latest selection | Eligibility comparison | Consequence |
|---|---|---|---|
| Supplier `country` objects | 24 supplier occurrences | 82 supplier occurrences | Matches the documented example and existing parser, not the table's string type |
| `greekVatNumber` | 20 true, 4 false | 82 explicit nulls | Null is not missing or false; flag is not the current grouping authority |
| False flag with eligible country/tax shape | 4 occurrences | 0 | Retain disagreement, do not silently reclassify a supplier |
| Populated `prevReferenceNo` | 16 records | 9 records | Previous-act links are present; not all are proven amendments |
| Populated `nextRefNo` | 14 records | 2 records | Local publication counting does not consolidate linked lifecycles |
| `nextModified: true` | 14 records | 1 record | Raw successor flag, not a verified current-record legal classification |
| `nextExtended: true` | 0 records | 1 record | Preserve the assertion; linked-target semantics remain unverified |
| `numberOfSections > 1` | 3 records | 17 records | Publication count is not lot count |
| CPV key/value objects | 74 occurrences | 148 occurrences | Shape verified; full reference-dictionary membership not checked here |

Counts in the primary/repeated column are **not added together**. All repeat
observations were validated, but that column describes the latest selected set.
No source identifiers, companies, supplier keys, raw pages or reviewer responses
are included in this public summary.

## Existing behavioral proof

The unchanged [`test_buyer_concentration.py`](../../tests/test_buyer_concentration.py)
already tests hand-computed joint overlap/ties, unknown/empty/foreign suppliers,
true/false/unknown cancellation, repeated observations, cutoff changes and ambiguous
latest revisions against both Python and real PostgreSQL. The unchanged
[`test_kimdis_contracts.py`](../../tests/test_kimdis_contracts.py) exercises field
types, unknowns, money, references and original evidence. These are synthetic
behavior tests; they do not fill the real-source coverage gaps above.

Full local gates, dependency audit and hosted delivery evidence are recorded in
[checkpoint PR #244](https://github.com/StamKavid/nima-ai/pull/244) as they finish;
pending checks are not passes. No release gate changes because these checks
pass. The private verifier and receipts remain outside Git; the verifier records
the parent/page hashes, native SQL parity, field census and original-field counts.

Private receipt SHA-256:
`f88f7b4be6c989910d9e5459fe3342c4a56e1e0c964cb89ab58002d27a118c52`.
Verifier SHA-256:
`9bf94c7e0b61e77a0c9a3a211ab527c6b220962392fe2e94f00b0cbc3141718f`.
The receipt contains private supplier keys and stays outside Git; these fingerprints
identify the retained proof without publishing its contents.

## Remaining work

- Owner review of the intended publication-participation question and its limits;
  human arithmetic remains unsigned. The API field mapping is engineering work,
  not something the owner must reconstruct from memory.
- Compatible historical definition/acceptance profiles before any promotion.
- Real cancellation/unknown-status and linked-target reconciliation before new
  population/lifecycle claims; use newly authorized bounded evidence or a supplied
  retained sample, not an implicit retry or national scrape.
- Versioned taxonomy dictionaries and explicit CPV versus company-activity
  attribution when those definitions are implemented.
- The first buyer-to-original product flow, consenting-user task observation,
  positive two-source reconciliation and operational acceptance remain open.
