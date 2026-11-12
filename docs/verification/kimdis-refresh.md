# Bounded KIMDIS refresh verification

Date: 2026-11-12. Base: main `e80e23f`, merged orchestration PRs #22–#26.
The user approved docs/sources/kimdis-refresh.md by requesting continuation.
No live source request, selected live cohort, activated policy or production
service is part of this increment. Only synthetic provider responses were used.

## Delivered behavior

Migration 0006 stores immutable policy settings, activation history, frozen daily
cycle dates and stable child/request mappings. A unique open cycle and saved
request budgets bound repeat work. A short Prefect coordinator dispatches existing
child workflows without waiting in their runner slot. Explicit enable/pause
uses the same SQL policy lock as allocation/dispatch. Fresh services have two
registered deployments, no policy and no active schedule.

The daily policy is 04:00 Europe/Athens, with seven recent completed query days
and up to seven oldest missing dates, clipped to an explicit policy start.
Replays reuse UUID5 child identity derived from durable cycle intent; a later
cycle legitimately creates new observations for the same source query date.
Unknown or terminal children block further dispatch and later cycles. Partial
collection, quarantine and missing projection receipts cannot advance coverage.

## Observed checks

- Acceptance suite: **469 tests passed**, **92.49%** combined line/branch coverage.
  This includes the existing ingestion, registry, identity and workflow suites.
  Final complete check/audit results and exact delivery heads are recorded in PRs.
- Locked dependency audit: no known advisories. No package or service was added.
  Python 3.12, Prefect 3.9.2 and PostgreSQL 17 remain pinned as before.
- Thirteen pure policy/calendar cases cover Athens DST conversion, midnight/year
  and leap-day boundaries, unsafe roots, cohort validation, clipping, overlap,
  deduplication and bounded planning across a long outage.
- Real PostgreSQL cases verify immutable settings, concurrency exclusion, stable
  cycle/request replay, blocked later cycles, bounded date selection and populated
  v5 upgrade preserving KIMDIS, GEMI and existing workflow evidence. Migrations
  0001–0005 remain unchanged.
- Progress cases verify a later completed date cannot hide an earlier gap, an
  empty window can reconcile successfully, false job completion does not certify
  evidence, and quarantine/exhaustion cannot mint new request budgets. A later
  cycle preserves changed A→B source versions and both observations.
- Eight real Prefect server/process-runner cases verify explicit schedule lifecycle,
  scheduled coordinator execution, duplicate ticks, worker restart, missing
  deployment failure, dispatch SIGKILL on both sides of remote acceptance, a
  pause/dispatch race, and failed/unknown work stopping further sends. Provider HTTP
  alone was intercepted; the engine, SDK and SQL boundaries were real.
- Daily cron/timezone configuration was validated through the actual control API.
  Scheduled execution used a short test-only interval; no wait for a daily trigger
  or claim of an observed production 04:00 run is made.
- Three additional subprocess SIGKILL cases stop before reconciliation, after a
  verified window commit, and after cycle completion. Restart reuses the request,
  retaining one observation and one projection receipt.
- Mutation experiment: changed the cycle business-date guard to allow an unresolved
  old cycle to be reused as a new day. The identity regression failed with
  `DID NOT RAISE`; source was restored byte-for-byte before final checks.

## Review findings addressed

The real restart tests exposed a Prefect 3.9.2 boundary mismatch: a deployment's
empty schedule list clears schedules, while its update API rejects explicit null.
The coordinator leaves the public Pydantic schedules field unset in the SDK update
payload. A real restart must change the deployment registration timestamp and
preserve the active schedule; a cached old API record cannot satisfy that test.
Re-run this regression before changing Prefect versions.

A negative dispatch case showed that skipping an unknown child was insufficient:
remaining allocated children could still be sent. The coordinator now stops new
sends when a child is unknown or terminal, including on an interrupted cycle's
recovery. Accepted/running work can finish after pause, as specified.

SQL values are parameterized and the gap query is one fixed literal. No security
rule, coverage floor, test, dependency audit or secret check was disabled.

## Container/hosted verification

The Compose CI smoke checks explicit schema version six, both installed module
entrypoints, timezone data, non-root execution, absent schedules and empty policy,
request and observation tables. Actionlint validates the workflow configuration.
The new complete Compose stack has not been started locally: the previous image
attempt exhausted this 7.9 GB vfs environment, and available capacity remains
below what its full stack needs. Host-level real server/runner tests are separate
evidence and do not establish current container startup.

GitHub Actions runs, including the merged baseline, remained queued during work.
The integration cannot read Actions permissions (403), so a queue cause is not
claimed. Delivery PRs must remain draft until their final-head quality and Compose
checks pass; queued runs are not successful validation. Branch-protection
configuration is still unverified. User merges and live activation remain separate.

## Five-axis review and practical limits

Correctness: durable cycle intent precedes child dispatch; immutable SQL identity,
saved budgets and verified receipts govern replay/completion. Unknown delivery
stays unknown until evidence or explicit same-request recovery resolves it.

Readability/architecture: pure calendar policy, SQL state, progress inspection,
engine control, coordinator and CLI are separate small modules. Existing manual
collector paths and registry evidence boundaries remain intact.

Security: validated selected-buyer policies, fixed local API configuration,
private archives, redacted outputs and UUID-only engine parameters. SQL state
closes before a pause RPC and remains disabled when activation is unacknowledged.
No raw record, identifier label, DSN or key enters engine parameters.

Performance: at most 14 one-day children per cycle, one open cycle per policy,
one scheduled future run per policy and the existing serial source lease/rate
limits. Gap selection works from successful query dates rather than materializing
every day of an outage; report output is bounded. No throughput benchmark is claimed.

The seven-day overlap may miss older revisions. Query-date coverage is not a
source-wide modification watermark or a provider update SLA. A selected-buyer
pilot is not national coverage. Independent collectors/deployments do not share
this workflow's lease unless they share its database. Manual edits to managed
schedules require reconciliation; paused or blocked state does not cancel work
already accepted by the engine. Graph, models and investigator UI remain later work.
