# Selected refresh-policy health

This SQL-only command answers whether one recorded KIMDIS policy needs operator
attention. It never dispatches, reconciles, retires or enables work, requests a
source/engine, inspects originals, changes grants or installs a migration.
Existing `refresh show`, selected-run health and recovery retain their contracts.

Use an existing protected `NIMA_DATABASE_URL` configured for a SELECT-only reader:

```sh
uv run --frozen python -m nima dataops refresh-health \
  --policy-id POLICY_UUID \
  --max-tick-age-hours 24 \
  --max-observation-age-hours 24 \
  --output-dir /absolute/private/refresh-health
```

Replace the UUID/path with the selected private configuration. Thresholds are
explicit integers 1–8760 hours, not a publisher SLA. No source acquisition or
schedule is activated by this command. Keep configuration, artifacts and event
streams outside Git; private publication requires owner-only directories/files
(0700/0600) and refuses symlinked destinations. stdout reports only status and
attention count. The complete canonical report is content-named in the output
directory; fixed started/completed/failed events go to stderr.

## What is checked

- Policy state, retirement and compatibility with installed processing pins.
- Recorded coverage from policy start through yesterday in Europe/Athens:
  distinct completed query dates, total gaps and up to seven oldest gaps.
- The seven most recent eligible query dates: each date's latest completed
  business-date cycle, reconciled source-window observation time, observation age
  and whether reobservation for today's business date is recorded. A fresh date
  cannot hide an older/unobserved date elsewhere in that overlap.
- The open cycle, even if a later completed cycle exists; otherwise the latest
  cycle. All its children, request/run IDs, dispatch/request state, processing
  clocks and consumed execution/attempt/projection/dispatch budgets are included.
  Existing recovery policy supplies conservative deadline/budget reason codes.

`sampled_at`, `last_tick_at`, request updates and reconciliation completion are
processing clocks. `source_observed_at` records a reconciled window observation;
it is not a publisher update timestamp or an assurance about every page's age.
An unreconciled child remains attention even if its request says `complete`.
An enabled policy with current tick activity may still have coverage/overlap gaps.
Paused/retired/pending policies remain explicit attention states; health does not
silently interpret them as active. Threshold equality passes; strictly older
observations/ticks and future clocks require attention.

`checks_passed` means these selected recorded checks passed. It does not prove
worker liveness (always unknown here), current archive/projection integrity,
country-wide coverage, old-correction capture, supplier identity, publisher truth
or analyst usefulness. Completed empty captures can pass after evidence
reconciliation. Use [run health](dataops-health.md), [validation history](validation-history.md)
and [archive verification/restore](backup-restore.md) for their separate scopes.

## Reader and bounds

Reader grants: USAGE on `nima`; SELECT on `schema_migrations`, `refresh_policies`,
`refresh_cycles`, `refresh_windows`, `refresh_retirements`, `workflow_requests`
and `workflow_dispatches`. No source bodies, write privileges, schema ownership,
control locks or superuser identity are needed. Operator role provisioning remains
separate; the command never grants itself access or claims a deployed role model.

Reads use a single REPEATABLE READ, READ ONLY transaction, five-second statement
and two-second lock timeouts. Local `row_security=off` causes refusal if row-level security
would apply; it does not bypass policies or expose hidden records. A filtered
cohort must not silently become a healthy report. Saved configuration is bounded
to 16 KiB before JSON deserialization. The report omits its buyer IDs, archive paths
and raw values.
Stored failure strings are not selected. Children are bounded to 14 (a fifteenth
sentinel causes refusal), recent/oldest-missing lists to seven each, and report
bytes to 32 KiB. Missing/mismatched children or invalid saved intent fail rather
than producing a truncated healthy report. History aggregates can grow with the
selected policy's recorded history; the statement timeout remains the bound.

Exit codes: 0 checks passed; 3 attention; 2 configuration; 1 operational/evidence/
publication failure; 130 interruption. Operational failures use fixed reasons,
never raw driver messages or supplied values. An unsupported policy format is an
evidence refusal, not an empty healthy policy. Inspect the selected request and
policy using the [recovery runbook](refresh-recovery.md) before any retry/control
action; an attention report never authorizes recovery or resets a budget.
