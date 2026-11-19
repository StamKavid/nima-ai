# V1-01: durable readout validation history

Status: scoped implementation under the owner's 2026-11-19 instruction to proceed
after merged #139/#140, main `73f8aa4`. Follow the accepted
[work package](docs/roadmap/agent-backlog.md#v1-01--durable-validation-history-next-implementation-candidate).
This first vertical slice verifies an already-published supplier–buyer artifact.
It does not change the read-only publication command, activate collection or
automatically migrate the private pilot.

## Boundary and identity

The existing readout uses a SELECT-only source connection. Preserve that role and
successful artifact bytes. Add an explicit post-publication validator with a
separate journal connection; do not add INSERT privileges to the source reader.
The validator reconstructs the bounded readout through its existing SQL snapshot,
original reconciliation, calculation and contract gate, then checks the selected
private artifact's hash, contract and byte equality. No source/network request,
new artifact publication, archive repair or source-table write occurs.

An immutable intent binds canonical semantic request hash, declared artifact hash
(the existing lowercase SHA-256 filename), ODCS ID/version/canonical metadata hash
and `nima-readout-verification-v1`. Archive locations and DSNs are not identity.
Invalid CLI/request/name configuration fails before registration; these are not
claimed as durable dataset checks. Missing/unsafe artifact or evidence after a
valid intent is registered produces a durable blocked outcome.

Each canonical UUID attempt has an immutable start and at most one immutable
terminal outcome. A deterministic outcome hash includes intent hash and check
payload, excluding attempt UUID, database principal and wall time. Fresh attempt
IDs perform fresh validation; unchanged results can share an outcome hash.
Reusing an ID with different intent is a conflict. Reusing a completed ID returns
its original attestation/time with `reused: true`, without rechecking the report,
original evidence or source SQL. Request parsing still confirms the intent.
It must never be presented as fresh evidence verification. A pending ID resumes
under a session advisory lock; concurrent use fails as busy, never starts a second
check. Process death releases the lock. A failed attempt stays failed; use a new
ID after repairing inputs.

## Persistence and states

Add migration 0010, creating only schema `nima_validation` and two tables:
`attempts` (intent/hash/start/principal) and `outcomes` (attempt/intent FK, canonical
result/hash/completion/principal). JSON payloads are bounded to 4 KiB. Triggers
forbid UPDATE/DELETE/TRUNCATE, and stamp database time/current principal on INSERT.
Public gets no privileges. No roles are created or grants applied automatically.
All prior migrations/checksums and the 26 source-schema tables remain unchanged.

| State | Meaning |
|---|---|
| pending | Durable intent; no committed outcome, including interruption |
| passed | Current originals/SQL reconstruct the artifact, output contract passes and bytes agree |
| failed | Artifact digest, output contract or reconstructed-byte comparison disagrees |
| blocked | Artifact/evidence/SQL inputs or supported policy cannot be checked |

Fixed check/reason pairs: artifact_integrity/artifact_unavailable (blocked),
artifact_integrity/artifact_digest (failed), reconstruction/inputs_unavailable
(blocked), output_contract/contract_rejected (failed), byte_equivalence/bytes_differ
(failed), byte_equivalence/ok (passed). Only a passed result carries verified
snapshot hash and bounded observation/record counts. Failures record declared
intent, not a fabricated validated dataset reference. Result inspection validates
payload/identity integrity; no source labels, private paths or exception text is
stored in these new tables.

The journal writer is non-superuser, cannot create in project schemas, cannot
mutate source/processing relations, and has SELECT/INSERT only on the journal
tables plus migration-history SELECT. Reject broader journal mutation privileges.
Inspection runs in a read-only transaction and supports a SELECT-only journal
role. This is a trusted local operator journal, not protection against a malicious
database owner or cryptographic certification of government assertions.

## SQL/files recovery

The artifact already exists before validation; this command never publishes it.
Commit intent before file/SQL validation, then one terminal row after checking.
There is no claim of an atomic SQL/filesystem transaction. A crash before outcome
commit leaves pending; retry the same intent. A crash after commit reuses the
saved outcome. Artifact loss/change after an earlier pass does not rewrite that
attestation; a fresh ID can record the new failure. A schema/permission/database
failure prevents a successful journal result; it cannot silently return success.

## Interfaces and implementation

```sh
python -m nima dataops validate-readout --attempt-id UUID \
  --request /PRIVATE/request.json --report /PRIVATE/SHA256.json
python -m nima dataops validation-show --attempt-id UUID
```

`NIMA_DATABASE_URL` remains the source reader. Environment-only
`NIMA_VALIDATION_DATABASE_URL` is the separately configured journal connection;
inspection may use its SELECT-only variant. Existing `dataops health` behavior
and stdout/stderr stay unchanged. New stdout exposes fixed states, IDs/hashes,
counts/timestamps and reused status; fixed stage events go to stderr. No raw
values, paths or DSNs. Exit 0 passed/pending inspection, 3 failed/blocked result,
2 configuration, 1 operational/conflict/busy/unavailable, 130 interrupted.

Use Python 3.12+, existing Psycopg/strict JSON/private descriptor helpers and
frozen dataclasses. Reuse a public preparation function from analytics export;
keep existing publication error mapping and contract monkeypatch regressions.
New policy/model lives in `contracts/history.py`, SQL journal in
`storage/validations.py`, validator/CLI in `dataops/validation.py` and
`dataops/validation_cli.py`. No dependency, CI or quality-threshold change.

## Acceptance and delivery slices

H1: freeze this contract/plan; verify merged prerequisites and identity.
H2: pure canonical intent/outcome rules and actual migration/journal tests;
bounded payloads, immutable/FK/time/role behavior and idempotent conflict handling.
H3: shared analytics preparation with byte/error compatibility tests.
H4: actual validation/inspection commands, real SQL/files, unchanged source rows
and report/original bytes, failed/blocked/fresh/cached outcomes and privacy.
H5: actual process kills before/after terminal commit, concurrent locking and a
meaningful guard mutation, installed-wheel resources, full `just check` and
`just audit`, final-head hosted jobs and reviewable PR. Keep checkout stable while
test workers import it. Use only owned disposable PostgreSQL 17 fixtures.

This records one output boundary. Other dataset contracts, scheduler integration,
retention/pruning policy, cross-source health aggregation and live deployment
remain subsequent V1-01 work. Append-only history is retained until a separately
reviewed archival/retention policy exists; no automatic deletion is introduced.

## VH1: selected-artifact validation health

Owner merged #142 at `ef657aa` and requested continuation on 2026-11-19. Add one
read-only journal-health report for an explicit lowercase artifact SHA-256:

```sh
python -m nima dataops validation-health --artifact-sha256 SHA256 \
  --max-check-age-hours 24 --max-pending-age-minutes 30
```

Use only `NIMA_VALIDATION_DATABASE_URL` and the existing restricted reader profile.
No source connection, report/archive read, new validation, SQL write, migration,
grant, repair, schedule or private deployment. Package metadata is read offline.
This is recorded-validation health, separate from source/capture freshness and
current artifact integrity. Preserve all existing command results and report bytes.

Read the complete selected cohort in one repeatable-read READ ONLY transaction.
Preflight at most 1,000 attempts and 8 MiB of intent/outcome JSON; exceeding either
fails as `validation_limit`, with no truncation. Each cohort query has a five-second
statement/two-second lock bound; connection/schema/role setup keeps existing bounds.
Use one bulk read, verify every stored intent/outcome hash and association, then
close SQL before pure assessment. Never perform per-attempt SQL or trust only a
latest row. Missing cohort produces attention, not a valid zero-check verdict.

The current supported contract must be bound to its actual semantic provider.
Compare recorded contract ID/version/hash and validator version with this policy;
an old-policy pass cannot establish current-policy health. Keep counts for all
historical passed/failed/blocked/pending records and current-policy attempts.

Latest means greatest **start time**, not last completion: an older slow check
must not mask a newer failed/blocked/pending attempt. Equal latest start times are
ambiguous; expose all tied IDs without choosing an arbitrary causal winner.
`checks_passed` requires one latest attempt, current policy, passed/fresh outcome,
no overdue pending attempt and no clock anomaly. Otherwise return `attention`
with sorted fixed reasons: no_checks, ambiguous_latest, latest_pending,
latest_failed, latest_blocked, latest_policy_mismatch, stale_check,
overdue_pending, future_timestamp, clock_order. Earlier failures remain counted;
a later valid pass can resolve their operational attention. Younger older pending
attempts remain visible even when the latest pass is healthy.

Thresholds are explicit operator settings: exact integers, 1–8,760 hours and
1–10,080 pending minutes. Equality is fresh/not overdue; only strictly greater
age triggers attention. Future start/completion or completion before start is a
clock anomaly. These are not provider SLAs. Include SQL sample time, selection,
policy, thresholds, counts, latest IDs/state/times, last current-policy pass time
and `verification_scope: recorded_validation_history_only` in versioned JSON.
Health does not revalidate files or certify metrics, identities or source accuracy.

Exit 0 checks_passed, 3 attention, 2 configuration, 1 operational/integrity/limit,
130 interrupted. Keep fixed private-safe stderr events and no source values,
private paths, principals or DSNs in output. Bound output to 64 KiB.

Slices: VH1a freezes this contract; VH1b introduces typed recorded checks/shared
decoding and bounded SQL history; VH1c adds pure time/policy assessment;
VH1d exposes CLI and operator instructions; VH1e verifies real restricted SQL,
concurrent snapshot consistency, oldest-corruption refusal, exact time/tie/current
policy cases, a guard mutation, installed wheel, full gates/audit and final-head
hosted jobs. Live setup and other dataset boundaries remain later work.
