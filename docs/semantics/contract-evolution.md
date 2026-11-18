# Committed data-contract evolution

CI compares the ODCS catalogue in two immutable Git commits using the current
[compatibility policy](data-contracts.md#evolution-and-verification). This checks
interface metadata evolution. It does not certify government accuracy, live data,
freshness, a metric or a dataset. All three current contracts remain draft.

The checker reads Git tree/blob objects from the flat
`src/nima/contracts/*.odcs.json` catalogue. It never imports historical Python,
follows contract URLs, reads source evidence or uses a dirty descriptor file as
the comparison input. A file rename retaining its ID is allowed. Every retained
ID is compared; additions must be valid. Removed/replaced IDs, duplicate IDs,
invalid metadata and an empty candidate fail. An empty baseline permits first
registration. There is one active descriptor per ID; parallel major-version
catalogues and contract retirement need a separately reviewed lifecycle policy.

## Baseline selection

| Invocation | Baseline | Candidate |
|---|---|---|
| Pull request | GitHub event `pull_request.base.sha` | Checked-out HEAD, normally the synthetic merge commit |
| Existing-branch push | GitHub event `before` | Checked-out HEAD |
| New-branch push (`before` is forty zeroes) | Local merge-base with `refs/remotes/origin/main` | Checked-out HEAD |
| Manual workflow dispatch | Local merge-base with `refs/remotes/origin/main` | Checked-out HEAD |
| Explicit local command | Required `--base` full SHA | Required `--head` full SHA |

Event values enter through step environment variables, not shell interpolation.
HEAD is resolved once. Missing/unsupported context, unavailable commits and
non-ancestor baselines fail; no comparison is silently skipped. A branch with
divergent push history needs an explicit review rather than a guessed baseline.
The quality job alone uses checkout `fetch-depth: 0`; the action remains pinned,
credentials are not persisted and all other CI jobs/gates remain present.

Run a local comparison after fetching the intended history:

```sh
just contracts-check "$(git rev-parse origin/main)" "$(git rev-parse HEAD)"
```

Both arguments must be lowercase full forty-character SHA-1 commit IDs. The
baseline must be an ancestor of the candidate. For another local repository:

```sh
uv run --frozen python scripts/check_contracts.py --repo /path/to/repository \
  --base BASE_COMMIT_SHA --head HEAD_COMMIT_SHA
```

The checker itself does not fetch. Shallow history must contain the actual
baseline and ancestry; partial/promisor clone configurations are refused before
history reads to prevent implicit object fetches. For normal full clones, fetch
missing history explicitly, inspect it, then rerun. Failed metadata must be fixed
and versioned against the selected baseline; the checker offers no bypass flag.

## Outputs, limits and verification

Success prints one JSON object with `status: passed`, checker version, commit IDs
and total/compared/added/unchanged/patch/minor/major counts. Failure prints only a
fixed reason, never descriptor values, paths or Git stderr. Exit codes are 0 for
success, 1 for history/metadata/compatibility failures and 2 for configuration.
`--help` has conventional CLI help behavior.

The catalogue is limited to 64 regular descriptor files, 256 KiB per descriptor
and 64 KiB per Git tree listing. Filenames use lowercase ASCII letters, digits
and hyphens. Symlinks and non-regular entries are refused. Strict JSON rejects
duplicate keys and non-finite numbers. Each Git call has a ten-second timeout;
blob size is checked before reading content. These are input/operation limits,
not an OS-enforced whole-process memory or runtime quota.

```sh
uv run --frozen pytest tests/test_contract_baselines.py tests/test_contract_baselines_cli.py
```

Tests create actual disposable histories and execute the real CLI. They cover
version changes, renames, additions, removal/replacement, invalid metadata,
dirty-file bypass attempts, insufficient history and provider baseline selection.
The existing full quality gate still runs independently. A failing CI check does
not establish effective GitHub branch protection; see
[remote controls](../../CONSTRAINTS.md#remote-controls).

Durable per-dataset check history and scheduled monitoring remain later work.
A major metadata bump does not authorize changing an output interface, migrating
a database or activating a source.

Implementation references: [checkout history](https://github.com/actions/checkout#fetch-all-history-for-all-tags-and-branches),
[GitHub event context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#github-context),
[git ls-tree](https://git-scm.com/docs/git-ls-tree) and
[git cat-file](https://git-scm.com/docs/git-cat-file).
