# Inspect citation data fitness

A trusted local operator can assess one existing
[verified citation report](source-citations.md). This command reconstructs the
report from the selected source ledger and original bytes, then evaluates the
unchanged dataset-acceptance policy. It makes no source requests and writes only
a separate private sidecar. It does not certify a metric or approve a numeric use.

## Inputs and command

Use the same private citation request, explicit stored KIMDIS/Diavgeia runs,
UTC observation cutoff and archive bindings that generated the report. The
combined selection is limited to ten runs. Supply the existing restricted reader
through environment configuration `NIMA_DATABASE_URL`; do not put credentials
in command arguments, a request or Git. No journal database is needed.

The request/report/output paths must be absolute. The report's basename must be
its lowercase SHA-256 followed by `.json`; it is bounded to 8 MiB. Its directory
must be owned and mode 0700, and the regular single-link file owned and mode 0600.
Symlinks, unsafe traversal, wrong hashes, changed metadata and conflicting bytes
are refused. Keep requests, archives and outputs private and outside Git.

```sh
uv run --frozen python -m nima dataops assess-citations \
  --request /PRIVATE/citation-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

Every invocation, including retry, calls the existing preparation API exactly
once. That API owns the SELECT-only repeatable-read snapshot, original-byte and
SQL reconciliation and Python/SQL parity. The freshly reconstructed report must
match the inspected file byte-for-byte. The command never repairs a mismatch,
fetches missing evidence or trusts saved success flags. Source resources close
before publication. Archive relocation changes configuration, not result identity.

## Results and recovery

Stdout reports fixed status and sidecar/subject/policy hashes plus the decision.
Stderr reports fixed `dataops.acceptance` stage events. Neither includes paths,
credentials, source values or arbitrary exception text.

| Exit | Meaning |
|---|---|
| 0 | `ready` or `limited` sidecar published |
| 3 | `blocked` or `not_assessed` sidecar published |
| 2 | Invalid configuration or input |
| 1 | Evidence, database, contract, size or publication failure; no successful assessment returned |
| 130 | Interrupted |

The content-addressed `nima-citation-acceptance-v1` sidecar is at most 64 KiB,
with directory/file modes 0700/0600. It binds the subject hash, request/cutoff,
cohort, run profiles, model/SQL and complete policy definition to checks and
fourteen measured counters with explicit grains. It omits company names, tax
numbers, amounts, record bodies, ADA lists and physical archive paths.

`limited` retains partial/quarantined coverage, unknowns, ambiguity and other
reported diagnostics. Zero admitted pages are disclosed as `no_admitted_pages`,
without a retrieved-byte/date claim. Revoked targets count per citation edge;
shared decisions do not become a false distinct-target count. A pending
revocation is not labelled revoked. See the exact
[counter mappings](../specs/SPEC-citation-acceptance-readout.md#counter-mapping).
A reconstructed subject can receive any policy decision. Broken verification
produces a fixed command failure, never a fabricated dataset reference.

After interruption, retry the same command. A completed identical sidecar is
verified and reused only after reconstructing the source report again. A process
kill can leave a private `.tmp-*` file; it is not a completed result. Preserve
originals and investigate hash/SQL disagreements rather than changing evidence
to make a check pass. A conflicting final file is not overwritten. Publication
and SQL/filesystem inspection are not one atomic transaction; a sidecar attests
only the inspected bytes and cohort, not future availability or source truth.

Publishing this sidecar does not record a journal attempt. Use the separate
[citation history commands](acceptance-history.md) for durable recording and
inspection. U1–U4 history, actual cohort reconciliation and metric certification
remain separate work. Existing citation v1 bytes and their
`metric_eligibility: not_assessed_v1_08` field remain unchanged.
