# Buyer supplier concentration (U3)

`buyer_supplier_record_concentration.v1` describes how a single reported buyer's **captured
contract-publication records** spread over **eligible reported suppliers**. It is descriptive evidence
about a bounded capture. The definition is `draft`: it is **not** market share, not a monetary or spend
concentration, not a competition or misconduct signal and not a certified metric. It is the third
metric of the [V1-05 semantic model](../specs/SPEC-semantic-model.md) and reads the same observation rows
as the [first metric](participation.md), reusing the shared record selection and party helpers.

## Inputs

An explicit cohort of observations (the first metric's validated rows), an inclusive UTC cutoff and one
reported buyer key. The key is the source's own organization key, compared after trimming ASCII
whitespace only and exactly otherwise (no case folding, no name matching).

## Rules

1. **Revision.** Observations after the cutoff are dropped, then the latest observed time per source ID is
   chosen. Identical versions collapse; different versions tied at that time are `ambiguous`, listed for
   the whole cohort and never attributed to any buyer. "Latest" means latest observed in this cohort.
2. **Buyer records.** The selected, unambiguous records whose latest version reports the requested buyer.
   A later version can move a record to another buyer; an unknown buyer is never attributed.
3. **Eligible supplier.** A reported Greek (`GR` or `EL`) nine-ASCII-digit, not all-zero tax number, with
   ASCII whitespace trimmed. The key is `GR:<tax number>`; `GR` and `EL` group together. No checksum is
   run and no company is asserted. Anything else (foreign, lower-case country, malformed or placeholder
   numbers, missing text) is an *ineligible occurrence*, counted and disclosed.
4. **Resolution.** A buyer record is `resolved` when it has at least one eligible supplier. Otherwise it is
   *unresolved* with a reason: `unknown_suppliers` (the list is unknown), `empty_suppliers`, or
   `no_eligible_supplier`. A resolved record that also has ineligible occurrences is listed as
   *partial*, so a share built on it can be read with that caveat.
5. **Counts.** Each resolved record counts **once for every distinct eligible supplier**, so a record with
   two suppliers counts for both and supplier counts overlap. `participation_total` is their sum and
   `joint_records` the number of resolved records with two or more eligible suppliers; neither is a record
   count. No contract value is allocated and no fractional share is used.
6. **Shares.** `top_share` is the top supplier's record count over **resolved** records, and
   `unresolved_share` the unresolved records over **all** the buyer's selected records, both as exact
   numerator and denominator (no floating point). When several suppliers tie for the top, every one is
   listed in `top_supplier_keys`; none is chosen.
7. **Cancellation.** `true`, `false` and unknown are all included, with a breakdown per supplier.

## Output and status

`buyer_key`, the three record counts, both shares, the top suppliers and count, `distinct_suppliers`,
`participation_total`, `joint_records`, `partial_source_ids`, `suppliers` (ordered by record count, then
key), `ambiguous_source_ids` and one decision per buyer record with its evidence versions. Status is
`empty_capture`, `no_observations_before_cutoff`, `observed_concentration`, `buyer_records_unresolved`
(the buyer has records but none resolved), `selection_unresolved` (no buyer records, but ambiguous
records could belong to it) or `no_observed_buyer_records`.

## Reproducibility

The pure provider is `nima.semantics.buyer_concentration`; its packaged `buyer_concentration.sql` is the
reference SQL. Every test scenario runs both on PostgreSQL and requires the same complete result. The
definition hash binds the rules and the SQL hash. Observations are bounded at 5,000 (the first metric
keeps its own bound of 500) and validated with fixed error reasons; no source value appears in an error.

## Not part of this slice

No readout command, no hierarchy roll-up (a ministry over its units is slice SH3, after the Diavgeia
feed), no company or group concentration and no real-data reconciliation. A concentration over
captured records says nothing about the buyer's total procurement or its competition.
