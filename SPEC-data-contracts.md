# Spec: first machine-readable analytics contract

## Objective and authorization

The owner requested continued implementation after the data-contract proposal on
2026-11-18. Extend the existing semantic-layer/market-analytics boundary with one
offline ODCS contract. This is a thin extension of the approved capability map,
not a new orchestration platform. Preserve all pending pipeline and human tasks.

The first output is the existing `nima-supplier-buyers-v1` private artifact. Nima
owns its guarantees; it cannot promise government-source accuracy, availability
or national coverage. The metric remains draft. Source-acceptance and normalized
dataset contracts follow after this output boundary is proved.

## Contract and implementation

- Pin official ODCS 3.2.0 JSON Schema, upstream commit and SHA-256, with its
  Apache-2.0 license. Package it locally; validation never retrieves references.
- Package a reviewable JSON contract (JSON is also valid YAML). Record Nima
  ownership, use/coverage limits, output fields, quality-check references and
  the existing semantic definition. The latter is a reviewed snapshot compared
  with `nima.semantics.participation.definition()`, not a second calculation.
- Declare the supported Nima profile: string/integer/number/boolean/object/array,
  required/nullability, enum, nested properties/items, and the explicit supported
  logical options. Fail unsupported constructs instead of silently ignoring them.
- Validate the actual output against that shape after original reconciliation
  and before private publication. Refuse metadata/semantic/shape mismatches with
  `analytics_contract`; preserve previous artifacts, source rows and originals.
- Keep every existing successful report byte unchanged. Contract validation does
  not make a draft metric certified, nor add a release/validation-result registry.
- Provide conservative compatibility comparison: removals, existing field shape,
  grain/semantic/quality/terms changes require a major version; optional added
  fields require a minor; descriptive-only edits require a patch. Changed content
  cannot reuse a version and versions cannot go backwards. A major bump still
  needs a separately versioned consumer interface and review before activation.

## Structure and commands

`src/nima/contracts/`: contract, local schema/license, loader/profile validation
and compatibility policy. `tests/test_data_contracts*.py`: metadata, compatibility
and real publication tests. `docs/semantics/data-contracts.md`: operational scope,
upstream provenance and reproduction. No new service, migration or source request.

```sh
uv run --frozen pytest tests/test_data_contracts.py
uv run --frozen pytest tests/test_data_contracts_publication.py
just check
just audit
```

Use the existing Python 3.12, immutable values, fixed failures and strict mypy
conventions. Declare jsonschema 4.26.0 directly (already in the locked runtime
through Prefect); add its typing stubs to development dependencies. Review the
lock/export changes; do not upgrade unrelated packages or change CI policy.

## Acceptance and boundaries

1. Official-schema validation and installed-wheel resource loading work offline.
2. Current metric/SQL definition matches the reviewed contract; changing its
   revision rule or SQL hash fails without intentional contract evolution.
3. Real readout passes; removed required field/wrong type/negative count fail;
   existing duplicate-grain, missing-evidence and bad-projection guards still
   prevent publication. Existing report bytes and private data remain unchanged.
4. Compatibility tests cover same-version edits, backwards versions, optional
   additions, field removal/type/nullability changes and semantic changes.
5. A meaningful disabled-guard mutation fails its regression; complete local
   gates/audit and actual final-head hosted results precede handoff.

Always preserve original evidence and consumer semantics. Never execute code,
SQL or links from contract metadata. No scheduled monitoring, alerts, automatic
certification, universal ODCS execution, source refresh or live pilot deployment.
Historical PR-baseline automation and durable contract-check history are later
increments; passing policy tests alone is not that automation.

## Checkpoint C9: source acceptance and normalized KIMDIS records

The owner merged #137 (`9cd4c8a`) and requested this next slice on 2026-11-18.
Extend the same capability, preserving earlier contracts and pending work.

1. Extract the source-neutral ODCS/profile/compatibility implementation into
   `nima.contracts.schema`. Preserve C8 public APIs, report bytes and failure
   behavior. Importing schema support must not load analytics/semantics/storage.
2. Add two draft ODCS 3.2.0 documents: Nima's minimum decoded-page acceptance
   boundary and its normalized contract-record guarantee. Government availability,
   source truth, national completeness and freshness are never promised.
3. Explicit profile additions: `nima.opaqueItems: true` permits an array with
   unconstrained items, needed to preserve per-record quarantine; `nima.present:
   true` requires a nullable property to exist. These are ODCS custom properties,
   not silently ignored constraints. Other unsupported constructs still fail.
4. Keep strict JSON/Decimal decoding and existing pagination checks authoritative.
   Check the source contract after those checks. Unknown fields remain in the
   original bytes/fingerprint, and malformed record items retain existing issues.
5. Validate each successfully normalized record before it can enter a Page or
   leave `normalize_contract`. Money remains finite Decimal in the model and exact
   text in the validation view, nullable fields are present, suppliers preserve
   missing versus empty, references retain stage/namespace, and evidence must
   match the independently known raw digest and record index. A normalizer output
   defect stops the page; it must not be labelled as a source quarantine issue.
6. Cache only immutable packaged contract validators per process. No network,
   arbitrary SQL/code execution or mutable consumer policy. Move the unchanged
   normalizer-version constant to the source boundary, preserving storage's
   existing public alias and every saved version/hash/request.

Acceptance: focused source/profile tests prove compatibility, exact Decimal and
Greek/identifier/unknown handling, metadata/binding refusal, quarantine retention
and fatal bad producer output. Real SQL proves that a rejected page retains raw
bytes while checkpoint, observations, quarantine and outbox remain unchanged.
Existing replay/readout bytes must reproduce through the packaged wheel on the
selected private pilot. Meaningful guard mutation, full local gates/audit and
final-head hosted checks precede owner review. Use the existing commands and
quality floor; no new dependency, migration, live source request or deployment.
Historical PR comparison and durable check history remain later.

### Measured CI budget exception

On unchanged head `7d7da93`, push run 44364797668 passes all jobs, including
2,397 tests in 408.01 seconds and the audit. PR run 44365266941 attempts 1 and 2
both reach the final workflow tests and are cancelled at the ten-minute job
limit. Increase only `quality.timeout-minutes` from 10 to 15 for setup, runner
variation and the complete gate. This is an explicit CI configuration change for
owner review under CONSTRAINTS.md. Preserve every command, assertion, coverage
threshold, pinned action/image, permission, fixture job and audit. The bound stays
finite. New-head hosted verification is required; application-source byte equality
allows reuse of the complete local application verification and packaged proof.

## Checkpoint C10: committed historical compatibility gate

The owner merged #138 at `9d29845` and requested automatic historical comparison.
Compare the flat `src/nima/contracts/*.odcs.json` catalogue in two immutable Git
commits using the existing ODCS/profile and conservative SemVer checker. Read Git
tree/blob objects, never the working tree, old Python code or contract links.

- Require full lowercase 40-character SHA-1 commit IDs and an ancestor baseline.
  Missing Git history, empty candidate catalogue, duplicate IDs, non-regular
  descriptor files, invalid JSON/ODCS or removed identities fail closed.
- One current descriptor per contract ID. A file rename retaining its ID is
  harmless; a removed/replaced ID cannot masquerade as a new contract. Validate
  additions and compare every retained identity. An empty baseline permits first
  registration. Parallel major-version catalogue lifecycle remains later work.
- Reject descriptors over 256 KiB, more than 64 contracts and tree listings over
  64 KiB; Git calls have a ten-second timeout. Strict JSON rejects duplicate keys
  and non-finite values. Output contains commit IDs, fixed reasons and counts;
  descriptor/source values, Git stderr, paths and private evidence are not printed.
- CLI: `uv run --frozen python scripts/check_contracts.py --base SHA --head SHA`
  (optional `--repo PATH`), also `just contracts-check BASE HEAD`.
- CI mode `--ci`: PRs use the provider's base SHA from a step environment value;
  existing-branch pushes use the provider's `before`; new-branch pushes and manual
  dispatch use the local merge-base with fixed `origin/main`. HEAD is resolved
  once to a commit. Missing event/ref context is an error, not a skipped check.
- Only quality checkout fetches full history (`fetch-depth: 0`), retaining the
  pinned action and `persist-credentials: false`. An additional comparison step
  precedes the complete existing gate. Event values enter through environment
  arguments, never interpolation in shell code. Keep all jobs, permissions,
  assertions, audit, pins and the approved fifteen-minute quality bound.

Implement in `scripts/check_contracts.py`, real disposable Git tests in
`tests/test_contract_baselines.py`, and the narrow workflow/justfile additions.
Source-neutral schema code remains authoritative. No source/normalizer/semantic
definition, source request, dependency, database migration or deployment changes.

Acceptance: actual Git histories prove unchanged/patch/minor/major/new-ID cases;
unversioned edits, insufficient bumps, removals, duplicate IDs, symlinks, corrupt
JSON, oversized data, unavailable/divergent history and dirty-tree bypasses fail.
Actual CLI/CI-mode executions prove PR/push/new-branch/manual baseline selection
and fixed failures, and have no network/database access. A removed-identity guard
mutation must fail its regression. Verify the real main-to-feature catalogue,
full local gates/audit and final-head hosted jobs before owner review. This checks
interface metadata evolution; it does not certify live data or persist check
history. Effective branch protection remains separately documented, not implied.

Security review note for C10: the Git reader resolves the installed Git executable
to an absolute path and uses fixed subcommands, separately passed argv, validated
object IDs, no shell, no replacement objects and no lazy fetch. Scoped Bandit
B404/B603 annotations cover that necessary local subprocess boundary, following
the existing fixture-controller pattern. No global exclusion or severity change;
all other findings fail the unchanged security gate. Review these annotations
with the PR. The operator's tooling installation/PATH remains trusted.
