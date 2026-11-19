# ADR-0006: Retire refresh policy controls without completing failed work

## Status

Proposed implementation under the owner's continuation after merged #144,
2026-11-19. Code/migration review precedes any live setup or retirement.

## Context

Same-request retry preserves budgets and refuses exhausted/expired work. Treating
abandonment as successful completion would fabricate query-date coverage.
Replacing UUIDs automatically would conceal new spending authority.

## Decision

Add one append-only operator retirement decision per policy. It permanently
fences future SQL allocations/dispatch reservations, with database-stamped time
and principal. Original children, failures, clocks, counters and coverage remain.
Keep retirement separate from acknowledged engine schedule state and processing
compatibility. Already reserved work may still send or finish. Successor policy
linking/new-budget authorization is a separately scoped explicit operation.

## Consequences

An exhausted policy can be stopped honestly without repairing its evidence.
Unfinished windows stay gaps. Pending schedule pause acknowledgement stays visible;
an engine outage does not reopen the SQL gate. Operators cannot unretire a policy.
This adds one control table and lock/trigger checks, with no new service/package.
It does not provide cancellation, successful coverage or a replacement budget.
See the [R2 contract](../../SPEC-refresh-recovery.md#r2-permanent-audited-policy-retirement).

R2 is owner-accepted through #145, main `3626314`. The R3 extension proposes one
atomic, explicit new-budget authorization to a fresh paused successor. It retains
the cohort, binds the successor configuration and budget-profile ID, and copies
no coverage. This keeps renewed authority distinguishable from bounded retries.
See the [final checkpoint contract](../../SPEC-refresh-recovery.md#r3-explicit-successor-authorization--final-code-checkpoint).
