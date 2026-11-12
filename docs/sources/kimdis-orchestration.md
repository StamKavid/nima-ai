# Local durable KIMDIS workflow

Status: **approved**, 2026-11-11. The user approved the workflow scope, then
selected self-hosted Prefect to use an Apache 2.0 orchestration server.
No orchestration component was installed before that selection. Provider module: `source-ingestion` in
CAPABILITIES.md. Supplements SPEC-source-ingestion.md; no new capability module.
Base: merged PRs #20–#21, main `b24c14a`.

## Objective and scope

Run the existing KIMDIS pipeline as a durable, inspectable workflow rather than
requiring an operator to coordinate collection, resume and projection commands.
The first release handles **one explicitly requested bounded contract collection**:
prepare/locate its stable run → collect or safely resume → project that run →
reconcile. It uses a local Prefect server and the existing PostgreSQL authority.

Assumptions: development remains private/local, the existing domain ingestion
semantics stay authoritative, and no GEMI key is needed. Keep registry comparison
as the next identity increment. Recurring scheduling, a source-refresh watermark,
parallel fan-out, Diavgeia/TED, graph/AI work and production hosting are subsequent
increments. Starting development services must never start a live collection.

This follows the reference's first durable-workflow increment. It does not claim
an unattended real-time service. KIMDIS documents daily refresh; a future scheduler
must account for late publication/revisions and cannot equate yesterday's date
window with a complete update feed.

## Reference and documented behavior

- [Course pipeline](https://github.com/neural-maze/substack-brain-course/blob/b6d347435ff9ee9e9abb783594d3b267f73af2bf/kb/functions/ingest.py):
  named steps, bounded retries, per-source concurrency and repeat-safe persistence.
- [Prefect license](https://github.com/PrefectHQ/prefect/blob/main/LICENSE): Apache 2.0.
- [Self-hosted server](https://docs.prefect.io/v3/concepts/server): independent
  workflow state/UI, with no Prefect Cloud account required.
- [Retries](https://docs.prefect.io/v3/how-to-guides/workflows/retries): flow/task
  retry controls; domain writes and recovery still require SQL-backed repeat safety.
  Process termination is distinct from a caught task failure. Do not claim automatic
  continuation after SIGKILL unless a real server/worker test establishes it.

Do not rely on the SDK's time-limited event/idempotency suppression to protect
domain writes or block a legitimate explicit recovery. An HTTP 2xx event receipt
means delivery acceptance, not successful collection or projection.

## Stack and commands

Retain Python 3.12, PostgreSQL 17, HTTPX 0.28.1 and Psycopg 3.3.8. The direct
dependency is `prefect==3.9.2` (Python 3.11–3.15, Apache 2.0), verified on PyPI.
Use the same pinned version for client/server. No Inngest or separate application
FastAPI/Uvicorn dependency is needed. Compatibility and the complete resolved
dependency audit must pass before adoption. The development image pins the
official Python base digest and installs the hash-locked Prefect version with the
application, so client and server match. PostgreSQL is digest-pinned. Do not use
`latest`; production image packaging remains separate.

Implemented development interfaces (use the Compose instructions in README to
keep archive paths in the worker's filesystem):

```bash
uv sync --frozen
docker compose -f infra/compose.orchestration.yml up --build -d
docker compose -f infra/compose.orchestration.yml run --rm app python -m nima db migrate
uv run --frozen python -m nima workflows submit kimdis \
  --request-id REQUEST_UUID --from-date 2026-11-06 --to-date 2026-11-06
uv run --frozen python -m nima workflows dispatch REQUEST_UUID
uv run --frozen python -m nima workflows show REQUEST_UUID
```

NIMA_DATABASE_URL and an operator-configured NIMA_ARCHIVE_ROOT remain environment
configuration. No secret or arbitrary endpoint/path is placed in an event. Dev
services expose only loopback host ports; container callbacks use the private
development network. Prefect exposes its local server/UI; Nima adds no public submission/authentication
API. Prefect control state is stored separately from Nima evidence. Disable
analytics/telemetry and ephemeral/cloud fallback for this self-hosted scope. No cloud account, tunnel, subscription,
external event export or production deployment is part of this increment.

## Work identity and delivery boundary

An explicit request UUID fixes the source, original query, limits, versions and
archive location in PostgreSQL before event delivery. The request binds to one
stable collection run **before any provider request**. Reusing a UUID with changed
parameters fails; submitting the same request again never silently creates another
collection. A new observation run requires an explicitly new request identity.

Persist a pending dispatch before creating a versioned Prefect deployment flow run
with only the request UUID as its parameter. Delivery is at least once. A crash
between SQL commit, send and acknowledgement leaves discoverable pending/unknown
delivery, not lost work or a falsely completed job. Explicit dispatch retries the
same logical request; duplicate events and expired engine deduplication windows
must remain safe through SQL identity and worker leases.

Add a checksum-verified migration 0005 for request/run binding, dispatch and job
execution state/budgets. Preserve source evidence and migrations 0001–0004.
Request parameters and run binding cannot be reassigned during recovery. Engine
run IDs and delivery IDs are distinct from the domain request and collection IDs.

## Durable stages and safe retries

1. **Prepare/locate:** validate the saved request and schema; create or locate its
   single run using existing archive/journal invariants. Orphan preparation files
   cannot imply that a provider call occurred or change an existing mapping.
2. **Collect/resume:** reuse current raw-before-normalize, journal, lease/fencing,
   archive replay and source-change checks. A completed run returns a verified
   summary without fetching it anew. Interrupted work resumes the same run.
3. **Project selected run:** materialize only that run's participation events and
   existing projection version. The current global outbox batch is not proof of
   this run's completion. Keep existing receipt/acknowledgement transactions and
   leave unrelated runs eligible for their own workers.
4. **Reconcile:** compare collection flags, page/observation/quarantine counts and
   projection receipts. Persist job outcome before returning its final summary.
   No workflow is complete while selected work is missing, locked, failed,
   quarantined or deferred. A completed job does not certify a source snapshot.

Named task outputs contain only IDs, hashes, fixed outcome codes and counts.
Never serialize raw source bodies, labels, tax numbers, DSNs or keys into engine
history. SQL remains the authority if the engine loses a response or a task result.

Only one workflow-managed KIMDIS collector may access the source at a time;
enforce this across workers using a database-backed source lease as well as the
engine queue. Retain 20 requests/minute pacing. Independent manual collectors
are outside this workflow-wide guarantee and must not be run concurrently against
the same provider during this first local deployment.

Keep current per-invocation limits: 100 pages, 3 HTTP attempts/page, 8 MiB/body,
20-second inactivity and 300-second cooperative collection budget. Add persistent
request-wide ceilings: 300 provider attempts including resume verification and
unknown-started attempts, four collector executions, and 30 minutes from first
execution. Do not renew these totals when a task or worker retries. Reserve each
provider attempt before sending it. Existing explicit CLI resume behavior stays
unchanged; workflow recovery adds the stricter enclosing budget.

Projection is bounded to 100 batches of 100 events, with a stable task identity
per batch. Do not mark a limited/locked batch successful while selected receipts
remain absent. Limits fail visibly without truncation or automatic fresh runs.
Blocking I/O retains its existing cooperative, not OS-enforced, deadline semantics.

Map invalid configuration, incompatible schema, changed source, corrupt evidence,
authentication rejection, quarantine and exhausted budgets to explicit terminal
or deferred outcomes. Retry only documented transient/execution failures within
the saved budgets. Capture fixed failure classifications; never copy arbitrary
exception text or original event contents into a failure dataset.

## Structure and code style

Keep orchestration adapters in `src/nima/orchestration/`, request state in
`src/nima/storage/workflows.py`, packaged migration 0005, and explicit CLI routing
in `src/nima/__main__.py`. Reuse the collector/resume and projection boundaries;
extract small helpers where needed rather than copying their logic. Tests belong
in `tests/test_workflow*.py`; local services in `infra/compose.orchestration.yml`;
verification notes in `docs/verification/kimdis-orchestration.md`.

Use strict typed inputs, immutable request values, parameterized SQL and existing
Ruff/mypy conventions. Illustrative event-domain value:

```python
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CollectionRequested:
    request_id: UUID
    event_version: str = "nima-kimdis-request-v1"
```

## Verification and acceptance

Use pytest, disposable real PostgreSQL and a real local Prefect server. Write
failing behavioral tests before code. `just check` and `just audit` retain their
current gates and at least 90% combined coverage; no skipped integrations or
weaker checks. Extend CI to run this required engine-backed suite with pinned
services. External provider traffic is mocked or served by a local fixture.

Acceptance requires duplicate events and explicit redispatch to converge on one
request/run; conflicting parameters to fail; source attempts to stay within the
saved enclosing budgets; selected-run projection to exclude unrelated runs; and
all completion flags/receipts to reconcile. Failure and partial outcomes remain
inspectable through SQL status and the local engine timeline without data leakage.

Actually SIGKILL the application worker after a source/SQL commit but before step
acknowledgement, and after projection before its result is recorded. Restart it
with the server still running and retry/redispatch the same domain request; prove safe replay without duplicated observations,
projections or falsely completed jobs. Also interrupt dispatch before/after send.
Do not substitute fake SDK callbacks for the server/runner recovery boundary. Mutate a
meaningful request identity or budget guard and restore it after a failing test.

This proves local worker recovery and domain repeat safety, not engine-cluster
failover, machine power-loss recovery or production availability. Live smoke
validation is a separately explicit bounded date window; installing or testing
the workflow never automatically calls a government API.

## Review decision and boundaries

Always preserve source evidence, domain identity, budgets and unknown outcomes.
The workflow scope, dependency/schema/CI integration and change to self-hosted
Prefect were explicitly approved before implementation. The server is Apache 2.0;
the course's Inngest execution model is a reference, not an installed dependency. Public hosting,
paid infrastructure, recurring source schedules, more connectors, automatic
identity links and graph/model work require their later scoped decisions.

No production hosting choice or GEMI credential is needed for this local scope.
After it is verified, define source-aware scheduling/refresh and continue registry
comparison. No unresolved user data or external-account requirement blocks writing the code.
