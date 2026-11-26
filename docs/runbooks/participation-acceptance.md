# Inspect supplier–buyer data fitness

Use `dataops assess-participation` to assess an existing private U1 supplier–buyer
report against its original captured evidence. It reconstructs the report through
the existing preparation API, then publishes a separate data-fitness sidecar.
It makes no source requests. Metric definitions remain draft.

## Run the command

Use the same private `nima-participation-request-v1`, explicit stored KIMDIS runs,
UTC cutoff and archive bindings that produced the supplier–buyer report. Configure
`NIMA_DATABASE_URL` through environment settings using the existing restricted
reader; credentials never belong in arguments, reports or Git. No journal DSN.

```sh
uv run --frozen python -m nima dataops assess-participation \
  --request /PRIVATE/readout-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

All three paths must be absolute and safe. The report basename is its lowercase
SHA-256 plus `.json`; its private owned directory/file modes are 0700/0600, with
no symlink traversal and one hard link. Its maximum size is **1 MiB**; the
citation consumer retains its separate 8 MiB subject bound. Existing limits of
ten runs, 500 observations and 32 pages still apply to U1 preparation.

If no report exists, the existing `analytics supplier-buyers` command can create
one from the same request and stored evidence. This does not collect new data.
Both the original report and request contain private details; retain them privately.

## Interpret the sidecar

The canonical `nima-participation-acceptance-v1` sidecar is at most 64 KiB,
content-addressed and published with 0700/0600 modes. It binds the subject,
request hash, snapshot, cutoff, source profiles, metric/SQL and unchanged policy
metadata to eleven counters and the per-use decision. It omits tax numbers,
buyer keys, names, normalized records, amounts and physical archive paths.
Hash binding does not make the private sidecar anonymous.

`unknown_suppliers` counts the union of unknown-list and unresolved-country
eligibility flags among unambiguous selected records. Ambiguous revisions have
their own count. Invalid supplier occurrences retain their occurrence grain;
cancellations and unassigned buyers refer to matching supplier records. These
buckets overlap and must not be added into a new denominator. See the exact
[counter mapping](../specs/SPEC-participation-acceptance-readout.md#frozen-policy-and-counter-mapping).

Retain both the decision and provider status. `selection_unresolved`,
`empty_capture`, `no_observations_before_cutoff` and `no_observed_participation`
are distinct; none establishes actual market absence. Readiness does not certify
the draft metric, establish legal company identity or turn record counts into
paid spending. Monetary eligibility remains not applicable.

## Results and recovery

| Exit | Meaning |
|---|---|
| 0 | `ready` or `limited` assessment published |
| 3 | `blocked` or `not_assessed` assessment published |
| 2 | Invalid input/configuration |
| 1 | Evidence, database, contract, size or publication failure |
| 130 | Interrupted |

Stdout contains fixed status, hashes and decision; stderr fixed acceptance stage
events. No private path, source value or arbitrary driver exception is echoed.
The eleven counters are measured from freshly prepared facts; saved flags are
never proof. Every invocation, including retry, calls preparation once. Its SQL
snapshot closes before original-byte reconciliation and publication.

Incomplete, quarantined or zero-page runs fail U1's existing strict boundary:
no sidecar or plausible zero is manufactured. Complete-empty runs still need the
archived empty page. Missing/corrupt originals, changed SQL/projections or report
byte mismatch fail without repair or fallback collection.

Retry the same command after interruption. Source evidence is rechecked before
an identical completed artifact can be reused; conflicting output is not overwritten.
A process kill may leave a private `.tmp-*` file, not an extra completed result.
A previously completed file can survive a later failed verification; its existence
is never a cached pass. Archive relocation preserves identity when bindings select
the same evidence. SQL/filesystem inspection and publication are not one atomic
transaction, and no claim of future availability or source truth follows.

U2–U4 acceptance, durable history, real-cohort validation and certification remain
separate work. [Implementation proof](../verification/participation-acceptance-readout.md).
