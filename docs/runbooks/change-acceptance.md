# Assess observed-change data fitness

This offline U4 command assesses a saved `nima-observed-change-v1` report against
fresh reconstruction from its private request and stored runs. It publishes a
separate `nima-change-acceptance-v1` sidecar. The original report is unchanged.
Use the existing restricted reader via environment-only `NIMA_DATABASE_URL`.
No source request, journal write, evidence repair or new privilege is performed.

```sh
uv run --frozen python -m nima dataops assess-changes \
  --request /PRIVATE/change-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

The request uses `nima-observed-change-request-v1`: earlier/later run UUID arrays
and archive bindings. Their union has 1–10 distinct runs; captures cannot share
a run. One empty side remains a valid `no_runs` abstention. Request bound: 16 KiB.
All command paths must be absolute, without symlink traversal. Keep the request
and hash-named report private (0700 directory/0600 file). The subject is bounded
to 1 MiB; the canonical sidecar to 64 KiB, under its SHA-256 filename.

The command reads one source snapshot, checks reference SQL on frozen inputs
through a second read-only connection, then closes both before publication.
Every retry repeats preparation and byte comparison. An existing sidecar does
not cache success; a changed source snapshot may require a newly prepared parent.
Relocating unchanged originals does not change request/report/sidecar identity.

## Read the scope before the decision

`verified_two_capture_cohort`: both captures meet the existing same-query,
complete, quarantine-free, strictly ordered rules. Every admitted original page
is verified. Six counts are explicit: observations, pages, reported page records,
quarantine, distinct category-union records and distinct ambiguity-union records.
Neither summing capture record counts nor summing their ambiguity-list lengths
gives the cross-capture record count. Ambiguity on either side excludes a record
from every category. Empty complete captures still require original empty pages.

`sql_comparability_only`: stored counters establish `incomparable`, and originals
are deliberately not read. The sidecar is `blocked`, retains every sorted native
reason and declares raw verification not performed. Only quarantine is measured;
the other five core counts and version profiles are unavailable, not zero.
The cohort hash is null and run profiles are empty. This diagnoses comparability,
not archive health. Query/time mismatch can coexist with complete capture counters.

`capture_end` is the maximum stored run observation end, on either path, with
`time_basis: stored_capture_end`. It is a deterministic binding, not an operator
cutoff or freshness assertion. The metric remains draft. All-ambiguous captures
can retain `no_observed_change` with a `limited` assessment; that is not evidence
that underlying data stayed unchanged. Missing from a later capture is not deletion.

## Results and recovery

- Exit 0: sidecar published with `ready` or `limited` data fitness.
- Exit 3: sidecar published with `blocked` or `not_assessed` fitness.
- Exit 2: invalid input; exit 1: evidence, database, contract, size or publication
  failure; exit 130: interruption. Failures never turn into synthetic assessments.

Terminal output contains fixed codes and hashes. Detailed record evidence stays
in the private parent; no query text, source/company identifiers or archive paths
are copied to the sidecar. Missing SQL runs, inconsistent originals/projections,
wrong roles, hash/byte disagreement or failed parity produce no new assessment.
Missing originals after a successful positive assessment invalidate the next
attempt; SQL-only abstention still skips originals explicitly.

After interruption inspect the hash-named final file. Atomic publication can leave
a completed artifact or private temp file; retry with the same inputs, preserving
existing evidence. Publication and inspection are not one atomic transaction.
Actual cohort validation, certification and durable acceptance history remain open.
[Contract](../specs/SPEC-change-acceptance-readout.md),
[proof](../verification/change-acceptance-readout.md).
