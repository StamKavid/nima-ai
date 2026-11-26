# CI runtime headroom and timing evidence

Date: 2026-11-26 (Europe/Athens). This maintenance slice follows U3 delivery
#231. It changes CI diagnostics and the time allowance, not application behavior.

## Observed baseline

Both completed runs used the same Git tree
`4af97f238f460dcab5bbb2de619b689cbe1078e2` and passed all three jobs.
Job elapsed time includes setup, checks, audit, artifacts and cleanup.

| Run | Quality job | Job elapsed | Pytest elapsed | Tests / coverage |
|---|---|---|---|---|
| [PR 45861771247](https://github.com/StamKavid/nima-ai/actions/runs/45861771247) | 140054334334 | 19m53s | 1,111.57s | 5,049 / 95.31% |
| [Main 45863343061](https://github.com/StamKavid/nima-ai/actions/runs/45863343061) | 140059758591 | 15m06s | 839.10s | 5,049 / 95.31% |

The PR job had seven seconds remaining against its 20-minute limit. The same
tree differed by 4m47s between jobs; these two observations do not establish a
regression, a distribution of runner performance or a root cause. Test execution
dominates both. Timestamped file-progress lines point to workflow/refresh engine
and contract tests as candidates for profiling, but are not individual-test or
phase timings. Local U3 pytest took 759.44s; it is not a comparable hosted baseline.

## Bounded response

- Set the quality job limit to 30 minutes: approximately 1.5 times the longest
  observed whole job, rounded to a minute. This tolerates the observed duration
  while retaining an upper bound; a job can consume ten more runner minutes if
  stuck. It does not fix a hang or guarantee future runs finish.
- Keep `just check` unchanged. It still runs the container-lock check, lint,
  strict types, every test with 90% combined coverage,
  package build and source security. Contract compatibility and dependency audit
  remain separate required steps, and both Docker jobs remain intact.
- Set `PYTEST_ADDOPTS` only on the check step to print the 30 slowest pytest
  setup/call/teardown phases of at least one second and write
  `work/test-results.xml`. JUnit test time includes setup, call and teardown under
  pytest's existing default. Keep `coverage.xml` and add this XML to the same
  `coverage` artifact with seven-day retention and `if: always()`; missing files
  remain allowed when an earlier gate prevents testing. A killed job may not
  finish or upload either report. No real source data is used by this suite.

No sharding, cached test success, database sharing, durability changes, excluded
tests, new dependencies or coverage changes are introduced. This slice makes no
speed claim. Built-in pytest evidence is proportionate before changing the test
harness; a scheduling framework or custom profiler is unnecessary here.

## Verification and next decision

Validate YAML and pytest options, compare gate composition with `just check`,
then require full local `just check`/`just audit` and all three exact-head hosted
jobs. Confirm the uploaded artifact contains both XML files and JUnit accounts
for the whole passing suite. Final observed results belong on the delivery PR;
do not rerun an unchanged suite solely to update this note.

Use phase timings to choose one measured optimization later. Preserve fresh
per-test databases, crash/recovery coverage and production durability semantics.
Do not infer a speed improvement from one faster hosted run. After this checkpoint,
return to U4 acceptance; actual cohort proof and metric certification remain open.
