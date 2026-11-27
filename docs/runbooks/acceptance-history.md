# Citation acceptance history

Record an existing citation report's actual data-fitness assessment in a separate
append-only journal. This is an operator attestation of inspected evidence; it
does not certify a model or establish source truth. Publishing with
`assess-citations` remains unchanged and does not create journal rows.

## Setup

An administrator explicitly applies packaged migration 0015 with the existing
migration command. It adds two tables in `nima_validation`; it does not change
the legacy validation journal or create roles/grants. Back up the database first
for an operational migration; software proof uses owned disposable PostgreSQL 17.

Create separate non-owner roles and review the generated grants before applying:

```sh
uv run --frozen python -m nima dataops access-grants \
  --profile acceptance-writer --role nima_acceptance_writer
uv run --frozen python -m nima dataops access-grants \
  --profile acceptance-reader --role nima_acceptance_reader
```

The writer has SELECT/INSERT only on `acceptance_attempts` and
`acceptance_outcomes`, plus migration-history SELECT. The inspector has SELECT
only. Neither may read source or legacy journal tables, own project objects,
create objects, rewrite history, use project sequences or inherit excess rights.
Use the existing access audit as well as the runtime role checks. A database
owner can bypass operator controls; this is not a hostile-owner audit system.

Configure connection strings privately in environment settings:

- `NIMA_DATABASE_URL`: existing restricted source reader, for fresh recording.
- `NIMA_ACCEPTANCE_DATABASE_URL`: dedicated acceptance writer when recording;
  dedicated SELECT-only acceptance reader when inspecting.
- `NIMA_VALIDATION_DATABASE_URL`: unchanged legacy validation journal.

Do not put credentials in command arguments, request files or Git.

## Record and inspect

Use the existing private absolute citation request and hash-named parent report.
No output directory or filesystem sidecar is produced by recording.

```sh
uv run --frozen python -m nima dataops record-citation-acceptance \
  --attempt-id 11111111-1111-4111-8111-111111111111 \
  --request /PRIVATE/citation-request.json \
  --report /PRIVATE/REPORT_SHA256.json
uv run --frozen python -m nima dataops acceptance-show \
  --attempt-id 11111111-1111-4111-8111-111111111111
```

Registration commits a valid intent before checking the report, originals and
source SQL. One attempt lock prevents concurrent execution. The terminal result
and exact canonical sidecar bytes commit in one transaction:

| Execution | Fitness | Meaning |
|---|---|---|
| pending | null | No terminal result; interruption may have occurred |
| assessed | ready / limited / blocked / not_assessed | Actual existing consumer decision |
| refused | null | Closed verification refusal, without an assessment body |

Recording exits 0 for ready/limited, 3 for assessed blocked/not_assessed or refusal,
2 for configuration, 1 for journal/integrity/conflict/busy/unknown failures, and
130 for interruption. Fixed stage events go to stderr; JSON stdout is bounded
to 16 KiB and includes identities, states and stored times, never source details,
paths, connection strings or the full sidecar. Bodies are bounded to 64 KiB.

After interruption, inspect first. Retrying a supported pending attempt runs the
existing public verifier once. Retrying a completed ID returns the original
result/times with `reused: true` and
`verification_scope: recorded_acceptance_history_only`; it does not check current
source availability. A new UUID requests fresh verification. Later evidence loss
can therefore produce a new refusal without rewriting an earlier assessment.
Different request/parent identity with the same ID is a conflict. Paths can move
without changing the semantic request hash. Historical decoding uses recorded
profiles, not today's defaults; unsupported pending profiles are refused.

Inspection needs only the SELECT-only journal connection and attempt ID. It uses
a repeatable-read, read-only snapshot with timeouts and verifies stored hashes,
envelopes and body bindings. Exit 0 means an intact history record, including a
pending or negative one; it does not approve data fitness.

This first slice covers citations only. U1–U4 history, aggregate freshness,
actual-cohort acceptance and certification remain separate.
[Contract](../specs/SPEC-acceptance-history.md),
[software proof](../verification/acceptance-history.md).
