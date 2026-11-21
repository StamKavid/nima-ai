# Captured records by CPV code and month (U2)

`captured_record_count_by_cpv_period.v1` counts distinct captured KIMDIS contract-publication
records per **reported CPV base code** and **calendar month of the reported submission date**. It is
descriptive evidence about a bounded capture. The definition is `draft`: not a spending figure, a
market share, an award or a certified metric. It is the second metric of the
[V1-05 semantic model](../specs/SPEC-semantic-model.md) and reuses the shared
[record selection](../../src/nima/semantics/selection.py) and the measured
[time model](date-format-measurements.md).

## Inputs

An explicit cohort of observations, an inclusive UTC cutoff, and optionally one CPV base code and
a first and last month (`YYYY-MM`). Each observation carries the record's version (source ID and
source-content hash), its cancellation flag, the submission-date text and its CPV assertions as
extracted from the original archived bytes (status `reported`, `missing`, `null`, `empty` or
`invalid`; the extraction contract is [market metadata](market-metadata.md)). A version with no
extracted metadata is a different case from a version whose assertions contain no reported code.

## Rules

1. **Revision.** Observations after the cutoff are dropped, then the latest observed time per source
   ID is chosen. Identical versions collapse; different versions tied at that time are `ambiguous`,
   listed, and never placed. "Latest" means latest observed in this cohort, not source-current.
2. **Code.** A record is placed under each distinct reported code's first eight digits. Duplicate
   codes and codes that differ only in the check digit collapse. Only `reported` assertions place a
   record; syntax is checked, membership in a CPV release is **not** (`taxonomy_validation:
   not_checked`). Labels, parents and release selection belong to the hierarchy slice SH1.
3. **Unclassified.** A record with no reported code is placed in the `unclassified` cell, with the
   reason kept in its decision: `no_reported_code`, or `metadata_unavailable` when the version has no
   extracted metadata.
4. **Month.** The calendar month of `source_submitted_at` as parsed by the time model. A zone-less
   value is read as Europe/Athens civil time. A missing or unparseable date places the record in
   the unknown period; nothing is taken from the observation time.
5. **Cancellation.** `true`, `false` and unknown are all included, with `cancelled_count` and
   `unknown_cancellation_count` per cell. This is a publication count, not an active-contract count.
6. **Filters.** A CPV filter keeps only records with that code; an unclassified record cannot match.
   A month range keeps only records with a parsed month in range; an unknown period cannot match.

## Output and disclosures

`cells` (code, month, count, source IDs, cancellation counts), `period_totals` (distinct records per
month), `coverage` (selected records, classified, the two unclassified reasons, date parsed, absent
and unparseable), `ambiguous_source_ids` and one decision per selected record with its evidence
versions. Cells are ordered by code then month with unknowns last.

A record with several codes appears in several cells, so the cells of one month can add up to more
than that month's distinct records; `period_totals` counts each record once. Status is
`empty_capture`, `no_observations_before_cutoff`, `observed_activity`, `selection_unresolved`
(no cell, but ambiguous, unclassified or unknown-period records could have matched the request) or
`no_observed_activity`. No share, ratio or monetary total is produced.

## Reproducibility

The pure provider is `nima.semantics.cpv_period`; its packaged `cpv_period.sql` is the reference
SQL. Every test scenario runs both on PostgreSQL and requires the same complete result. The SQL
receives the already parsed month, so its parity covers selection, placement and aggregation; date
parsing is tested in the time model. The definition hash binds the rules, the time model version and
the SQL hash. Inputs, cutoff and bounds (5,000 observations, 1,000 assertions each) are validated
with fixed error reasons; no source value appears in an error.

## Not part of this slice

No readout command, no assembly of inputs from stored metadata snapshots, no CPV release or label,
no parent roll-up (SH1) and no real-data reconciliation. The only real CPV evidence so far is the
archive of one capture; certification needs the owner's reconciliation (slice S7).
