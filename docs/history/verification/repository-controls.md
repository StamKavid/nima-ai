# Repository controls and just verification

Date: 2026-11-12. Base: merged refresh release `242e9bb` on main. User authorization
covers merged-branch cleanup, main/dev protection configuration and make → just.
The application runtime and data workflow behavior are unchanged.

- Installed official just 1.59.0 in ignored `.tools/bin` after verifying the release
  archive SHA-256. Every previous recipe and quality/security/audit command was
  ported; the Makefile was removed. CI and current contributor/spec instructions
  now use just. Archived reports and the immutable skill snapshot retain history.
- `just check` passed: **486 tests**, **92.53%** combined line/branch coverage,
  strict typing, formatting/lint, skill integrity, package builds, Bandit and
  redacted Gitleaks. `just audit` reported no known dependency advisories.
- Seventeen additional cleanup tests cover merged/unmerged and foreign heads,
  default/main/dev protection, current versus advanced SHA, protected/unknown
  protection metadata, open head/base dependencies, paginated/malformed/missing
  metadata, and actual deletion against a local bare Git repository.
- Real Git tests prove an expected-SHA lease rejects deletion after a newer commit,
  and main is retained. Mutation of the merged-head SHA comparison failed the
  advanced-head regression; the original source was restored byte-for-byte.
- Previewed and deleted seven matching merged remote heads using the same guarded
  executor. Re-read GitHub's branches afterward: main/dev and eight total remaining
  remote heads were present. Local branches were preserved. A preceding metadata
  request failure stopped before mutations, exercising the fail-closed path.
- Created dev at main `242e9bb`. Both baseline branches passed hosted CI (main
  43165010871, dev 43166465554). Final change-head runs are recorded in the PRs.
- Actionlint and POSIX shell syntax checks passed. No provider request, poller,
  source record, GitHub billing change, paid subscription or production deployment.

The cleanup workflow activates after its reviewed merge to the default branch.
It executes trusted default-branch code only, scopes token permissions to the
cleanup job, and checks source metadata before an atomic expected-SHA deletion.
It also sweeps older eligible heads, allowing deferred stack bases to be cleaned
on a later merge. Active open PR dependencies and new commits are retained.

GitHub-side protection was **not enabled**. Reading private rulesets returned a
Pro-plan requirement; creating rulesets/changing native deletion returned an
integration-administration 403. Repository visibility remains private. The ruleset
payload and manual activation/verification steps are in docs/repository-settings.md.
A JSON file and cleanup exclusions are not server-side push protection.

Review: command-runner migration preserves all gates, operational Python is kept
separate from application code, metadata inputs fail closed, and no PR code is
executed in the write-permission workflow. Readable small scripts replace an
unreviewable privileged inline payload. API history is bounded by a 4 MiB input
limit and job timeout; oversized/failed metadata retains branches and fails visibly.
Future users should inspect the plan before manual application. No automatic
merge or change to the existing independent-review requirement was introduced.
