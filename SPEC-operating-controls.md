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
