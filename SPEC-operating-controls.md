# Spec: operating controls — V1-03

## O1: workflow stage diagnostics

Continue the approved [V1-03 roadmap](docs/roadmap/agent-backlog.md#v1-03--operating-controls)
after owner-merged #146 (`476f9be`, reviewed `ded3478`). V1-02's current-profile
workflow-recovery code checkpoint is complete. This increment lets a local
operator correlate a failed application stage with its durable request and run.
It does not activate collection, schedules or a hosted logging service.

Assumptions: one trusted operator; existing PostgreSQL journals remain
authoritative; stderr is supervised privately; default execution stays unchanged.
No new dependency, migration, CI setting, source budget or live operation.

## Contract

- `NIMA_WORKFLOW_EVENTS` accepts `off` (also the unset default) or `stderr`.
  Any other value raises fixed `diagnostics_configuration` before stage work.
  Configuration is read once per stage invocation.
- Instrument the existing SDK-independent `prepare_request`, `collect_request`,
  `project_request` and `finalize_request` functions. Preserve signatures, return
  payloads, SQL transitions, source pacing, durable budgets and original errors.
  Diagnostics performs no additional SQL or HTTP requests.
- Enabled stages emit compact JSON lines to stderr: `schema_version` equal to
  `nima-workflow-stage-event-v1`, `source` equal to `kimdis.contract`, `stage`,
  `event`, `request_id`, fresh per-call `invocation_id`, `run_id` (initially null),
  and `processed_at` (UTC event-processing time). A selected durable run emits
  `run_selected`; normal completion emits `succeeded`; an exception emits `failed`
  or `interrupted`. At most three events per call, each under 1 KiB.
- Terminal failures add only `reason` and boolean `retryable`. Known workflow
  codes come from an explicit allowlist; standard HTTP status codes may appear
  as `http_NNN`. Unrecognized workflow codes become `unrecognized_failure`,
  other unexpected exceptions `unexpected_error`. No exception text, SQL, DSN,
  path, name, tax identifier, source payload, monetary value or result dictionary
  is serialized. This guarantee covers these events, not third-party logs.
- A processing timestamp is neither a source timestamp nor a freshness claim.
  Stage success does not mean workflow completion, coverage, source currency or
  analytical correctness. A successful projection call may leave events pending.
  Retry invocations receive different invocation IDs without resetting SQL state.
  A process kill may leave only an opening event; absence of a terminal event
  means unknown outcome. Inspect SQL before retrying.
- Serialize each complete line/write/flush within one process. No cross-process
  ordering, durable delivery, log archive or exactly-once guarantee is promised.
- Opted-in stderr write/flush failure raises fixed `diagnostics_unavailable`.
  An opening failure prevents stage work; a later failure can follow committed
  SQL. Do not infer rollback or repeat with a new request identity. If stage work
  is already raising, preserve that exception and attach a fixed
  `diagnostics_unavailable` note if its failure event cannot be delivered.
  Default-off execution never writes to stderr.

## Implementation and style

Python 3.12+, stdlib JSON/context manager/lock/UTC clock, existing psycopg and
pytest. `src/nima/orchestration/events.py` owns the bounded event contract;
`pipeline.py` selects run IDs using existing reads. Tests live in
`tests/test_workflow_events.py`; the private operator procedure lives in
`docs/operations/workflow-diagnostics.md`. No global logging reconfiguration.

```python
with workflow_stage("prepare", request) as events:
    # Existing work and durable run mapping.
    events.bind_run(run)
```

## Verification and finite checkpoint

1. Freeze contract/plan/tasks; test default-off, strict mode, event correlation,
   failure redaction, interruption and sink failures before/after real SQL work.
2. Instrument all four stages; run a synthetic PostgreSQL/HTTP workflow and
   retry/failure paths. Compare durable results and unchanged budgets. Prove
   process termination leaves an open trace and SQL remains authoritative.
3. Review correctness, readability, architecture, privacy and performance. A
   failure-redaction mutation must fail its regression and be restored. Verify
   the installed wheel, complete local gates/audit and exact-head hosted jobs.

Commands: `uv run --frozen pytest tests/test_workflow_events.py -q`,
`uv run --frozen ruff check .`, `uv run --frozen mypy`, `just check`, `just audit`.
Use only disposable PostgreSQL 17 and synthetic local HTTP fixtures. Preserve
90% combined coverage and all existing assertions/checks. Never commit private
logs, source data, credentials or pilot evidence. No pending owner requirement
blocks this code increment under the existing continuation authorization.

O1 ends at one verified review-ready PR. V1-03 remains incomplete until scoped
runtime-role proof, approved off-host restore, protected operator configuration,
full policy/child health and effective branch-rule findings are addressed. Those
are separate work, not implied by O1 or permission to deploy it.

## O2: selected refresh-policy health

Continue after owner-merged #147 (`6f706f1`, exact reviewed `f230ea0`). Add one
read-only `dataops refresh-health` command to expose recorded policy gaps,
unresolved children and aging observations. Existing `refresh show`, selected-run
health, event formats, recovery actions and source budgets retain their contracts.

### Contract and limits

- Required inputs: explicit policy UUID, absolute private output directory,
  `--max-tick-age-hours` and `--max-observation-age-hours` (integers 1–8760).
  Use the protected `NIMA_DATABASE_URL`; no credential-bearing CLI argument.
- Read one REPEATABLE READ, READ ONLY PostgreSQL snapshot with five-second
  statement and two-second lock timeouts. No locks for control, source/engine
  calls, filesystem archive inspection, migration, grant or journal mutation.
  Set local `row_security=off` to refuse reads that would be filtered by RLS;
  this does not bypass access policy or grant access to hidden records.
  Decode saved policy intent and compatibility in that same snapshot without
  constructing a filesystem-validating execution policy.
- Bound saved configuration to 16 KiB before driver deserialization; return at
  most 14 children, seven recent query dates and seven oldest missing dates.
  Refuse excess/missing/mismatched cycle children, rather than truncating them.
  Bound the canonical private report to 32 KiB. SQL aggregates remain protected
  by statement timeout; this is not a constant-time national history scan.
- Prefer the single open cycle to a later completed cycle; otherwise select the
  latest cycle. Inspect all its children and recorded request/run IDs, states,
  start/update times and consumed budgets. Use existing `RecoveryBudget` policy
  for conservative headroom diagnostics, without authorizing recovery.
- Count completed distinct query dates from policy start through yesterday in
  Europe/Athens. Report the gap count and up to seven oldest gaps. For each of
  the last seven eligible dates, select its latest completed business-date cycle
  and report its reconciled window observation time and whether it was
  reobserved for today's business date. Completion is recorded SQL evidence;
  this command does not reverify archive/projection contents.
- Keep processing sample/tick/request-update clocks separate from reconciled
  source-window observation clocks. Missing/future clocks, threshold age strictly
  greater than its configured limit, missing coverage, overdue overlap, paused/
  retired/pending policy, incompatible processing pins and unresolved child work
  produce fixed attention reasons. Complete request labels alone never establish
  reconciled coverage. Worker liveness and publisher correction coverage remain
  unknown. `checks_passed` means only these selected recorded checks passed.
- Publish through the existing private no-clobber artifact publisher. The JSON
  artifact carries version `refresh-health-v1`, policy/selected-cycle/child IDs,
  thresholds, clocks, counts and fixed reasons. No company, buyer, archive path,
  saved configuration, raw driver/engine message or stored failure text is copied.
  stdout contains only status/attention count (or a fixed failure). Stderr contains
  fixed started/completed/failed component events, with no source values.
- Exit 0 checks passed, 3 attention, 2 invalid configuration, 1 operational/
  integrity/publication failure, 130 interruption. Invalid/absent/corrupt evidence
  must never become an empty healthy report. Existing command routes stay intact.

### Slices and finite acceptance

1. Pure typed snapshot/assessment tests for boundaries, clocks, coverage and
   child budgets; implement without source or workflow-SDK dependencies.
2. Bounded SQL adapter and actual restricted-role tests: immutable source state,
   unavailable/schema/size/cardinality refusal, open-cycle preference and an
   interleaved commit proving a single frozen snapshot/read-only transaction.
3. Actual CLI/private output/error/redaction proof, operator procedure and current
   project/chapter progress. A removed blocked-child guard must fail its regression
   and be restored. Installed wheel, full `just check`/`just audit`, unchanged
   committed contracts and exact-head hosted jobs precede review-ready delivery.

Code: `dataops/refresh_health.py`, `dataops/refresh_health_store.py`,
`dataops/refresh_health_cli.py`, existing command router; focused pytest files.
Use stdlib/dataclasses, existing psycopg and private artifact helpers. Commands:
`uv run --frozen pytest tests/test_refresh_health*.py -q`,
`uv run --frozen mypy`, `just check`, `just audit`. Preserve 90% coverage and
all existing gates. No dependency, migration, CI, live acquisition or schedule
change. O2 ends at one verified review-ready PR; remaining V1-03 deployment,
runtime-role, off-host restore and repository-control acceptance stays separate.

## O3: runtime-role and evidence-protection audit

Status: **approved by the owner on 2026-11-19 with the decisions below.** Continues
after owner-merged #148 (`d09ec20`, exact reviewed `9d866f0`). It addresses the
V1-03 exit item "enforce non-owner runtime writes and immutable evidence". Today
that proof is per feature: each evidence table has its own immutability trigger
and a few role tests exist, but nothing states the whole role contract or fails
when a new table arrives unclassified or a role holds more than intended.

### Objective

One packaged, versioned **access contract** drives two commands, so documentation,
grants and checks cannot drift apart:

- `dataops access-audit` is read-only. It compares a named role's effective
  privileges, and the protection of every Nima table, with the contract.
- `dataops access-grants` only **prints** the reviewed `GRANT` statements for a
  profile and role name. It never connects to a database or executes SQL; the
  owner reviews and runs the output. Provisioning stays an owner action.

An operator learns, from catalogue state at one snapshot, whether a runtime role
could rewrite evidence. A pass proves catalogue state only, not passwords,
`pg_hba.conf`, network exposure, a compromised superuser or a deployed role model.

### Decisions recorded

1. **Profiles, not four coarse classes.** The runbooks already define narrow
   per-capability roles, so the contract uses named access profiles. A profile is
   a privilege **ceiling**: holding less is fine, holding more is attention.
   Version 1 profiles come only from documented grants: `analytics-reader`,
   `run-health-reader`, `refresh-health-reader`, `validation-writer`,
   `validation-reader`, `retirement-operator` and `successor-operator`. The two
   health readers are separate because their runbooks grant different tables. This
   splits the former single "operator" idea into read-only health and separate
   recovery-control roles. Database CONNECT is granted separately and is not part
   of the contract.
   `ingest-worker` and `projector` have no documented grant list. Their ceilings
   are **not** part of this PR: deriving a safe ceiling needs a separate design and
   proof that the real workers run under it (ingestion spans many tables and
   several distinct duties). They are a separately approved follow-up (O3e); none
   is guessed.
2. **Grant script included.** `access-grants` is generated from the same contract
   and is print-only. Role names are validated and quoted as identifiers. A test
   applies generated grants to a disposable database and requires the audit to pass.
3. **Restore check.** The audit runs against a restored backup as one check of the
   off-host restore rehearsal; the restore runbook records this. It is evidence for
   that rehearsal, not a replacement for it.

### Assumptions (still open to correction)

1. Schemas in scope are `nima`, `nima_processing` and `nima_validation`.
2. Every table is classified `evidence` (append-only), `control` (mutable by
   design, with named writer profiles) or `reference`. An unclassified table is a
   failure, so later migrations must classify what they add.
3. No new dependency, migration, CI change, live acquisition or deployment.
4. Tests use a disposable local PostgreSQL 16 through `NIMA_TEST_DSN`, as existing
   store tests do.

### Contract and limits

- Audit inputs: `--role NAME`, `--profile NAME`, absolute private `--output-dir`.
  Connection comes from protected `NIMA_DATABASE_URL`; no credential-bearing
  argument. Grants inputs: `--profile NAME`, `--role NAME`; output goes to stdout.
- One REPEATABLE READ, READ ONLY transaction with five-second statement and
  two-second lock timeouts. Uses catalogue functions and views only; reads no
  application rows and takes no control locks. Object and trigger lists come from
  the transaction snapshot, but PostgreSQL's privilege functions return the newest
  committed grants even inside it (verified on a real server). A grant committed
  during the audit is therefore reported, never hidden. The audit is point-in-time,
  not an atomic cross-object snapshot.
- Per evidence table: a `BEFORE UPDATE OR DELETE` immutability trigger exists and
  is enabled (`tgenabled = 'O'`); the audited role holds no UPDATE, DELETE,
  TRUNCATE or TRIGGER privilege on it unless the profile ceiling names that exact
  column or operation. Per control table: only the contract's writer profiles may
  write. Column-level UPDATE grants count as UPDATE.
- Per role: not superuser, no CREATEROLE/CREATEDB/REPLICATION/BYPASSRLS, owns no
  Nima object, holds no CREATE on a Nima schema or the database, is not a member
  of the schema owner role, and has no sequence or function privilege beyond its
  profile ceiling.
- At most 128 tables and 64 sequences/functions in scope; excess is refused, never
  truncated. Canonical private report at most 32 KiB, version `access-audit-v1`,
  containing contract version, role name, profile, snapshot time, object names and
  fixed reason codes only. No passwords, connection strings, server grant text or
  row data.
- Exit codes follow O2: 0 passed, 3 attention, 2 invalid configuration, 1
  operational or publication failure, 130 interruption. An unreadable catalogue,
  a missing role or an unknown profile is a failure, never an empty pass.
  `checks_passed` means only these recorded checks passed.

### Slices and finite acceptance

1. **O3a** pure typed contract and assessment: table classification, profile
   ceilings, fixed reason codes, unclassified-table and excess-privilege cases.
   No database or new dependencies.
2. **O3b** pure grant renderer from the same contract: identifier quoting, refusal
   of invalid names, deterministic output, and a test that every rendered grant is
   within its profile's ceiling.
3. **O3c** bounded catalogue adapter with real roles: a least-privilege reader
   passes; generated grants applied to a fresh role pass; UPDATE on evidence, a
   disabled or dropped immutability trigger, a TRUNCATE grant, a superuser, an
   owner and a table added after the contract each produce their exact reason.
   A grant committed mid-audit is seen, not hidden, and the audit changes nothing.
4. **O3d** actual CLI for both commands, private no-clobber artifact, redaction
   proof, operator runbook with the grant matrix, restore-runbook entry,
   installed wheel, restored guard
   mutation (removing the evidence-trigger check must fail a regression), full
   `just check` and `just audit`, unchanged committed contracts and exact-head
   hosted jobs before one review-ready PR.

Code: `dataops/access_contract.py` (with a packaged contract resource),
`dataops/access_audit.py`, `dataops/access_audit_store.py`,
`dataops/access_grants.py`, `dataops/access_cli.py`, the existing command router
and focused `tests/test_access_*.py` files. Commands:
`uv run --frozen pytest tests/test_access*.py -q`, `uv run --frozen mypy`,
`just check`, `just audit`. Preserve the 90% coverage floor and every gate.

### Boundaries

- Always: fail closed on anything unclassified or unreadable; keep reports free
  of secrets and row data; test with real roles, not mocks.
- Ask first: any migration, dependency or CI edit.
- Never: execute grants or change roles from either command, connect to a live
  deployment, or describe a passing audit as proof of a secure deployment.

### Findings recorded during O3a

- The contract classifies 33 tables: 22 evidence and 11 control, pinned by an
  explicit test so any change to the classification must be a visible edit.
- Only 7 of the 22 evidence tables (those from migration 0008 onward) have a
  TRUNCATE-blocking trigger. The other 15 block UPDATE and DELETE only, and row
  triggers do not fire on TRUNCATE. For those 15, TRUNCATE is protected by
  withholding the privilege from runtime roles, which the audit checks, but the
  table owner is not blocked. The audit lists the 15 as fixed limitations. Adding
  TRUNCATE triggers would be a migration and needs separate owner approval.
- O3c needs PostgreSQL 17 (the migration runner refuses any other version). The
  hosted CI service container is 17; the O3a/O3b slices need no database.

## O3e: worker role profiles

Status: **approved by the owner on 2026-11-19; slice O3e-1 in progress.** Decisions:
per-duty profiles (recommended option), a sequence grant only where execution proves
it necessary, and the optional TRUNCATE-trigger migration approved as a **separate**
increment (its own branch, spec section and PR) after O3e-1. Follows
owner-merged #149 (`fa4d772`). O3 shipped seven profiles whose grants are documented
in runbooks. The pipeline workers that actually write evidence have no documented
grant list, so they are not yet covered. This spec closes that gap without guessing.

### What is known

- Every command reads the same `NIMA_DATABASE_URL`; only validation has its own
  variable. The code does not separate worker roles, so the grants a worker needs
  are defined only by the SQL its command runs.
- The projector writes `projection_contracts`, `projection_mentions`,
  `projection_receipts` and updates `outbox.delivered_at`; it reads
  observations and the outbox with `FOR UPDATE SKIP LOCKED`. Ingestion, GEMI
  import, replay promotion and the workflow and refresh engines each write other
  tables. No exhaustive per-command table exists yet; grep of `INSERT/UPDATE`
  statements is not a safe source because statements span lines and call helpers.

### Approach: ceilings proven by execution, not by reading

A ceiling is the smallest privilege set under which the real command completes,
proven in two directions on a disposable PostgreSQL 17 database:

1. **Sufficient:** grants printed from the candidate profile are applied to a fresh
   NOLOGIN role and the actual command (or the actual store function it calls)
   completes with the expected result and unchanged evidence bytes.
2. **Necessary:** removing each table-level privilege, one at a time, makes that same
   run fail with a permission error. A privilege whose removal changes nothing is
   not in the ceiling. This stops a ceiling from drifting wide.

The candidate set starts from static SQL review of the command; execution decides.
The audit then covers the new profile automatically, since it reads the same
contract. No privilege is ever added because "it might be needed".

### Proposed profiles and order

Each profile is one **duty**, not one process, so a role can be as narrow as the
duty. Recommended order, each its own reviewed slice:

1. `projector` (smallest, clearest SQL above).
2. `collector` (page, raw object, record version, observation, quarantine, outbox,
   run and HTTP-attempt writes).
3. `gemi-importer` and `replay-promoter` (separate commands with separate tables).
4. `workflow-runner` and `refresh-engine` (workflow and refresh control tables).

Stopping after slice 1 or 2 is a valid outcome. Profiles for later duties are
approved one at a time.

### Decisions needed

1. **Granularity.** Per duty as above (recommended), or one broad `pipeline-worker`
   profile. A broad profile is faster but lets the projector hold collector write
   rights, which defeats the purpose of the audit.
2. **Sequence use.** Identity sequences (`observations`, `http_attempts`) are written
   through INSERT. Confirm that USAGE on the sequence is part of the ceiling only
   where execution proves it necessary.
3. **TRUNCATE gap (separate, optional).** Fifteen older evidence tables have no
   TRUNCATE trigger. I recommend a small additive migration `0013` adding statement
   level BEFORE TRUNCATE triggers to those tables, with tests proving existing rows
   and the 22-table evidence classification are unchanged. It is a schema change and
   needs your explicit approval; it is **not** part of O3e unless you say so.

### Boundaries

- Always: disposable databases only; evidence bytes compared before and after each
  run; failures are fixed codes.
- Ask first: any migration, dependency or CI change, including the TRUNCATE triggers.
- Never: grant to, or audit, a live deployment from tests; widen a ceiling without a
  failing necessity test; run a source or engine call to learn what a worker needs.

### Slices and acceptance

1. **O3e-1** `projector`: contract entry, sufficiency and necessity tests with the
   real `drain` function, audit passes, runbook row.
2. **O3e-2** `collector`: same shape with a recorded-sample fixture and no network.
3. Later duties only after the previous slice is reviewed.

Each slice ends in one review-ready PR with full `just check`/`just audit` and
hosted exact-head jobs. Existing profiles and the audit report format
(`access-audit-v1`) stay unchanged; new profiles only add names.

## O3f: evidence TRUNCATE guards

Status: **delivered: owner merged #151 at `d3d80c7` (exact reviewed `8da0c32`).** Approved
by the owner on 2026-11-19 (the optional migration in O3e decision 3) as its own increment. Closes the finding
recorded in O3: 15 of the 22 evidence tables (migrations 0001-0007) block UPDATE and
DELETE with row triggers but have no TRUNCATE trigger, and row triggers do not fire on
TRUNCATE. Today only withheld privileges protect them, and the table owner is not
blocked. The seven newer evidence tables already carry a statement-level guard.

### Contract

- Add one forward-only, additive migration `0013.sql`. For each of the 15 tables it
  creates `<name>_no_truncate BEFORE TRUNCATE ... FOR EACH STATEMENT EXECUTE FUNCTION
  nima.reject_mutation()`, reusing the existing function and its 55000 error
  'Evidence rows are immutable'. No new function, table, column, index or data change.
- Tables: raw_objects, run_pages, record_versions, observations, quarantine,
  projection_contracts, projection_mentions, projection_receipts, gemi_imports,
  gemi_responses, gemi_profile_versions, gemi_observations, refresh_events,
  identity_entities and identity_review_events, all in `nima`.
- Effect: TRUNCATE on any of them is rejected for every role, the owner included, and
  `TRUNCATE ... CASCADE` from a referenced table is rejected too. It is a guard
  against mistakes and over-privileged runtime roles, not a boundary against a
  superuser, who can still disable a trigger or set `session_replication_role`.
- Nuance, verified by emptying the migration: PostgreSQL rejects a plain `TRUNCATE` of a
  referenced table with a foreign-key error before any trigger runs, so the guard
  matters for unreferenced tables and for `TRUNCATE ... CASCADE`, which is the form
  that could wipe evidence. Twelve tables were open to a CASCADE wipe and are now
  closed. `raw_objects`, `run_pages` and `gemi_imports` were already blocked indirectly,
  because newer guarded tables reference them; they now have their own independent
  guard. The O3 wording that the fifteen tables were unprotected was too broad.
- Audit and contract: all 22 evidence tables become `truncate_guarded`, so the
  `truncate_not_trigger_guarded:*` limitation list becomes empty and a missing
  TRUNCATE trigger on any evidence table is `truncate_trigger_missing`. Report format
  `access-audit-v1` and all profiles are unchanged; only the limitation list shrinks.
- Compatibility: databases at version 12 apply only 0013; the stored checksums of 1-12
  are untouched. Existing rows, roles, grants and ownership are preserved. No code
  path truncates these tables (checked in `src`, `scripts` and `infra`).
- Rollout: apply only to disposable test databases here. Running `migrate` on the
  private pilot is a separate owner action and is never automatic. A rollback is a
  new forward migration dropping the 15 triggers; it has no data effect.

### Acceptance

1. `TRUNCATE ... CASCADE` of each of the 15 tables is rejected for the owner and for a
   role holding TRUNCATE everywhere, with the fixed error, leaving every table
   unchanged; a plain TRUNCATE never succeeds; UPDATE and DELETE are still rejected.
2. A database built at version 12 with real rows upgrades to 13 with every table's
   rows, grants and ownership identical, and applying 0013 twice is a no-op.
3. The migration history lists 13 entries with unchanged checksums for 1-12.
4. The audit passes with an empty limitation list; dropping or disabling any one of the
   15 new triggers is reported with its exact reason.
5. Normal ingestion, projection and the full suite are unaffected; full gates, wheel
   proof and hosted exact-head jobs precede one review-ready PR.
