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
Direct SQL receives the trigger's fixed 55000 refusal; application paths return
`policy_retired` before RPC. Source/processing version compatibility stays distinct
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
