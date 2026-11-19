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
