# Recovering a refresh child

Use this local operator control for an interrupted or incomplete child whose
original budgets still have headroom. Inspect the policy and selected request
first, using the existing private environment configuration:

```sh
uv run --frozen python -m nima refresh show POLICY_UUID
uv run --frozen python -m nima workflows show REQUEST_UUID
uv run --frozen python -m nima refresh recover POLICY_UUID --request-id REQUEST_UUID
```

Replace both UUIDs with the recorded identities. Recovery authorizes a local
Prefect dispatch; its worker may contact the configured source. This code PR
does not itself run recovery, enable a policy or activate collection. Use the
existing protected worker/egress procedure for an approved live operation.

The policy must be enabled and compatible. The request must be an unreconciled
child in its open cycle, with a sending/accepted window. `allocated` work belongs
to the existing tick path. Recovery holds the policy and global source locks
through the send; busy policy/collector returns `policy_busy`/`source_busy`.
This serializes controls and collection, without establishing worker liveness.
Accepted/queued engine jobs may already exist, so duplicate delivery remains
possible and workers continue to use the same SQL identity/leases/checkpoints.

Recovery requires all original headroom: elapsed time at most 30 minutes from
the original start (if started), fewer than four collection executions, 300 HTTP
attempt reservations and 100 projection batches. Future start clocks are refused.
There must also be fewer than four saved dispatches for this request, including
the original and pending/unknown/manual sends. A recovery reservation adds one
dispatch. These are independent budgets; a dispatch does not reset or consume a
collection execution/HTTP reservation before the worker starts.

Exhaustion returns existing fixed budget codes, or `recovery_dispatch_limit`.
Invalid child selection returns `recovery_child`; a complete request returns
`recovery_complete`. Version incompatibility retains its original fixed code.
Expired/exhausted work stays blocked. Audited policy supersession/terminal
resolution remains later work; changing IDs or deadlines would bypass history.
The general manual `workflows dispatch` command retains its separate semantics;
the new cap is enforced on recovery reservations, not all independent controls.

A successful response acknowledges dispatch only. It retains the request/run,
saved intent, counters and clock; a sending window may become accepted. The next
tick uses existing evidence reconciliation before advancing completed coverage.
An unavailable/lost engine acknowledgement leaves an unknown dispatch; a process
death can leave a pending intent. Both count against headroom. Retry the same
request only after inspecting it. Never infer non-delivery from a lost response.

Exit codes retain refresh semantics: 0 acknowledgement, 1 operational/eligibility
refusal, 2 configuration, 130 interruption. Operational errors contain fixed reasons,
without DSNs, archive paths or arbitrary engine exception text. Argument parsing
retains the shared CLI diagnostics; keep credentials in environment settings.
No SQL/engine
atomic commit or automatic retry is claimed. See the [R1 contract](../specs/SPEC-refresh-recovery.md)
for synthetic process/SQL/control verification and the remaining V1-02 scope.

## Permanently retire a policy

After explicit reviewed migration 0011 and operator grants, retirement is SQL-only:

```sh
uv run --frozen python -m nima refresh retire POLICY_UUID --reason budget_exhausted
uv run --frozen python -m nima refresh show POLICY_UUID
```

Use `NIMA_DATABASE_URL` through protected environment settings. The other reasons
are `processing_incompatible` and `operator_stop`; these are operator
classifications, not verified data-quality findings. Retirement does not decode
stored source configuration or inspect archives. No live retirement/migration is
part of the code PR. Back up/restore using the existing procedure before live DDL.

The database stamps one immutable decision/time/effective principal. Same reason
reuses that decision; a different reason gives `retirement_conflict`. There is no
unretire. The decision survives attempted owner UPDATE/DELETE/TRUNCATE, including
parent-policy TRUNCATE CASCADE. This is a trusted database audit, not protection
against an administrator changing DDL. Principal is stored in SQL, omitted from
terminal summaries. No source data, request ID, clock, counter or window changes.

Retirement closes the SQL reservation gate atomically. It keeps an acknowledged
paused policy paused; otherwise `state=pending` records required engine pause
acknowledgement. New cycles/windows, enable updates and linked child dispatch
reservations are refused, including the general manual workflow path. Already
reserved sends or accepted/running jobs can still finish; retirement is not
cancellation. Independent collectors require the existing operator stop procedure.

If schedule reconciliation is required, run the existing explicit
`refresh pause POLICY_UUID` in the configured worker environment. Engine failure
leaves reconciliation pending and the retirement gate closed. `refresh show`
keeps retirement, processor compatibility and schedule state separate. It samples
retirement with state/coverage in one read-only repeatable-read snapshot. Missing
days and unfinished children remain visible; retirement never completes them.
`refresh plan` remains a date preview and exposes a retirement flag.

The narrow retirement operator needs existing migration/schema access plus:

```sql
GRANT USAGE ON SCHEMA nima TO RETIREMENT_OPERATOR;
GRANT SELECT ON nima.schema_migrations,nima.refresh_policies,
    nima.refresh_retirements TO RETIREMENT_OPERATOR;
GRANT UPDATE(state) ON nima.refresh_policies TO RETIREMENT_OPERATOR;
GRANT INSERT ON nima.refresh_retirements,nima.refresh_events TO RETIREMENT_OPERATOR;
GRANT USAGE ON SEQUENCE nima.refresh_events_event_id_seq TO RETIREMENT_OPERATOR;
```

The role name is a placeholder; no role/grant is created automatically. Existing
inspection roles need SELECT on the new table as well as their prior read grants.
Other worker/inspection operations keep their own grants. The narrow retirement
role was tested without source-table INSERT permission. Migration 0011 adds one
control table (27 total in `nima`); original migration bodies remain unchanged.

Successor linking and explicit new-budget authorization remain a later increment.
Retirement creates no replacement policy/request and transfers no coverage.

## Authorize one fresh successor generation

After reviewed migration 0012, use a **new, unused** policy UUID and an already
retired predecessor. Review the inherited cohort and budget profile first:

```sh
uv run --frozen python -m nima refresh show OLD_POLICY_UUID
uv run --frozen python -m nima refresh supersede OLD_POLICY_UUID \
  --successor-id NEW_POLICY_UUID --authorize-new-budgets
uv run --frozen python -m nima refresh show NEW_POLICY_UUID
```

This creates a paused policy and one immutable authorization atomically. Buyers,
coverage start, archive root and scheduling profile are inherited exactly;
processing pins use the installed supported v1 profile. Existing policies cannot
be adopted. The command uses only database configuration and archive-path
metadata validation, with no evidence reads, archive creation, Prefect/source
request or activation. Live use is separate from code approval and requires the
existing backup/migration and protected-worker procedures.

The required flag authorizes **fresh budgets**, not a reset of old work. The fixed
[`nima-refresh-budgets-v1` profile](../specs/SPEC-refresh-recovery.md#r3-explicit-successor-authorization--final-code-checkpoint)
retains existing request/cycle ceilings, including 300 reserved attempts per
request and at most 14 children per cycle. These are not one lifetime allowance
for an enabled policy. A successor reobserves the inherited range and starts its
own coverage; it receives no copied successful windows. This may revisit dates
already collected by the old generation. Review that cost before separately
enabling a schedule. Old failures, gaps, original bytes and counters remain.

Same-pair retries reuse the original approval/time/hash, even after activation or
runtime changes; they never re-pause or activate it. Another target conflicts.
SQL records the effective principal, time and actual immutable successor config
hash, and rejects used/active/different-scope targets and mutation/truncation.
`refresh show` exposes at most the direct incoming/outgoing links in its snapshot;
it does not combine coverage or traverse an entire chain. Principal/path/source
labels stay out of terminal summaries. Already reserved old work retains R2's
completion semantics.

The narrow successor operator needs schema usage, SELECT on `schema_migrations`,
`refresh_policies`, `refresh_retirements`, `refresh_successions`, `refresh_events`
and `refresh_cycles`; UPDATE(state) on `refresh_policies`; INSERT on
`refresh_policies`, `refresh_events`, `refresh_successions`; and USAGE on
`refresh_events_event_id_seq` (all in `nima`). No source-table INSERT is needed.
Inspection roles additionally need SELECT on `refresh_successions`. No grants
are automatic. Migration 0012 adds one table, bringing `nima` to 28; older bodies
stay unchanged. Source activation keeps its separate existing permissions.

This is the final R3 code checkpoint for current-profile workflow recovery. It
ends at fully verified, review-ready delivery, with main merge and live rollout
tracked separately. The next planned work package is V1-03 operating controls.
