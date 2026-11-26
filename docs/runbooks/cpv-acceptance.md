# Inspect CPV/month data fitness

`dataops assess-cpv` reconstructs an existing private CPV/month report through
the original verifier, then publishes a separate acceptance sidecar. It makes no
source requests. CPV describes procurement objects, not a company's KAD sector;
the metric remains draft and CPV taxonomy validation remains unchecked.

## Run

Use the same private `nima-cpv-period-request-v1` that produced the report:
explicit stored KIMDIS runs, UTC observation cutoff, optional CPV base code and
inclusive first/last reported month, and archive bindings. Configure
`NIMA_DATABASE_URL` in environment settings with the existing restricted reader.
No journal DSN; keep credentials out of arguments, files and Git.

```sh
uv run --frozen python -m nima dataops assess-cpv \
  --request /PRIVATE/cpv-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

All three paths must be absolute and safe. The report's basename is its lowercase
SHA-256 plus `.json`; owned private directory/file modes are 0700/0600, with no
symlink traversal and one hard link. Maximum report size: **1 MiB**. Existing
preparation bounds remain ten runs, 500 observations and 32 pages. If no report
exists, `analytics cpv-period --request /PRIVATE/cpv-request.json --output-dir
/PRIVATE/reports` creates one from stored evidence without collecting data.

## Meaning

The canonical `nima-cpv-acceptance-v1` sidecar is at most **64 KiB**. It binds the
report/request/cohort hashes, cutoff, run profiles, metric/SQL and unchanged
policy to ten measured counters and the decision. It does not copy selection
details, CPV cells, source IDs, names, tax numbers, amounts or archive paths.
Both reports remain private; hash binding is not anonymization.

`selected_records` means distinct unambiguous latest-selected source records
at the cutoff **before CPV/month filters**. Unknown dates/classification and
cancellations use that same scope. Ambiguous records have a separate counter.
Observations/pages describe all admitted evidence, including after-cutoff rows.
See the exact [counter mapping](../specs/SPEC-cpv-acceptance-readout.md#frozen-policy-and-counters).

One record can contribute to several CPV cells. Never sum cell record or
cancellation counts to obtain distinct-record counts. Classification buckets
partition selected records; date buckets independently partition them. These
dimensions overlap one another. Filters change cells, while diagnostic scope
stays explicit even when no cells match.

Retain provider status alongside `ready`, `limited`, `blocked` or `not_assessed`.
`selection_unresolved`, `empty_capture`, `no_observations_before_cutoff` and
`no_observed_activity` remain distinct. No decision certifies the metric,
establishes market absence/national coverage/source-current state or turns
contract-publication counts into awards, payments or spending.

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
source-cohort connection, then reference SQL on frozen JSON in a separate
read-only connection. Both close before sidecar publication; no second source
snapshot is read for the assessment.

The existing verifier rejects incomplete, quarantined or zero-page captures with
no sidecar. Complete-empty still needs the archived empty page. Missing/corrupt
originals, mismatched SQL/projections or changed report bytes fail without repair
or fallback collection. A saved success flag is never proof.

Retry the same command after interruption. Originals are verified afresh before
an identical completed sidecar is reused; conflicting output is not overwritten.
A kill may leave a private `.tmp-*` file. A completed file can survive a later
failed attempt; its existence never caches a pass. Archive relocation preserves
identity when bindings select the same bytes. SQL/archive inspection and
publication are not one atomic transaction.

U3/U4, durable acceptance history, actual cohort reconciliation and metric
certification remain separate. [Verification record](../verification/cpv-acceptance-readout.md).
