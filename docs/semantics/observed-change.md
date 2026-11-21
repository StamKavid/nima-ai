# Observed change between two captures (U4)

`observed_change_between_captures.v1` compares two **captures** of the same declared query and says,
record by record, what was added, what changed, what is missing from the later capture and what is
unchanged. It is descriptive evidence about two observations. The definition is `draft`. It never says a
record was deleted, withdrawn, amended or legally changed; it says what a later capture did or did not
contain. It is the fourth metric of the [V1-05 semantic model](../specs/SPEC-semantic-model.md) and reuses
the shared [record selection](../../src/nima/semantics/selection.py).

## What a capture is

A capture is one or more collection runs of one declared query, with the versions they observed. Each run
carries facts the comparison needs: its query hash, whether collection and normalization completed,
how many records were quarantined, and the time span of its observations. Whether a run really is complete
is decided where the run is read (its stored counters against the totals the source announced); this
metric only refuses to compare when those facts say it is not.

## When it must abstain: `incomparable`

A comparison is meaningful only if both captures covered the same question completely and one is
strictly later. Otherwise the result is `incomparable`, carries **no change categories**, and lists every
reason that applies, sorted:

| Reason | Applies when |
|---|---|
| `no_runs` | either capture has no run |
| `run_incomplete` | any run did not complete collection and normalization |
| `quarantined_records` | any run quarantined a record: that record may be missing from a capture only because it was set aside |
| `query_mismatch` | the runs of the two captures do not all share one query hash |
| `not_later` | the earlier capture's last observation is not strictly before the later capture's first |

An empty but complete capture is legitimate (a query can return nothing) and is compared.

## Rules when comparable

1. **Selection.** Within each capture the latest observed version of each source ID is chosen, as for every
   metric. If different versions tie at that time the record is `ambiguous` in that capture, is listed for
   that capture, and is excluded from every category of the comparison; it is neither added, missing nor
   unchanged.
2. **Categories** for every source ID that is unambiguous in the captures it appears in:
   - `added`: in the later capture only;
   - `missing_from_later_capture`: in the earlier capture only;
   - `changed`: in both, with different source-content hashes;
   - `unchanged`: in both, with the same hash.
3. **Meaning.** `changed` means the published record content differs, not which field or why.
   `added` means the earlier capture did not contain it, not that it is new. `missing_from_later_capture`
   is never deletion. No legal or effective event is inferred.
4. **Evidence.** Each listed record names its versions and observation IDs on each side.

## Output and status

`status` (`incomparable`, `observed_changes` or `no_observed_change`), `reasons`, a summary per capture
(runs, query hashes, selected records, ambiguous source IDs), exact `counts`, and the four category lists
ordered by source ID. The counts reconcile: the earlier capture's selected records equal
`missing + changed + unchanged` plus those excluded as ambiguous in the later capture, and the later
capture's selected records equal `added + changed + unchanged` plus those excluded the other way.

## Reproducibility

The pure provider is `nima.semantics.observed_change`; its packaged `observed_change.sql` is the
reference SQL. Every test scenario runs both on PostgreSQL and requires the same complete result. The
definition hash binds the rules and the SQL hash. Inputs are validated with fixed error reasons and
bounded (5,000 versions and 100 runs per capture); no source value appears in an error.

## Not part of this slice

No command that reads stored runs, decides completeness from stored counters or builds the two
captures, no field-level change detail, and no real-data reconciliation. The first real revisions
observed (five records changed between two local captures) are evidence this metric is meant for; they
are not yet a reconciliation.
