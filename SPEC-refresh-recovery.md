# V1-02 R1: bounded same-request refresh recovery

Owner requested continuation after #143; exact reviewed `e29e1cd` reaches main
`435326a` (2026-11-19). This is one increment of V1-02, using the installed
spec/planning/incremental/TDD/review workflow. Saved-intent decoding, default
preservation, version refusal and archive replay/promotion already exist.

## Objective and boundary

Give the trusted local operator an explicit retry of an interrupted or incomplete
child without inventing a request/run, resetting its clock/counters or advancing
coverage. Existing `workflows dispatch` is a general manual control; this new
refresh-specific path adds eligibility, serialization and a dispatch cap.

```sh
uv run --frozen python -m nima refresh recover POLICY_UUID --request-id REQUEST_UUID
```

Use existing environment-only local Prefect/database configuration. This command
authorizes a local control-plane send for that child; it may cause the existing
worker to collect under its original saved limits. Implement/test using synthetic
HTTP fixtures and disposable databases only. No live invocation, source request,
schedule activation, migration, dependency or CI change is authorized here.

## Eligibility and durable ordering

Acquire the existing per-policy lock, require compatible enabled policy, and
acquire the same global source lock used by collection. If busy, refuse before
new dispatch evidence or RPC. Hold both session locks through dispatch. Pause,
tick and recovery therefore serialize; queued or otherwise non-collecting engine
jobs can still exist, so worker liveness remains unknown.

The selected request must belong to that policy's open cycle, have no reconciled
completion, and have a `sending` or `accepted` original window. Allocated work is
handled by tick, not recovery. Preserve policy/cycle/window identity. Require the
request's recorded processing versions and fixed v1 limits to be executable.

Reserve a new existing `workflow_dispatches` intent in a row-locked transaction.
Before insertion, read the original request state/start/counters and count all
its dispatches, including unknown/pending/general-manual sends. Refuse complete
requests, future start times, elapsed time strictly over 30 minutes, executions
at 4, attempts at 300, projection batches at 100, or 4 existing dispatches. A
not-yet-started request has no elapsed deadline; starting remains the worker's job.
This conservative first increment requires headroom in every budget. Existing
worker checks still apply if time/headroom changes before execution.

The recovery path permits at most four total saved sends at reservation, counting
the original; failed/unknown sends consume that quota. It does not redefine the
separate general manual dispatch API or claim to cap independent operator actions.
Fixed refusal codes reuse workflow budget/version codes, plus `recovery_child`,
`recovery_complete`, `recovery_clock`, and `recovery_dispatch_limit`.

Commit intent before Prefect RPC; reuse existing accepted/unknown acknowledgement
storage and request-only parameters. Acknowledgement loss is unknown, never
proof of non-delivery. Success may advance a `sending` window to `accepted`, but
never regresses an accepted window or marks work/coverage complete. Reconcile
through the existing evidence path on a later tick. The terminal response has
policy/request IDs, dispatch acknowledgement and existing request status/budget
summary, without DSN/path/source text. Retain existing fixed operational CLI errors
and exit rules; argument parsing keeps the shared CLI behavior. Credentials stay
in environment settings, never arguments.

## Recovery and limits

Process death releases locks. Death before dispatch insertion sends nothing;
death after insertion consumes a pending dispatch; death after acceptance retains
the acknowledged row. Retrying uses the same request and counts prior evidence.
No distributed SQL/engine transaction is claimed. Active collectors cause a
fixed busy refusal. Concurrent recovery attempts serialize or refuse; budget and
dispatch checks/insertion are atomic even when called directly through storage.

Expired/exhausted/incompatible children remain blocked. Policy supersession and
audited terminal resolution need a separate additive schema/retention contract;
this increment must not disguise a new UUID/deadline as recovery. No seven-day
refresh or late-change coverage assumption changes.

## Structure, slices and acceptance

R1a freezes this contract/plan/tasks. R1b adds a small pure recovery budget policy
under `nima.workflows`, source-lock reuse and atomic storage reservation. R1c adds
the refresh control operation/CLI using existing dispatch acknowledgements. R1d
proves actual SQL locks/caps, current-version refusals, unchanged identity and
counters, unavailable/unknown control outcomes, process death and synthetic
completion/reconciliation. Keep typed models, bound SQL parameters and fixed
private-safe errors. Shared collection/ordinary dispatch assertions stay intact.

Tests: pure exact deadline/clock/budget boundaries; actual PostgreSQL including
concurrent reservations; actual CLI and local Prefect/runner with intercepted
source HTTP; SIGKILL/retry evidence; meaningful budget-guard mutation restored.
Use `uv run --frozen pytest tests/test_refresh_recovery*.py`, existing workflow/
refresh/intent regressions, installed-wheel execution, `just check`, `just audit`
and final-head hosted jobs before owner review. Record exact synthetic verification
with delivery. Keep original source evidence/private operational results outside Git.

## R2: permanent, audited policy retirement

Owner merged #144 at `82ded43a`, including exact reviewed `5e90a32`, and requested
continuation on 2026-11-19. R2 stops future reservations for a retired policy;
it is not a budget renewal, source cancellation or successor-policy operation.

```sh
uv run --frozen python -m nima refresh retire POLICY_UUID --reason budget_exhausted
```

Reasons are fixed operator classifications: `budget_exhausted`,
`processing_incompatible`, `operator_stop`. They do not certify the condition.
Use only `NIMA_DATABASE_URL`; retirement does not decode source intent, inspect
archives, load Prefect or issue RPC/source requests. Invalid reason/UUID input
fails before writing. Retire on an existing policy only; repeated same-reason
calls reuse the original decision/time, different reasons conflict. There is no
unretire. Approval is review of this code/migration, not a live retirement.

Add migration 0011: one `nima.refresh_retirements` row per policy, with a policy
FK, checked reason, database-stamped timestamp and effective database principal.
Reject UPDATE/DELETE/TRUNCATE even for the owner. Preserve all migration 1–10
bodies and every existing source/request/cycle/window/budget identity. Schema
`nima` grows from 26 to 27 tables; adjust exact inventory assertions accordingly.
No dependency, CI, grant, private deployment or schedule activation change.

In one transaction, retirement records the decision and closes the SQL gate:
keep already acknowledged `paused` state; otherwise set `pending`, and append the
existing state event. It does not contact the engine. Pending means schedule
pause acknowledgement remains required; the existing explicit `refresh pause`
operation can finish that reconciliation. Failed RPC cannot reopen retirement.

Serialize retirement with existing per-policy controls. PostgreSQL row locks
also serialize retirement with cycle/window/dispatch INSERTs and enable updates;
triggers reject these new reservations after retirement, including general manual
workflow dispatch. Pending/paused updates and acknowledgements of earlier
reservations remain allowed. A committed reservation can still send/finish after
retirement; there is no distributed engine/SQL cancellation claim. Independent
collectors remain subject to the existing operator stop procedure.

Application retirement and dispatch reservation explicitly use READ COMMITTED
control transactions: state/count checks after locks see preceding commits even
when connection defaults are repeatable-read. Dataset read snapshots keep their
existing isolation. Test both defaults, including the final recovery quota slot.
Direct SQL receives the trigger's fixed 55000 refusal; application dispatch maps
that refusal to `policy_retired` before RPC. Other invalid intent/version checks
retain their existing precedence. Source/processing compatibility stays distinct
from retirement. Historical incompatible policies remain stoppable.

`refresh show` reads retirement with state/coverage in its repeatable-read snapshot;
expose `retired`, reason/time, `execution_enabled=false`, and a retirement block
reason. Preserve unfinished children, source observation times and missing days.
Plan remains a preview, adding a retirement flag. Retire output includes version,
policy ID, reason/time, reused flag and schedule reconciliation state, omitting
database principal/configuration. Existing operational error/exit rules remain;
new fixed errors are `retirement_reason` and `retirement_conflict`.

R2a: contract/ADR/plan. R2b: schema/shared lock/retirement API plus actual immutable,
upgrade/role/atomicity/race tests. R2c: execution fences/inspection/CLI and no-RPC
tests, preserving R1 behavior for active policies. R2d: process death before/after
commit, deliberate fence mutation restored, installed wheel, full local gates/
audit and exact-head hosted proof before owner review. Test actual PostgreSQL
and synthetic fixtures only. Successor linking, new-budget authorization and
terminal child/cycle completion remain later; retirement cannot fill a gap.

## R3: explicit successor authorization — final code checkpoint

Owner merged #145 at `3626314` with exact reviewed `0bbdbf6`, then requested
continuation and a clear checkpoint end. R3 finishes this **current KIMDIS v1
workflow-recovery code checkpoint** at a review-ready PR with complete verification.
Owner merge establishes main delivery; private deployment, live collection,
arbitrary future policy formats and the wider v1.0 roadmap remain separate.

```sh
uv run --frozen python -m nima refresh supersede OLD_POLICY_UUID \
  --successor-id NEW_POLICY_UUID --authorize-new-budgets
```

Use existing environment-only database configuration. Require distinct UUIDs,
an already-retired predecessor, an unused successor ID and explicit boolean
authorization. No adoption of existing policies. Inherit the exact buyers,
coverage start, archive root, cadence, overlap, lag and child cap; only processing
pins come from the installed supported profile. Validate recorded old intent/hash
and the new supported intent before writing. Existing archive-path metadata
validation remains; read no evidence bodies and create no archive. No Prefect,
source request, schedule activation or private migration is part of this task.

Approval concerns fresh source-work budgets, not resetting an old request. The
fixed `nima-refresh-budgets-v1` profile retains request ceilings of 100 pages,
3 attempts/page, 8 MiB/body, 20 requests/minute, 20-second request/300-second run/
60-second retry-delay limits; enclosing limits remain 4 executions, 300 reserved
attempts, 100 projection batches and 30 minutes per request, up to 14 one-day
children per cycle and 10 buyers. These are per-request/cycle limits, not one total
lifetime policy allowance. Existing supported-v1 checks remain authoritative.
Future incompatible profiles need their own versioned implementation/review.

Add migration 0012 with one immutable `nima.refresh_successions` authorization per
predecessor and a unique successor: FK to predecessor retirement, FK to successor
policy, required true authorization, fixed budget-profile ID, database-stamped
successor configuration hash/time/effective principal. Enforce distinct IDs,
same non-processing scope, and a fresh paused successor (no ticks, cycles,
retirement or prior enabled/pending state). Reject UPDATE/DELETE/TRUNCATE/CASCADE.
Row locks serialize validation with enable/retire/allocation. The fresh-unretired
target and retired source prevent cycles. Prior migrations 1–11 stay unchanged;
`nima` grows from 27 to 28 tables, with exact inventories updated.

Create the paused successor, initial state event and authorization in **one SQL
transaction** under the predecessor's shared policy lock and READ COMMITTED.
Any collision/error/death before commit leaves no successor or link. Same pair
reuses the original authorization without reinterpreting it against new defaults;
another target conflicts. Reuse may report the successor's current state, and
never re-pauses or activates it. Keep the predecessor/retirement, requests,
clocks, counters, observations, versions, archived bytes and missing days intact.
Existing committed reservations retain their R2 semantics.

The successor starts with its own coverage: **copy no successful windows or
observations as new work**. It will reobserve the inherited range after separate
explicit enablement. Original successes/gaps remain attributable to the retired
generation. Explain this cost before any live use. Inspection includes only the
direct predecessor/successor (at most two links) inside its existing read-only
snapshot; no unbounded traversal or combined coverage claim. Responses contain
IDs, bound configuration hash, budget profile, authorization time, reused flag
and successor state; omit principal, archive path and source labels.

Fixed errors: `succession_authorization`, `succession_not_retired`,
`succession_conflict`, `succession_profile`; retain existing configuration,
policy/archive/database errors and operational exit rules. No new dependency,
CI edit, grants or notifications. Add public configuration/hash preparation
helpers only where needed; avoid a creation/inspection import cycle.

Slices: R3a contract/plan; R3b schema/atomic API and native SQL constraints/upgrade;
R3c CLI/bounded lineage and actual expired-child fresh-observation progress;
R3d before/after-commit SIGKILL, concurrency, narrow-role/guard mutation, installed
wheel, `just check`, `just audit`, historical contracts and exact-head hosted jobs.
Only synthetic/disposable fixtures. Then explicitly report **checkpoint complete**
and stop at owner review. Next planned module is V1-03 operating controls.
