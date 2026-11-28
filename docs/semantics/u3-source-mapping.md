# U3 source meanings and analytical choices

Checked 2026-11-28 against main `0ae4e36` (merged #243). This maps the existing
draft `buyer_supplier_record_concentration.v1`; it does not change its definition,
SQL, acceptance profile or historical artifacts. The [retained-data verification](../verification/u3-source-semantics.md)
records what was actually exercised.

## Publisher documentation

Primary references, read through the connected documentation browser:

- [KIMDIS API help](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help):
  sections “Ανάκτηση Συμβάσεων”, response fields and “Ανάκτηση Συνδεδεμένων Πράξεων”.
- [European Commission CPV](https://single-market-economy.ec.europa.eu/single-market/public-procurement/digital-procurement/common-procurement-vocabulary_en):
  procurement classification.
- [AADE A.1003/2026](https://www.aade.gr/egkyklioi-kai-apofaseis/1003-12-01-2026):
  KAD 2025 business activities, aligned with NACE Rev. 2.1 and CPA Rev. 2.2.

KIMDIS documentation mapping:

| Source field / interface | Documented meaning | Current implementation / boundary |
|---|---|---|
| `referenceNumber` | Unique ADAM | Namespaced publication ID; not a procurement-process ID |
| `organization` | Public body | Exact reported `key`; no organizational roll-up |
| `contractingMembersDataList[].vatNumber`, `.country`, `.greekVatNumber` | Contractor tax number, country, Greek-tax flag | Tax/country retained in normalized parties; flag remains in original bytes |
| `cancelled` and cancellation details | Cancellation | U3 uses tri-state boolean, retains original details through evidence |
| `submissionDate`, `lastUpdateDate` | Submission, update | Source text retained; U3 selects by observation time |
| `prevReferenceNo` | Previous act | Normalized `previous_record` link; no lifecycle consolidation |
| `objectDetailsList[].cpvs` | Procurement category | Reported classification; not company activity |

The help says `isModified: false` includes modifications. Without cancellation-date
filters, retrieval includes cancellations. `adamChain` describes linked stages and
modifications/cancellations; its heading uses GET but its example uses POST.
The country table says string; its example uses a key/value object. These are
documentation discrepancies, not permission to guess a new accepted shape.

## Nima transformations and evidence checks

The owner reviews the intended business question; technical mapping and arithmetic
are checked here against code and archived originals first.

| Transformation | Code | Evidence / remaining gap |
|---|---|---|
| Normalize source party fields and record evidence | [`kimdis.py`](../../src/nima/sources/kimdis.py) | Every retained row re-normalized; raw field, hash, pointer, exact money, dates and reference comparisons pass |
| Validate source envelope and normalized record | [`kimdis.py`](../../src/nima/sources/kimdis.py), [`test_kimdis_contracts.py`](../../tests/test_kimdis_contracts.py) | Existing contracts run on every retained page; malformed/synthetic cases remain separate from real-source coverage |
| Select latest observation per source ID at cutoff | [`selection.py`](../../src/nima/semantics/selection.py) | Repeated capture reconciles; real latest-time ambiguity absent, covered synthetically |
| Group eligible reported country/tax identifiers | [`parties.py`](../../src/nima/semantics/parties.py) | Greek-only eligibility is a Nima scope rule; foreign identifiers are not source errors |
| Count supplier participation and exact shares | [`buyer_concentration.py`](../../src/nima/semantics/buyer_concentration.py), [`buyer_concentration.sql`](../../src/nima/semantics/buyer_concentration.sql) | Independent original-field calculation, fresh Python, native SQL and retained results agree |
| Associate output with originals | [`buyer_readout.py`](../../src/nima/analytics/buyer_readout.py) | Record-level provenance; not a field-level lineage system or publisher-truth certificate |

An evidence occurrence is identified by **run, page number and record pointer**;
`/content/0` alone is not unique across pages. Original-page hashes bind bytes.
Repeated observations may share a source ID without becoming extra publications.

The sample's supplier countries and CPVs use key/value objects. This supports
the current parser on those retained responses, not every future source shape.
The original `greekVatNumber` may be explicitly null or disagree with the current
country/tax-shape grouping. Neither value is a verified tax identity. Do not infer
a missing flag from null or silently replace country eligibility with the flag.

## Analytical choices that remain draft

The [existing definition](buyer-concentration.md) includes true, false and unknown
cancellation states, counts a joint publication once for each distinct eligible
supplier, and divides supplier counts by records with an eligible supplier. These
are Nima conventions; official documentation does not certify that arithmetic.
Supplier counts overlap and are not a partition of either money or a market.

Keep the following populations distinct in future analysis:

1. **Captured publication history:** existing U3, including reported cancellations.
2. **Reported non-cancelled publications:** require `cancelled is false`; keep
   true and unknown separately. This is a proposed sensitivity/readout definition,
   not implemented metric support and not proof of an active contract.
3. **Procurement or contract lifecycles:** a separate future definition after
   reconciling previous/next/award/payment links, amendments, cancellations and
   lots. Do not obtain it by merely dropping rows with a previous reference.

Current U3 selects the latest **observed** record, not a verified latest legally
effective source revision. A populated previous/next link is not enough to label
a record an amendment or collapse a chain; uncollected targets remain unresolved.
Multiple suppliers do not establish a particular consortium/legal relationship.

CPV, KAD/NACE and geography are different dimensions. Future taxonomy validation
should bind the classification family, release, code, original label, reference
dictionary and mapping version. A code-shaped value or a shared keyword does not
prove dictionary membership, a company sector or a cross-taxonomy equivalence.
This checkpoint installs no dictionary and verifies no KAD source feed.

## Next decision

Retain the draft publication-participation calculation and its historical hashes.
Review the business question using the measured limits, then resolve compatible
definition/acceptance profiles before promotion. Any changed population or
grouping needs an explicitly versioned definition and its own reconciliation;
do not change old U3 outputs to make the review pass. An active-contract, spending,
market-share or competition claim is outside the present evidence.
