# Repository controls and development commands

Updated 2026-11-14. Repository: public `StamKavid/nima-ai`, explicitly confirmed by
the owner after changing visibility. This supersedes the original private-hosting
policy. Source data, evidence archives, credentials and databases remain outside
Git. The account and commit identity remain StamKavid.

Historical setup: PRs #27–#29 are merged; main `242e9bb` passed hosted
quality/Compose run 43165010871. `dev` was created from that exact commit.

## Branch cleanup

The cleanup workflow runs after a same-repository PR merges, or on explicit
workflow dispatch. It sweeps merged PR metadata so a branch retained as an open
stack base can be removed after its dependent PR is resolved. Default behavior
for local execution is a read-only preview:

```bash
GITHUB_REPOSITORY=StamKavid/nima-ai sh scripts/cleanup-merged-branches.sh
GITHUB_REPOSITORY=StamKavid/nima-ai NIMA_CLEANUP_APPLY=1 sh scripts/cleanup-merged-branches.sh
```

Eligibility requires a merged PR from this repository, an unchanged head SHA,
GitHub's unprotected flag, and no open PR using the branch as head or base.
The default branch, main, dev, master and develop are always excluded. The final
Git deletion uses an explicit expected-SHA lease; newer commits cause rejection.
Unmerged, advanced, unknown or actively used heads are retained. Local branches
are preserved; only remote heads are deleted. The seven verified old merged heads
were cleaned during this increment; the exact metadata preview/results stay in
ignored local work evidence.

The workflow checks out trusted default-branch code with credential persistence
disabled. It never checks out PR code or interpolates PR text into shell code.
Only that job receives contents-write and pull-requests-read permissions. Its
metadata planner uses standard-library Python; GitHub CLI supplies authentication.
A failed metadata request or rejected lease stops the sweep visibly. CI skips
branch-deletion push events, while commit pushes and PRs retain every quality gate.

## Main/dev protection: prepared, not enforced

`.github/rulesets/main-dev.json` is an importable ruleset covering both branches:

- Pull requests, one independent approval, stale-approval dismissal and resolved threads.
- Passing `quality` and `orchestration-compose`, with the branch up to date.
- Blocked deletion and non-fast-forward pushes; no bypass actors.

The existing project policy already specified one approval. A sole author cannot
approve their own PR; an independent reviewer is required when this rule is enabled.
Do not silently lower that requirement to get a merge through.

Historical GitHub responses blocked activation while the repository was private:

- Reading private rulesets returned 403 with “Upgrade to GitHub Pro or make this
  repository public to enable this feature.”
- Creating the ruleset and changing `delete_branch_on_merge` returned 403
  “Resource not accessible by integration.” Account admin status does not grant
  this integration the corresponding settings permissions.

The owner has since made the repository public. Read-only verification on
2026-11-14 found active ruleset `protect-main` (ID 26812073), but its branch
include/exclude lists are empty and it contains only deletion and non-fast-forward
rules. `GET /rules/branches/main` and `/rules/branches/dev` both returned `[]`.
Neither branch has verified effective protection. The separate classic-protection
endpoint still returned integration HTTP 403; that does not override the effective
rules observations. No settings were changed during this verification.

Use an administration-capable GitHub session to configure the intended policy.
Import the JSON at Settings → Rules → Rulesets, or create once:

```bash
gh api -X POST repos/StamKavid/nima-ai/rulesets --input .github/rulesets/main-dev.json
```

Inspect existing rulesets first; update the existing ruleset by ID on later runs.
Verify active enforcement and each branch's rules afterward. A committed JSON
file or workflow does not enforce GitHub-side push/review protection. The cleanup
workflow excludes main/dev even while server-side protection is unavailable.
Use that workflow for cleanup; enable native automatic branch deletion only after
both long-lived branches are protected.

References: [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[Git expected-SHA leases](https://git-scm.com/docs/git-push#Documentation/git-push.txt---force-with-leaseltrefnamegtltexpectgt).

## just replaces make

Install checksum-pinned just 1.59.0, then use the original recipe names:

```bash
sh scripts/install-just.sh
export PATH="$PWD/.tools/bin:$PATH"
just setup
just check
just audit
just --list
```

The local installer supports Linux x86_64, matching CI and the existing secret
scanner installer. Other platforms can install just 1.59.0 from its official
release. `just GITLEAKS=/path/to/gitleaks check` preserves the executable override.
UV/PIP cache environment overrides remain supported. Dotenv loading is disabled.
Recipes keep the original frozen dependency, test, coverage, build, audit and
security commands. Historical verification reports retain the commands actually
executed at the time; current instructions and CI use just.

just runs developer/CI commands. Prefect still orchestrates data workflows, and
uv still manages Python dependencies and package builds.
[Official just manual](https://just.systems/man/en/).

## Why Python 3.12 today

3.12 was selected in the initial specification and subsequently pinned in the
image, type-check target and CI. The project has validated database, archive,
process-kill and Prefect recovery behavior on that baseline. The project minimum
is `>=3.12`; it is not an exclusive 3.12 constraint.

Pinned Prefect 3.9.2 declares Python `>=3.11,<3.16`, explicitly including 3.14.
No Prefect prohibition on 3.14 has been established. Python 3.14 receives bug fixes
and is supported through October 2030; 3.12 receives security fixes through
October 2028. Moving to 3.14 is a reasonable next runtime change after checking
the frozen dependencies, native wheels, SQLite/PostgreSQL behavior and the real
process/crash suite there, then updating the image digest and CI together.
This command-runner change preserves the tested runtime; no 3.14 test run is claimed.

Sources: [Python version lifecycle](https://devguide.python.org/versions/),
[Prefect 3.9.2 metadata](https://pypi.org/pypi/prefect/3.9.2/json).
