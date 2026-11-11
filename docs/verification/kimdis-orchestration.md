# Local Prefect KIMDIS workflow verification

Date: 2026-11-11. Base: merged main `b24c14a`. The user approved the workflow
scope and selected self-hosted Prefect. No official provider request was made
for this increment. Hosted CI and review links belong in the delivery PRs.

## Implemented boundary

Migration 0005 adds immutable request identity, a stable collection-run binding,
append-only dispatch history and persistent budgets. The engine-independent
adapter reuses the existing collector/resume path and scopes participation
projection to the selected run. Prefect 3.9.2 supplies a local deployment, named
tasks, bounded selective retries and process execution. Only the request UUID is
passed to the engine. SQL and the raw archive remain authoritative.

Task caching and result persistence are disabled. Completed SQL evidence is
reconciled on replay rather than relying on Inngest-style memoized execution.
After SIGKILL, explicit redispatch creates a new Prefect run for the same Nima
request/run. This is not a guarantee of automatic crashed-process continuation.

## Observed local checks

- `make check`: **435 passed**, 127.72 seconds; **93.67%** combined line/branch
  coverage (2,842/3,034). Lint, strict mypy, skill integrity, wheel/sdist build,
  Bandit and redacted Gitleaks checks passed without skips or suppressions.
- `make audit`: no known advisories in the hash-locked environment. Prefect is
  pinned at 3.9.2; its package/server license is Apache 2.0. The dependency-only
  change is isolated because its generated lockfile cannot usefully be split.
- Six integration cases ran a real Prefect server and process runner against
  real PostgreSQL 17: normal dispatch, transient task retry, duplicate delivery,
  SIGKILL after collection/projection SQL commits, and SIGKILL around remote
  dispatch acceptance. Provider HTTP alone was intercepted with synthetic bytes.
  The engine/SDK/SQL transaction boundaries were not mocked.
- Crash redispatch retained one domain collection run, one provider fetch, one
  collection execution and one projection receipt. Unknown dispatch stayed
  visible; acceptance was never reported as completed collection.
- Real SQL tests covered concurrent submit, immutable parameters/run binding,
  source exclusion, fenced owners, persistent attempts/executions/deadlines,
  populated v4 upgrade preserving KIMDIS and GEMI observations, run-scoped
  projection, and a resume verification request consuming the last reservation
  before the next page was blocked.
- Mutation experiment: removed the reused-request parameter comparison in
  `RequestStore.submit`. The conflict regression failed with `DID NOT RAISE`.
  The source was restored byte-for-byte before the full checks.
- The built wheel contains migrations 0001–0005. Migrations 0001–0004 are unchanged.
- The digest-pinned Python development image built with hash-required installs
  and verified TLS using a BuildKit CA secret. Image inspection reported
  non-root `10001:10001`. Generated requirements are checked against `uv.lock`.

## Container verification and CI

The local Compose smoke attempt was **blocked by capacity**: this environment's
7.9 GB filesystem and Docker vfs copies exhausted disk while creating containers.
The successful image build does not establish a healthy Compose stack. Only this
increment's disposable image/cache and empty smoke-project volumes were cleaned.

The new workflow job `orchestration-compose` builds the image, starts
Compose, explicitly migrates Nima's schema and checks the installed module-path
deployment, non-root execution, absent schedules and empty source/request tables.
It creates no provider request. Hosted Compose verification **passed** at
`9924c24` in [job 130776657553](https://github.com/StamKavid/nima-ai/actions/runs/43093598298/job/130776657553).
This resolves the startup verification gap left by local disk capacity. Final-head
quality/Compose results are recorded in PR #26. The existing `quality` job runs
the real-engine tests through `make check`
and audits dependencies; no opt-in test flag or weaker threshold was added.
Branch-protection enforcement remains unverified: workflow jobs alone do not make
checks mandatory at the GitHub repository level.

## Five-axis review and limits

Correctness: request identity precedes provider calls; reservations commit before
HTTP, including resume verification. Receipt reconciliation governs completion;
quarantine/partial work is not complete. Failed/unknown delivery remains inspectable.

Readability and architecture: domain state and SDK adapters are separate modules;
legacy CLI defaults remain intact. Prefect server and client use the same lock.
The graph and later SQL analytics/dbt remain outside this increment.

Security: fixed local endpoint configuration, no cloud/ephemeral fallback, private
control/evidence directories, loopback published ports, redacted CLI outcomes and
no provider bodies/identifiers/DSNs in engine parameters. Compose trust-auth SQL
and unauthenticated Prefect are development services, unsuitable for public exposure.

Performance: one workflow collection owner per Nima database, existing HTTP
pacing, bounded task retries, 300 saved attempt reservations, four executions,
30-minute enclosing budget and at most 100 projection batches of 100 events.
Reservations can be consumed without a request if a process dies after reservation.
No throughput or production latency benchmark is claimed.

The workflow lease coordinates workers sharing the same Nima database. Independent
legacy collectors or other deployments do not share that lease; avoid overlapping
source collection outside this worker. Already in-flight HTTP cannot be revoked
by a later lost lease. No recurring schedule, refresh cursor, production service,
accepted live GEMI profile, reviewed identity graph or model was delivered.
