# Inspect buyer-concentration data fitness

`dataops assess-buyer` reconstructs an existing private buyer-concentration report
through its original verifier and publishes a separate acceptance sidecar. It
makes no source requests. The draft metric counts captured contract-publication
participation; it establishes no spending, market share or legal identity.

## Run

Use the same private `nima-buyer-concentration-request-v1` that produced the
report: explicit stored KIMDIS runs, UTC cutoff, exact reported buyer selection
and archive bindings. Configure `NIMA_DATABASE_URL` in environment settings with
the existing restricted reader. No journal DSN; keep credentials out of Git,
arguments and reports.

```sh
uv run --frozen python -m nima dataops assess-buyer \
  --request /PRIVATE/buyer-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

All three paths must be absolute and safe. The report basename is its lowercase
SHA-256 plus `.json`; owned private directory/file modes are 0700/0600, with no
symlink traversal and one hard link. Subject bound: **1 MiB**. Existing ten-run,
500-observation, 32-page and original-byte bounds remain. If needed, create the
report first from existing stored evidence:

```sh
uv run --frozen python -m nima analytics buyer-concentration \
  --request /PRIVATE/buyer-request.json \
  --output-dir /PRIVATE/reports
```

## Counter scopes

The private `nima-buyer-acceptance-v1` sidecar is at most **64 KiB**. It binds
report/request/cohort hashes, cutoff, source profiles, metric/SQL and unchanged
policy metadata to fourteen measured counters. It does not copy buyer/supplier
keys, tax IDs, source IDs, names, rankings, shares, amounts or archive paths.
The parent report retains detailed evidence. Hash binding is not anonymization.

Whole-cohort observations/pages cover every admitted original, including after
cutoff. `selected_records` counts unambiguous latest-selected source records
before buyer filtering; `ambiguous_records` also has whole-cohort scope. Buyer
diagnostics concern only unambiguous latest records matching the reported buyer.
The parent report's evidence list can be smaller than the cohort; it cites the
buyer's and ambiguous sources' observations, including their older/future versions.

`buyer_records = resolved_records + unresolved_suppliers`. Unknown, empty and
all-ineligible supplier lists are unresolved. A partial record has an eligible
supplier and some ineligible occurrences; several bad occurrences still count
as one partial record. Partial and joint records can overlap. Duplicate supplier
ordinals and GR/EL aliases do not multiply one key's participation per record.

One joint contract contributes to several supplier cells. Never use the sum of
supplier counts/cancellations as a distinct-record denominator. Cancellation
counters include unresolved buyer records too. Top share uses resolved buyer
records; unresolved share uses all buyer records. Zero denominators have no share;
all tied top suppliers remain in the parent report. No money is allocated.
See the [exact counter contract](../specs/SPEC-buyer-acceptance-readout.md#counter-and-evidence-scopes).

Retain the policy decision and provider status. `buyer_records_unresolved`,
`selection_unresolved`, `empty_capture`, `no_observations_before_cutoff` and
`no_observed_buyer_records` have different meanings. No decision certifies the
metric or proves source-current state, national coverage or actual buyer absence.

## Refusal and recovery

| Exit | Meaning |
|---|---|
| 0 | `ready`/`limited` sidecar published |
| 3 | `blocked`/`not_assessed` sidecar published |
| 2 | Invalid input/configuration |
| 1 | Evidence, database, contract, size or publication failure |
| 130 | Interrupted |

Stdout exposes fixed status, hashes and decision; stderr fixed stage events.
Each invocation, including retry, prepares once: one read-only repeatable-read
cohort connection, then reference SQL on frozen JSON through another read-only
connection. Both close before publication. The consumer reuses the shared pure
selector once for whole-cohort coverage; it does not re-run the per-buyer metric.

Real partial/quarantined/no-page captures refuse without a sidecar. Complete-empty
still needs its original empty page. Missing/corrupt originals, changed SQL or
projections, report-byte disagreement and malformed bindings fail without repair
or fallback collection. A saved success flag is never proof.

Retry after interruption. Source evidence is verified afresh before an identical
completed artifact is reused; conflicting output is not overwritten. A kill may
leave a private `.tmp-*` file. A completed sidecar can survive a later failed
attempt; its existence never caches a pass. Relocation preserves identity when
bindings select the same evidence. Inspection and publication are not atomic.

U4, durable history, actual cohort reconciliation and metric certification remain
separate. [Verification record](../verification/buyer-acceptance-readout.md).
