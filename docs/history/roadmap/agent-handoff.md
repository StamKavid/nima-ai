# Agent handoff: Nima through v1.0

Use this as the entry point for a new agent. It is a work protocol, not permission
to execute the entire roadmap or activate sources. The owner requested a versioned
plan on 2026-11-18. No agent delegation has been performed by creating this file.

## Read in order

1. Repository `AGENTS.md`, `CONSTRAINTS.md` and relevant pinned `.agents/skills/`.
2. [Release acceptance](../../specs/SPEC-release-v1.0.md),
   [version roadmap](../../roadmap/v1.0.md) and [capability map](../../../CAPABILITIES.md).
3. [Delivered state](../../progress.md), current [plan](../../../tasks/plan.md),
   [tasks](../../../tasks/todo.md), selected card and its referenced source/metric spec.
4. Applicable public operator/runbook documents; private inputs only when the
   current session grants access. Do not assume this agent's environment persists.

## Verify the starting point

```sh
git status --short
git fetch origin main
git log -5 --oneline origin/main
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Do not discard another agent's changes. Use a short-lived branch/worktree and
record its exact base commit. Confirm authenticated GitHub identity before a
push. Owner automation uses repository-local `StamKavid` attribution per AGENTS;
never rewrite legitimate contributors or global Git settings.

Planning baseline is main `9d29845` (#138). #139 is the separate historical
contract-gate delivery: inspect its merge and reachability before using it as a
prerequisite. A feature-branch merge or a stale progress heading is not proof of
main delivery. The roadmap PR changes documentation, not source state or versions.

## Constraints that commonly get lost

- Stack: Python 3.12+, locked `uv`, `just`, PostgreSQL 17, HTTPX/Psycopg and
  self-hosted Prefect; SQL owns durable workflow state. No dbt/graph/vector/model
  runtime has been adopted. Extend the modular monolith with small tested seams.
- Source code/docs are public by owner instruction; originals, source-derived
  pilot results, credentials, requests, databases and task records stay private.
  Do not copy a private result/path/config into a public issue/PR to prove work.
- Current real-data evidence is a bounded KIMDIS pilot, not a national feed.
  Its prior three-attempt source allowance is exhausted. No new source HTTP
  request, schedule, missing-original refetch or Publicity capture follows from
  "continue" on a code task without an applicable acquisition authorization.
- GEMI live access/key and deployed Publicity gateway are not established.
  Preserve operator IP protection. Do not use proxies to bypass access controls
  or transform a failed official API request into unapproved portal acquisition.
- Archive-before-parse, exact Decimal money, source namespace/revision/observation
  history, immutable human decisions and source Greek text are invariants.
  Commitments, decisions, awards, contracts and payments are different stages.
- Reported tax-ID groups are not verified legal entities; CPV is not KAD. Do not
  allocate full joint contract value to every supplier or infer wrongdoing.
- Existing replay, SQL promotion, restore drill, selected health and first readout
  exist. Extend them; do not restart from the older audit's missing-feature list.
- Human PV10, metric certification, sustainable acquisition, late-change behavior,
  shared-service security and effective main/dev protection remain explicit gates.

## Execution and evidence protocol

Select one unblocked [card](../../roadmap/agent-backlog.md). Record its ID, base SHA, scope,
dependencies, affected interfaces, proposed files and acceptance in the active
plan/tasks without deleting older pending work. Prepare only that bounded spec
and implementation. Resolve routine choices from existing approval; consequential
new metric/source/schema/access behavior needs a concrete reviewed contract.

For behavior changes, reproduce a failing acceptance case before implementation.
Use real disposable PostgreSQL/files/processes where the guarantee depends on
transactions, roles or crash recovery. Do not substitute mocks for those boundaries.
Run the relevant focused checks, then the repository gates:

```sh
just check
just audit
```

`NIMA_TEST_DSN` must name a disposable local PostgreSQL 17 database `nima_test`;
never point tests at the pilot/application database. Install/configure tools from
the checked-in runbooks rather than pasting credentials. Keep logs private when
they could contain source data. Run meaningful mutations only on owned test
code/data, restore exact source afterward and record what the mutation proved.

Use small commits, a PR to main, scoped review and final-head hosted evidence.
Required jobs currently include quality, orchestration-compose and
source-worker-egress; paused egress product work does not authorize deleting its
checks. No merge/deploy/release without the applicable owner instruction. Report
blocked operational proofs explicitly and continue independent offline work.

## Handoff payload for each completed card

Provide the card ID, PR and exact head/main status; interface/schema/contract
versions; files and decisions; executed commands/results; local versus hosted
evidence; remaining limits/blockers; next unblocked card. Refer to the approved
private evidence/configuration registry without exposing credentials or inventing
file paths. Never say data is certified because tests passed.

Suggested next-agent prompt:

> Read AGENTS.md and docs/roadmap/agent-handoff.md. Verify main and #139, then
> scope V1-01 from docs/roadmap/agent-backlog.md. Preserve current readout bytes,
> evidence and all pending tasks. Prepare the exact durable validation-result
> contract and failure/recovery acceptance, then implement only within existing
> authorization. Use synthetic/authorized stored inputs; no new acquisition or
> deployment. Finish with a reviewed PR and final-head checks, or a precise blocker.

If several agents are explicitly authorized, assign separate cards/file ownership,
freeze shared interfaces first and integrate through reviewed provider PRs. Do not
parallelize conflicting migrations or independently change a metric definition.
