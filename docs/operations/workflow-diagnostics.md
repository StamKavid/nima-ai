# Workflow diagnostics

The four KIMDIS application stages can emit bounded JSON events to stderr.
They supplement [selected-run health](dataops-health.md) and the SQL journals;
they do not certify freshness, coverage, evidence or metric correctness.
Default `NIMA_WORKFLOW_EVENTS=off` preserves current execution. Set the variable
to `stderr` in the **worker process** environment to opt in. Other values refuse
before stage work. Setting it only in the dispatching shell does not configure a
remote worker or an already running container. No schedule is activated here.

For an already authorized native runner, with its existing protected database,
archive and self-hosted Prefect settings:

```sh
NIMA_WORKFLOW_EVENTS=stderr uv run --frozen python -m nima.orchestration.runner
```

This is an operator command, not part of feature verification. The development
Compose file does not pass this variable automatically; any worker environment
override belongs in private operator configuration. Do not paste DSNs, keys or
source captures into the command, repository, PR or public logs. The event format
redacts its own fields; it does not redact unrelated Prefect/third-party output.

## Read a trace

Filter **parsed JSON** for `schema_version=nima-workflow-stage-event-v1` and the
exact request UUID. Every stage call has a fresh `invocation_id`. `started` has
no run yet; `run_selected` connects an existing durable run; then `succeeded`,
`failed` or `interrupted` describes that call. A projection success may leave
work pending. IDs are operational metadata: treat the logs as private.

`processed_at` is the event-processing UTC time. Compare source observation age
using health/journal commands; a recent event does not mean recent source data.
Events contain only fixed fields, UUIDs, timestamp and allowlisted failure codes.
Unknown workflow codes become `unrecognized_failure`; other unexpected failures
become `unexpected_error`. Original errors still propagate to the caller.

For a failed/open trace, use the existing private configuration:

```sh
uv run --frozen python -m nima workflows show REQUEST_UUID
uv run --frozen python -m nima runs show RUN_UUID
uv run --frozen python -m nima refresh show POLICY_UUID
```

Use the run/policy only when recorded for this request. These inspection commands
do not trigger recovery. Check the request outcome/reason, attempts, executions,
deadline, projection state and the policy's blocked child. Follow the
[recovery procedure](refresh-recovery.md) only after inspection; never invent a
new request identity to hide exhaustion. A failure before run selection may have
no run to inspect. Health and SQL remain the durable authority.

`diagnostics_unavailable` means an opted-in write/flush failed. At stage opening,
no stage work starts. At later points SQL may already have committed. If stage
work itself failed and its failure event cannot be delivered, the original
exception survives with a fixed `diagnostics_unavailable` note. SIGKILL can leave
an open trace with no terminal event. None of these proves rollback or delivery.

## Retention and limits

Choose a private supervisor sink before operational enablement: owner-readable
files (0600), parent directory 0700, outside Git and evidence archives. Baseline
retention is at most 30 days and 50 MiB per worker stream, whichever is reached
first; use supervisor rotation (for example five 10 MiB files) and time expiry.
Plan capacity and verify rotation/error reporting with synthetic events. Do not
delete raw evidence or human review decisions as part of log retention. An
incident copy needs an explicit private destination and retention decision.

The application writes and flushes lines under one process lock, at most three
events under 1 KiB each per stage call. This is neither durable delivery nor
global ordering. The host supervisor owns rotation, permissions and collection;
this PR installs none of those. Logs cannot reconstruct a missing journal or
prove worker liveness. Full policy/child health, scoped-runtime proof, approved
off-host recovery and effective branch controls remain V1-03 work.
