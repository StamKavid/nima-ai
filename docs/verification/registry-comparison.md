# Offline registry comparison: operator runbook and delivery evidence

RC1–RC5 are merged through #72 at main `c764dcb` (2026-11-15).
The command compares reported identifiers in selected stored evidence. It accepts
no company identity and makes no source request. A GEMI key is unnecessary here;
credentialed live-profile compatibility remains a separate pilot.

## Prepare the stored inputs

Use the tested Python 3.12/uv environment and PostgreSQL 17. Supply
`NIMA_DATABASE_URL` through environment settings; keep credentials out of command
arguments, terminal transcripts and Git. Database setup is explicit:

```bash
uv run --frozen python -m nima db migrate
uv run --frozen python -m nima identities compare --help
```

Migration is a separate setup action; comparison never migrates or writes SQL.
Choose an existing KIMDIS collection run UUID and finish projecting its accepted
observations. Run the bounded outbox consumer until the selected run's pending
observations have participation receipts/facts/mentions:

```bash
uv run --frozen python -m nima runs show KIMDIS_RUN_UUID
uv run --frozen python -m nima outbox project --max-events 100
```

Projection can process other pending runs too. Comparison fails visibly if the
selected run's projection is incomplete; it does not repair it or certify that
collection itself is complete. Inspect the run's original coverage separately.

Select 1–10 distinct UUIDs of existing completed GEMI imports. If a completed,
non-quarantined collector archive is available, import it explicitly first:

```bash
uv run --frozen python -m nima gemi import GEMI_RUN_UUID --archive-dir data/gemi
```

The GEMI collector run UUID is the stored import selector. The importer verifies
archived bodies; the comparison trusts that SQL import boundary and does not
rehash archives. See the [import contract](../sources/gemi-persistence.md).
Manually captured Publicity files cannot substitute for these normalized imports.
These commands do not fetch company data while waiting for an API key.

## Create and replay a private report

Replace UUID placeholders with your stored selectors. Repeat `--gemi-import` for
additional explicit imports; there is no implicit latest import or whole-registry
search. Choose a private output location, preferably outside the checkout:

```bash
uv run --frozen python -m nima identities compare KIMDIS_RUN_UUID \
  --gemi-import GEMI_IMPORT_UUID \
  --projection-version kimdis-participation-v1 \
  --output-dir data/registry-review --max-mentions 10000
```

| Bound | Behavior |
|---|---|
| Imports | 1–10 distinct stored UUIDs |
| Party occurrences | Requested `--max-mentions` in 1–10,000; an empty cohort is valid |
| Registry observations | At most 100 across the selected imports |
| Selected input/context | Conservative combined 8 MiB SQL preflight before label transfer |
| Canonical report | Exact 32 MiB encoding ceiling before publication |

All evidence/coverage comes from one repeatable-read, read-only transaction.
Supported versions, counts and terminal response/profile joins must reconcile.
SQL closes before filesystem publication. Bounds fail without truncation.

Stdout contains only run/import IDs, fixed statuses/version, counts, report SHA256
and `automatic_identity_links=0`. Names, AFMs, paths and driver messages stay out
of that summary. Find the private report at `<output-dir>/<report_sha256>.json`.
Directories/files are owner-only 0700/0600, and a `.gitignore` is published first.
Symlink traversal, Git internals, unsafe permissions and conflicting existing
artifacts are rejected. A hash does not anonymize the report contents.

Repeat the exact command to replay. Identical stored inputs and coverage produce
identical canonical bytes regardless of selector order. The publisher verifies
an existing artifact byte for byte and never overwrites a conflict. Changed
coverage/evidence produces a new hash; reports contain no generation timestamp.

A killed process may leave private `.tmp-*` files or an already complete final
artifact. Temporary files are not accepted reports. Retry through the normal CLI;
do not rename temporary files into place or delete conflicting evidence to make
replay succeed. Process-kill tests do not prove database-server, power-loss or
storage-device recovery. This publisher targets the tested Linux/POSIX filesystem.

## Interpret the report

`report_format=nima-registry-comparison-report-v1` and
`policy_version=registry-comparison-v1` distinguish it from `identities assess`.
The separate procurement assessment version is included as well.

| Per-occurrence outcome | Interpretation |
|---|---|
| `reported_identifier_agreement` | Eligible reported AFM text agrees with one or more selected found observations |
| `no_candidate_in_selected_imports` | Eligible party has no agreement in these selected imports |
| `unassessed_identifier` | Reported party identifier is ineligible or unknown under the existing policy |

Inspect `occurrences[].assessment` and `.comparison`; agreement references are
zero-based indices into the single `registry_observations` catalog. Every party
occurrence and selected registry observation is retained, including unmatched
rows, unchanged repeats and A→B→A observations. `registry_imports` records import
versions/times, manifest hashes and source attribution. `coverage` retains run
status, quarantine and unknown/empty supplier-list distinctions.

Original values/pointers and source, observation and import dates stay distinct.
Only ASCII space/tab/CR/LF are trimmed for comparison; leading zeros survive.
GR and EL remain separate procurement contexts. Buyer keys and names cannot
replace eligible tax identifiers. Nine ASCII digits do not establish issuer,
checksum or authority: those checks remain unknown/`not_checked`, and
`identity_status=unresolved` for every assessment.

Issues `multiple_registry_numbers_for_reported_afm` and
`reported_afm_changed_for_registry_number` expose contradictions without choosing
a winner. A 404 remains `not_found_at_observation`; it is not evidence of company
nonexistence, deletion or a negative identity match. Current registry claims do
not establish identity/status at a past contract date. `archive_integrity` remains
`not_checked`. Completion certifies bounded comparison of selected evidence,
not full collection, registry coverage, a verified identity or wrongdoing.

## Exit codes and recovery

| Exit | Fixed failure/status | Operator action |
|---|---|---|
| 0 | `complete`, including zero agreements | Inspect report and coverage privately |
| 2 | `configuration` | Correct selectors/options, mention bounds, projection version or database environment |
| 1 | `run_unavailable`, `registry_import_unavailable` | Select an existing stored run/import |
| 1 | `cohort_version`, `registry_version`, `registry_shape`, `registry_observation` | Inspect supported versions and stored evidence privately; do not patch history in place |
| 1 | `projection_incomplete`, `registry_incomplete` | Complete projection or investigate missing/count/join evidence; never silently drop rows |
| 1 | `comparison_limit`, `assessment_limit` | Select a smaller legitimate cohort/import set; no automatic truncation or scope change |
| 1 | `database_schema`, `database` | Check PostgreSQL/schema/connectivity in the private operator environment |
| 1 | `output_path`, `output_conflict`, `output_io` | Inspect ownership/permissions, path and existing bytes; retain conflicts for review |
| 130 | `interrupted` | Retry the same command and verify the resulting artifact |

`projection_version` is also a reused assessment error code; unsupported CLI
projection selectors are rejected as configuration before database reads. SIGKILL
cannot produce a graceful JSON/130 response; the replay checks cover that case.
Fixed public diagnostics deliberately omit raw values and private driver details.

## Measured delivery and limits

| Slice | Candidate and hosted run | Quality | Worker gate |
|---|---|---|---|
| RC1 | `db659cd`, [43642794825](https://github.com/StamKavid/nima-ai/actions/runs/43642794825) | 997 tests, 91.52% | 12 Docker tests, 833.40 s |
| RC2 | `21a5eb5`, [43643696440](https://github.com/StamKavid/nima-ai/actions/runs/43643696440) | 1,038 tests, 91.76% | 12 tests, 643.96 s |
| RC3 | `4418896`, [43647285400](https://github.com/StamKavid/nima-ai/actions/runs/43647285400) | 1,069 tests, 91.81% | 12 tests, 842.79 s |
| RC4 | `2f8971b`, [43647288882](https://github.com/StamKavid/nima-ai/actions/runs/43647288882) | 1,081 tests, 91.78% | 12 tests, 634.38 s |
| Main integration #71 | `b8767a3`, [43678995872](https://github.com/StamKavid/nima-ai/actions/runs/43678995872) | 1,081 tests, 91.86% | 12 tests, 632.95 s |
| RC5 #72 | `8c46f144e6ec2f889b56a8f76170e7c5dd9d07b6`, [43679268034](https://github.com/StamKavid/nima-ai/actions/runs/43679268034) | 1,106 tests, 91.82% | 12 tests, 648.64 s |

All three hosted jobs pass for those candidates: quality (including build,
security and dependency audit), Compose and the real Docker worker suite. Each
final worker verifier accepts one full 28-case controlled-fixture receipt; that
separate gate does not establish deployed internet egress or investigator IP
protection. #70 initially merged into its dependency branch; #71 integrated its
unchanged files into main before #72 merged. These are implementation results;
the documentation candidate's own checks are recorded in its delivery PR.

PostgreSQL cases prove the shared snapshot against concurrent commits, read-only
behavior, version/count/join checks, combined pre-transfer bounds and unchanged
source/outbox/archive state. Report cases cover stable bytes, coverage changes,
all-404 and empty cohorts, exact encoding bounds and unsafe publication paths.
All 23 CLI cases and both actual before/after-publication SIGKILL cases pass.

Mutation experiment: temporarily bypassing the procurement eligibility gate with
its raw comparison tax value caused 10 regression failures. Original policy bytes
were restored exactly (SHA256
`d13c01f2e2cde9e52748d4f7ef5969e903f9811e9c348b3b29743ce0e3c05006`),
then 63 focused policy/CLI tests passed and the full hosted suite passed. The
mutation and child pause interception are not production features.

The local executor had no configured PostgreSQL and insufficient Docker capacity;
local fixture setup failures were not reported as passing tests. Hosted PostgreSQL
and Docker provide the physical evidence above. No new test skip, suppression,
dependency, migration or CI exception was introduced for this increment.

Live GEMI compatibility, empirical false-match/false-merge quality, production
scale and investigator usefulness remain unmeasured. Reviewed reversible identity
decisions and a temporal graph require subsequent specifications and evaluation.
