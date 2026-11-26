# Spec: durable acceptance history, first citation slice

Module ID: `acceptance-history` (V1-08). Status: **proposed G1–G3; schema/contract
review only**. Baseline: main `2f78f37` after #233, identical reviewed `47d3e47`
tree. Date: 2026-11-26 (Europe/Athens). Extends the separately reviewed journal
boundary in [A3](SPEC-dataset-acceptance.md#owner-decisions).

## Objective and scope

An operator can record and inspect a durable attestation of citation data fitness:
which request/report/policy it concerned, what decision was actually produced,
when the attempt ran, and whether verification was refused or interrupted.
This first vertical slice records the existing citation-acceptance consumer only.
U1–U4 history adapters and aggregate history/freshness queries remain separate.
Existing `assess-*`, publication and legacy validation commands are unchanged.

Assume Python 3.12+, PostgreSQL 17, existing Psycopg/canonical/private-file helpers,
one trusted local operator and explicit private requests/originals. No new library,
service, orchestration framework, source acquisition, deployment or metric rule.
Data fitness remains distinct from metric certification and publisher truth.

## Why the legacy journal stays separate

`contracts/history.py` and migration 0010 admit only the original supplier–buyer
validator, with fixed intent/outcome identities and 4 KiB JSON documents. The
new acceptance sidecars can hold 64 KiB and have different decision meanings.
Keep all existing migration files/checksums, legacy tables, identities, commands
and historical payloads intact. Do not relabel a legacy `passed` validation as a
new data-fitness decision or widen its storage constraints to fit unrelated data.

Propose migration **0015**, subject to checking the next free number at build
time. Add exactly `nima_validation.acceptance_attempts` and
`nima_validation.acceptance_outcomes`, with no new schema. Register the two tables
as immutable evidence in the existing access contract and add dedicated
`acceptance-writer` / `acceptance-reader` profiles. No roles or grants are applied
automatically; migrations run only explicitly, first on owned test databases.

## Stored identity and representation

Each attempt is a canonical UUID. Its intent contains `nima-acceptance-intent-v1`,
`use: citations`, canonical semantic request hash, declared parent-report hash/
format (`nima-source-citations-v1`), recorder profile
`nima-citation-acceptance-record-v1`, and acceptance policy ID/version/hash.
Current admitted policy is `nima.dataset-acceptance` 1.0.0, hash
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
The intent digest uses the existing canonical UTF-8 encoder/hash convention.
Attempt UUIDs, clocks, principals, physical paths, DSNs and transient errors are
execution context and never part of deterministic intent/result identity.

`acceptance_attempts`: attempt UUID primary key, canonical intent hash/document,
database-stamped start/principal and unique `(attempt_id, intent_sha256)`.
Intent JSONB is an object bounded to 4 KiB of stored JSONB text.

`acceptance_outcomes`: at most one row per attempt, the composite intent FK,
canonical outcome hash/document, optional acceptance body/hash, database-stamped
completion/principal. Outcome envelope `nima-acceptance-outcome-v1` is bounded to
4 KiB JSONB text. Store the full canonical `nima-citation-acceptance-v1` body as
`bytea` of **1–65,536 bytes**, not JSONB under an equal-sized text budget.
Its SHA-256 must equal the stored body hash using PostgreSQL's built-in SHA-256;
no pgcrypto extension. The envelope hash binds intent, execution state, actual
fitness/body hash or closed refusal code, excluding attempt/clock/principal.

Use append-only row and statement-level TRUNCATE guards; prevent deletion,
updates, replacement and forged timestamps/principals. Use a new acceptance
stamp trigger function; the legacy stamp function's table-name logic is unchanged.
Revoke PUBLIC privileges on the new objects. SQL constraints bind fields and
states; application reads strictly decode shape/canonical identity/body hashes
and supported recorded profiles before returning any attestation.

## Execution state is not data fitness

| Execution state | Stored assessment | Data fitness | Meaning |
|---|---|---|---|
| `pending` | No outcome row | null | Intent committed, no terminal result yet |
| `assessed` | Exact prepared sidecar bytes and hash | Actual `ready`, `limited`, `blocked` or `not_assessed` | Existing consumer returned a verified assessment |
| `refused` | No body/hash | null | Existing consumer could not produce an assessment |

For `assessed`, preserve the complete existing sidecar bytes, counts, checks,
limitations, model status and request/cohort/policy/definition/SQL bindings. Do
not recalculate the policy or promote a draft model. Verify its parent/request/
policy bindings against the durable intent before committing the terminal row.
Model details and cohort identity are known from preparation, not invented at
intent registration; the declared parent hash binds the selected parent metadata.

For `refused`, record only the fixed existing acceptance code: input, limit,
evidence, database, contract or output refusal. No fake `blocked` assessment,
cohort identity, counts or body may be attached. Configuration/request/path/UUID/
declared-hash errors found before valid registration create no attempt. A missing
or changed report/original after valid registration can produce a durable refusal.
Unknown unexpected failures remain closed operational errors with no synthetic
terminal outcome. Interruption is not a refusal: leave the attempt pending,
unless its terminal transaction already committed; inspect before retrying.

## Fresh checks, historical reuse and crash behavior

Use one session advisory lock per attempt, acquired before registration/lookup.
Register and commit a valid intent before artifact/source verification. Do not
hold a database transaction over file verification. A concurrent caller gets
fixed busy status; process death releases the lock. Terminal insertion and its
body are one journal transaction, with no partial terminal record.

On a new or pending supported attempt, call the existing public
`prepare_citation_acceptance` exactly once. It already guards the private report,
reconstructs originals/SQL, compares full parent bytes and returns assessment
bytes. Do not call the publishing export or introduce another reader/verifier,
normalizer, policy evaluator, file decoder or journal/file two-phase commit.
No source rows, originals, parent or filesystem sidecar are written by recording.

After commit, the same completed attempt returns the same stored attestation/
timestamps with `reused: true` and `verification_scope: recorded_acceptance_history_only`.
It does **not** recheck originals, parent bytes or source SQL. A new UUID performs
a fresh check; equal deterministic results may share an outcome hash. Changed
inputs or later evidence loss never rewrite a completed result.

Reject same-ID reuse with different use/request/declared-parent identity. Validate
stored intents against their own recorded digest/profile, not reconstructed
current defaults. A supported historical completion stays inspectable/reusable
after code/default changes without consulting the current policy or source.
Pending work executes only under its recorded supported profile; unavailable
profiles get a closed refusal, never silent execution under a newer policy.
A new policy evaluation requires a new attempt ID. No in-place outcome upgrade.

## Connections and commands

Use existing environment-only `NIMA_DATABASE_URL` for the restricted source
reader; new `NIMA_ACCEPTANCE_DATABASE_URL` is the journal writer or SELECT-only
inspector. Do not repurpose `NIMA_VALIDATION_DATABASE_URL` or grant the source
reader INSERT privileges. First delivery introduces only these commands:

```sh
uv run --frozen python -m nima dataops record-citation-acceptance \
  --attempt-id 11111111-1111-4111-8111-111111111111 \
  --request /PRIVATE/citation-request.json \
  --report /PRIVATE/REPORT_SHA256.json
uv run --frozen python -m nima dataops acceptance-show \
  --attempt-id 11111111-1111-4111-8111-111111111111
```

Reuse existing request decoding and private/absolute path rules, the citation
parent's 8 MiB bound and the sidecar's 64 KiB bound. No output directory is needed.
Inspection needs only the journal connection, runs in SELECT-only repeatable-read
mode with timeouts and does not require the request, report, archives or source.
Closed JSON output, bounded to 16 KiB, reports IDs/hashes, recorded profile,
execution/data-fitness/refusal, stored times and reused/inspection scope; it does
not print the whole stored sidecar, source values, paths, DSNs or arbitrary errors.

Exit 0 for recorded `ready`/`limited`; 3 for assessed `blocked`/`not_assessed`
or recorded refusal; 2 for pre-registration configuration errors; 1 for journal/
integrity/conflict/busy/unknown failures; 130 for interruption. `acceptance-show`
returns 0 for an intact stored record, including pending or negative records:
inspection success is not data-fitness approval. Fixed stage events go to stderr.
Database failure during registration/finish cannot return recording success.

The journal writer is non-superuser/non-owner, cannot create/own project objects,
has SELECT/INSERT only on the two new tables plus migration-history SELECT, and
cannot mutate or broadly read source/processing/legacy-journal tables. Inspector
has only the corresponding SELECT ceiling. Reject inherited, PUBLIC, column,
sequence, owner-membership and rewrite privilege excess. Reuse the existing
catalogue/audit/grant tooling with explicit new profile/table registrations;
existing profile privilege ceilings stay unchanged. This is a trusted operator
history, not protection against a malicious database owner.

## Structure, style and verification

Pure bounded identities belong in `contracts/acceptance_history.py`, SQL persistence
in `storage/acceptance_history.py`, citation recording in
`dataops/citation_acceptance_history.py`, and parsing/events in a small history CLI
through the existing DataOps router. No generic five-use registry or empty adapters.
Match existing frozen records and closed error conventions, for example:

```python
@dataclass(frozen=True)
class AcceptanceOutcome:
    intent_sha256: str
    execution_state: str
    data_fitness: str | None
    acceptance_sha256: str | None
    refusal_code: str | None
```

After approval, use pytest and owned native PostgreSQL 17 fixtures. Require:
canonical identity/order/bounds; refusal versus fitness honesty; all actual
assessment decisions without fabricated verified data; bytea/envelope limits;
legacy-checksum/row/byte compatibility; composite FK, immutability/TRUNCATE and
database stamp enforcement; real least-privilege writer/inspector/source roles;
fresh attempts versus explicit cached reuse, profile-version survival and intent
conflicts; native counter/original refusal without HTTP or source changes; actual
SIGKILL/SIGINT before/after terminal commit, same-ID recovery and concurrency;
failed journal writes without false success; source loss after earlier success.

Require 100% new line/branch coverage, meaningful restored behavior mutations,
unchanged overall 90% gate, installed-wheel migration/native-command proof,
full local and exact-head hosted gates before merge readiness. Proposed commands:

```sh
uv run --frozen pytest tests/test_acceptance_history.py
just lint
just typecheck
just security
just check
just audit
```

These are implementation verification commands; no history test/module/migration
exists from this draft. A private pure probe confirmed legacy other-contract
refusal, order-stable hash/identity boundaries, null fitness/body for refusal and
the 64 KiB byte-versus-JSON-text representation difference. It performed no SQL/
archive/source access and proves no journal behavior. Probe:
`/workspace/work/nima-acceptance-history-contract-proof/probe.json`.

Always preserve immutable evidence, explicit unknowns and historical scope.
Changes to policy/model rules, existing migrations, dependencies, CI or further
uses need separate review. Never repair source data, insert new acceptance into
legacy tables, auto-apply grants, present cached attestations as fresh, certify
a metric or automatically merge/deploy. This checkpoint ends at a verified
citation record/inspect slice; revisit actual-cohort proof before expanding
history adapters. V1-08 and release acceptance remain open.

## Owner decisions requested

- **G1 — storage/scope (recommended):** additive migration/two tables in
  `nima_validation`, bounded bytea sidecar plus small envelopes; keep legacy
  identities/tables/checksums intact. First citation record/inspect only.
- **G2 — meaning/recovery (recommended):** pending/assessed/refused execution
  separate from actual data fitness; commit intent first, fresh new IDs, explicit
  historical completion reuse and stored-profile compatibility without revalidation.
- **G3 — access/delivery (recommended):** separate journal environment connection,
  explicit writer/reader profiles and no automatic grants/source writes; implement
  this slice after approval with the native/kill/byte/role gates above.

Approval includes implementation of this bounded schema/command slice only;
U1–U4 history, actual data acceptance, deployment and certification stay separate.
