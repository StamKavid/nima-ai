# KIMDIS bounded daily refresh

Status: **approved**, 2026-11-12. The user requested continuation after review. Module: `source-ingestion` in
CAPABILITIES.md. Builds on merged orchestration PRs #22–#26, main `e80e23f`.
This contract is implemented on the review branch. No live policy has been enabled.

## Objective and assumptions

Keep an explicitly selected KIMDIS contract cohort regularly observed while
making missing dates, late records and stale evidence visible to investigators.
Reuse the existing SQL-backed Prefect workflow, archive, normalization and
projection. Deliver one bounded local refresh capability, without additional
connectors, identity links, graph, AI or production hosting.

Proposed defaults: one local policy, 1–10 public-buyer IDs, a daily 04:00
`Europe/Athens` trigger, yesterday as the latest query date and a seven-day overlap.
These are operator policy choices, not a provider SLA. A national unfiltered
schedule and historical correction sweeps need later volume/coverage review.
Policies start paused. Approving implementation does not activate a live poller.

## Source and framework evidence

Reviewed 2026-11-11:

- [Official KIMDIS help](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help),
  sections on data refresh, usage limits and contract retrieval: daily/24-hour
  updates, a documented 350 requests/minute ceiling, paginated contract search
  and date-window handling. Nima retains its lower 20/minute rate and explicit
  dates. No documented general modified-since cursor was established in this review.
- [Prefect schedule creation](https://docs.prefect.io/v3/how-to-guides/deployments/create-schedules):
  cron schedules, timezones and inactive schedules. The installed 3.9.2 package
  exposes `prefect.schedules.Cron(..., timezone=..., active=...)` and `Flow.serve`
  accepts schedules. Pin/version compatibility must also be exercised in tests.

The provider's exact daily completion time and whether date filters capture every
late correction remain unverified. Do not reinterpret `dateFrom`/`dateTo` as
modification timestamps or invent ETag/change-feed support. Offset pagination
still cannot establish a point-in-time snapshot.

## Refresh policy and bounded selection

Create an immutable policy UUID fixing its version, connector/normalizer versions,
selected buyer IDs, archive root, explicit coverage start date, timezone, cadence,
lag and overlap. Validate 1–10 distinct positive ASCII buyer IDs; preserve their
text values. Use the worker's configured archive root. Policy creation validates
configuration without creating source archives or contacting the provider.

For business date D in Europe/Athens:

1. The eligible end is D−1. Never query today or dates before the policy start.
2. Select each eligible day in the most recent seven days, including days already
   observed in earlier cycles. This deliberately creates fresh observations.
3. Also select up to seven oldest never-completed dates since the policy start.
   Remove overlap: at most 14 one-day child windows per cycle.
4. Persist the frozen cycle and child mappings before delivery. Never recompute
   their dates from the wall clock during retries, including across midnight/DST.

The unique cycle identity is `(policy_id, business_date)`. A window receives one
persisted request UUID within that cycle. Replaying the same cycle reuses it;
reobserving a day in a later successful cycle uses a new request/run. Existing
content versions remain deduplicated and new observations retain their timestamps.

Cap outstanding children at 14 per policy. An unresolved previous cycle blocks
new cycles; do not accumulate an unbounded engine queue or replace exhausted jobs
with new UUIDs. Catch-up takes successive eligible cycles; expose the remaining
backlog instead of skipping it or silently extending a date window.

## Delivery, reconciliation and pause

Add a small coordinator deployment. A tick reconciles saved work, freezes one
bounded cycle, and dispatches child request UUIDs through the existing dispatcher.
It does not call the provider or wait synchronously for child flows while holding
an engine concurrency slot. Existing child workflows perform collection/projection.

Mappings must survive death between allocation, `RequestStore.submit`, dispatch
and acknowledgement. Use durable intent plus idempotent replay; do not assume
those separate operations are one transaction. Accepted dispatch is not completion.

Retain current child limits: 100 pages/invocation, three HTTP attempts/page,
8 MiB/body, 300 seconds/invocation, 300 saved attempt reservations, four collection
executions, 30 minutes/request and 100 projection batches. Collection remains
serialized by the existing SQL source lease. This covers workers sharing one
Nima database; independent collectors must remain stopped during a live pilot.

A child becomes successful only when the existing SQL evidence reconciliation
proves collection, normalization and selected-run projection complete. Empty,
properly reconciled windows can succeed. Partial, quarantined, source-changed,
expired, failed or unknown work never advances completed coverage. Exhaustion or
crashed/unknown delivery blocks the policy for review. Explicit recovery retains
the existing request UUID/budget; there is no unbounded automated redispatch.

Create the coordinator schedule inactive. Enabling records an auditable SQL state
change and enables only the registered policy's schedule. Every tick checks SQL
state, so a queued tick cannot create work for a paused policy. If engine schedule
activation fails, fail visibly and leave the policy paused; reconcile partial
activation on explicit retry. Pause gates new allocations/dispatches in SQL first,
then pauses the engine schedule; engine failure leaves a visible reconciliation
requirement. Serialize pause and coordinator allocation/dispatch decisions with
a per-policy lock and test that race. Already accepted or running child work may
finish after pause; pause is not cancellation. The existing manual deployment and
fresh default Compose stack retain no active schedule or policy.

## Persistence and truthful inspection

Use additive migration 0006 for policy/configuration, activation history, cycles
and child/request mappings. Enforce immutable identities, unique cycles/windows,
foreign keys, monotonic progress and durable history. Do not change migrations
0001–0005 or store provider bodies/secrets in engine state.

`refresh show` must distinguish:

- Contiguous query-date coverage since the explicit policy start, including gaps.
- Last successful observation time for each recent query date; bounded summaries
  and backlog counts rather than unbounded record/date output.
- Last coordinator attempt, accepted deliveries, actual child outcome, blocked
  reason and schedule reconciliation state. Worker liveness may remain unknown.
- Whether the seven-day overlap is fully reobserved, partially observed or stale.

A coverage cursor describes completed query dates only. It is not a source-wide
update watermark. Absence on a later recheck is not proof of deletion, withdrawal
or wrongdoing. Older revisions outside the overlap and publication delays beyond
it may be missed. Retain old evidence and report those limits.

## Stack, structure and style

Retain Python 3.12, Prefect 3.9.2, PostgreSQL 17, HTTPX and Psycopg; no new package
or service. Keep pure calendar/selection logic in `nima.orchestration.refresh`,
SQL policy/cycle state in `nima.storage.refresh`, and SDK/CLI integration separate.
Add migration `src/nima/storage/migrations/0006.sql` and focused tests alongside
existing workflow tests. Update README and verification evidence after implementation.

Use typed functions, UUID identities, immutable configuration and parameterized
SQL. Example contract, not implemented code:

```python
def select_dates(policy: RefreshPolicy, business_date: date) -> tuple[date, ...]:
    """Return at most 14 explicit query dates; no I/O or implicit current time."""
```

## Commands and activation boundary

Run operator commands in the worker environment, with existing Nima/local-Prefect
configuration. Replace UUID/buyer placeholders. Implemented interfaces:

```bash
uv run --frozen python -m nima refresh create kimdis \
  --policy-id POLICY_UUID --start-date 2026-11-06 --buyer-id BUYER_ID
uv run --frozen python -m nima refresh plan POLICY_UUID --as-of 2026-11-11
uv run --frozen python -m nima refresh show POLICY_UUID
uv run --frozen python -m nima refresh enable POLICY_UUID
uv run --frozen python -m nima refresh tick POLICY_UUID
uv run --frozen python -m nima refresh pause POLICY_UUID
```

`create`, `plan` and `show` make no provider request; plan is read-only. Enable
explicitly authorizes subsequent scheduled collection for that policy. Tick
requires an enabled policy; repeated ticks reuse the same business-date cycle.
The first live cohort/start date is an operator input, not silently selected.
No actual enable or live source run is part of this implementation approval.

Verification commands after implementation:

```bash
uv run --frozen pytest tests/test_refresh_policy.py tests/test_refresh_store.py tests/test_refresh_engine.py
make check
make audit
docker compose -f infra/compose.orchestration.yml up --build -d --wait
docker compose -f infra/compose.orchestration.yml exec app python -m nima db migrate
```

## Testing and acceptance

- Pure calendar tests cover midnight, both Athens DST changes, year/leap-day
  boundaries, start-date clipping, overlap/deduplication and bounded long outages.
- Real PostgreSQL tests cover concurrent ticks, unique/frozen child identity,
  populated v5 upgrade preserving both source histories, monotonic contiguous
  progress, gaps, quarantined windows, backlog caps and pause/dispatch races.
- Real Prefect server/process-runner tests cover inactive defaults, enabled
  scheduling, duplicate ticks and actual SIGKILL before/after child dispatch and
  completion reconciliation. Intercept provider HTTP only; make no official
  source requests in tests. Prefer controllable clocks/short test schedules over
  waiting for a daily trigger.
- Prove a failed/unknown or partial child blocks new cycles without changing
  request identity/budgets. Prove two cycles can observe changed bytes for the
  same query day without rewriting old evidence. Mutate a guard and demonstrate
  the corresponding regression fails before restoring it.
- Keep the existing coverage floor and all quality/security/audit checks. Update
  the Compose smoke migration assertion to six; retain the no-active-schedule,
  no-source-request default checks. This is an explicit CI extension, not a waiver.

Always preserve evidence, validate boundaries and distinguish source freshness
from local processing progress. Approval covers the described schema/CLI/CI
extension and offline/local implementation tests. New dependencies, altered
limits, broader cohorts, production hosting or a different freshness claim need
separate review. Never commit source data/credentials or infer wrongdoing from
collection anomalies. Success is a bounded, inspectable, opt-in refresh service
with demonstrated recovery, not a claim of nationwide real-time coverage.

## Review decision

The user approved the 04:00 Athens cadence, seven-day overlap, selected-buyer
pilot and 14-child ceiling by requesting continuation on 2026-11-12. Exact live buyer IDs and start date are required at policy creation;
provider completion timing and old-record change coverage remain limitations,
not assumptions silently promoted into guarantees. Implementation and acceptance evidence are recorded in docs/verification/kimdis-refresh.md.
