# Spec: supplier–buyer data-fitness readout

Module ID: `participation-acceptance-readout` (V1-08). Status: **owner approved
C1–C3 on 2026-11-26 (Europe/Athens), including implementation.** Baseline: merged
#225 at `e6c869d`. Extends [A3](SPEC-dataset-acceptance.md#owner-decisions) and the
[V1-08 work package](../roadmap/agent-backlog.md#v1-08--dataset-acceptance-and-comparability).
One consumer for U1; U2–U4 and durable history remain separate contracts.

## Objective and assumptions

A company researcher can inspect whether an existing supplier–buyer report
supports its declared captured-record use, with explicit unknowns, conflicts and
provenance. This supports the first business question: which public buyers appear
in captured KIMDIS records reporting the selected supplier? It neither certifies
the draft metric nor establishes market coverage, legal identity or paid spending.

Assume one trusted local operator, PostgreSQL 17, Python 3.12+, existing restricted
reader, explicit stored runs/cutoff and private original archives. No new source
request or deployment is required. Keep the existing metric, policy and legacy
report bytes unchanged; do not create another verifier or orchestration layer.

## Existing API and proposed command

`analytics.export.prepare_readout(dsn, request)` returns `PreparedReadout(body,
snapshot)`. It already owns the bounded SELECT-only repeatable-read SQL snapshot,
Python/SQL metric parity, projection validation, original-byte reconciliation and
existing output-contract validation. Its SQL connection closes before archive
reconciliation. Use the frozen snapshot it returns; do not open another connection
or rebuild the metric to assemble the assessment.

Approved command:

```sh
uv run --frozen python -m nima dataops assess-participation \
  --request /PRIVATE/readout-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

Use environment-only `NIMA_DATABASE_URL`; no journal DSN or attempt ID. Reuse the
existing `nima-participation-request-v1`: 1–10 runs, explicit UTC cutoff, `GR`,
reported tax-number selection and exactly one archive binding per run. Require
all three path arguments to be absolute and safe before SQL work; validate the
request through its public decoder before invoking preparation.

Inspect an owned private directory/file (0700/0600), no symlink traversal, regular
file, single hard link, stable metadata and lowercase SHA-256 `.json` basename.
The subject limit is **1 MiB**, U1's `MAX_RESULT_BYTES`; do not inherit the citation
report's 8 MiB limit. Preserve existing snapshot/page/original-byte bounds.

Call `prepare_readout` **exactly once per invocation**, including retries. Require
the inspected bytes' hash to match their basename and complete byte equality with
the fresh report. Decode only fresh metadata and the returned frozen snapshot;
selection facts come from its typed `MetricResult`. Saved success flags never
establish verification. Validate producer shapes/types, run membership, request,
snapshot, typed/serialized result and definition/SQL bindings before evaluation.
No new collection, projection drain, repair, second snapshot or normalizer.

## Frozen policy and counter mapping

Use unchanged `nima.dataset-acceptance` 1.0.0 with `use="U1"`, policy hash:

```text
f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06
```

The current U1 definition is `captured_contract_record_count.v1`, draft, hash
`7d8b5f8ecf6ae366482f4b06cd245f16d23408b489ad9bcb44af493282ac043f`;
SQL hash `85134c5d800350adfedf7dce6d995a36c48b194d919912695992f83369e11d5f`.
Retain the producer's definition-hashing convention. Unknown policy metadata is a
contract failure; a structurally supported verified producer definition not
admitted by the policy can receive its explicit `not_assessed` result.

Let `D = prepared.snapshot.metric`, `S` be the decoded frozen snapshot and `C` be
members of `D.records` with `ambiguous == False`. These are selected source IDs
at the cutoff, before supplier filtering. Reconcile the ambiguous ID list with
the typed decisions; never choose a tied version. Every required counter is
measured explicitly, including zeros. No fixture template or missing-key default.

| Counter | Grain | Mapping |
|---|---|---|
| `observations` | observation | `len(prepared.snapshot.observations)` across all admitted pages, including after-cutoff observations |
| `pages` | page | `len(S["pages"])` |
| `page_records` | reported_record | Sum of admitted pages' `record_count` |
| `quarantined` | quarantined_record | Sum of admitted runs' `quarantine_count`; measured, never a hardcoded zero |
| `selected_records` | source_record | `len(C)` |
| `ambiguous_records` | source_record | `len(D.ambiguous_source_ids)` |
| `unknown_suppliers` | source_record | Number of records in C where `unknown_suppliers or unassessed` is true: unknown supplier list or unresolved country eligibility for the selected tax number |
| `unassigned_buyers` | source_record | `len(D.unassigned_source_ids)`: matching supplier records with unknown buyer |
| `invalid_supplier_occurrences` | supplier_occurrence | `D.invalid_supplier_count`, including occurrences in selected ambiguous candidate versions as defined by the provider |
| `unknown_cancellations` | source_record | `D.unknown_cancellation_count`, among matching supplier records |
| `cancelled_records` | source_record | `D.cancelled_count`, among matching supplier records |

Exactly eleven counters are required by this mapping. Different grains and
unknown buckets overlap; they are not a partition to add together. Re-observation
and duplicate matching supplier ordinals do not multiply distinct-record counts.
A known empty supplier list is not unknown. For U1 this counter measures unresolved
reported-supplier eligibility: union the two typed flags once per record, rather
than summing their possibly overlapping lists. The original report retains their
separate detailed buckets. Invalid supplier occurrences are not
distinct suppliers or source records and need not be bounded by `len(C)`.

**Ambiguity matters:** `D.unknown_supplier_source_ids` can include ambiguous
records. Counting that entire list against the unambiguous denominator can turn
an otherwise valid all-ambiguous cohort into a false eligibility failure. Count
unresolved supplier eligibility only in C; retain ambiguous records in their
separate bucket.
An existing-provider/policy probe with two tied unknown-supplier versions gives
`selected_records=0`, `ambiguous_records=1`, `unknown_suppliers=0` and `limited`.
The naive list-length mapping incorrectly yields `blocked`. This is a contract
probe, not evidence verification or an implemented consumer.

All nine check IDs remain explicit. Successful reconstruction establishes
bindings, evidence, keys, membership, page accounting, capture completeness,
selection and eligibility. Comparability is `not_applicable/not_required_for_use`.
The unchanged pure evaluator retains authority over its own invariants/decisions.

## Completeness and negative results

The existing U1 preparation boundary requires complete managed, quarantine-free
runs, every selected page and reconciled projections. Partial/quarantined/no-page
runs fail that boundary. Return a closed failure with **no sidecar**, rather than
fabricating verified facts to publish a `blocked` assessment. A complete-empty
capture still requires its archived empty page.

Publish any of the four policy decisions only after successful reconstruction.
`ready` and `limited` describe data fitness for this use, not certification or a
numeric claim's truth. Always retain `provider_status`: `selection_unresolved`,
`no_observations_before_cutoff`, `empty_capture` and `no_observed_participation`
are distinct. An eligible tax number with unresolved supplier country yields
`selection_unresolved`; its unambiguous record contributes once to
`unknown_suppliers`, so the unchanged policy returns `limited`. Using only the
unknown-list bucket would incorrectly hide this limitation. No status is relabelled
as zero market activity; even `ready` with an empty/no-observed provider status
establishes no actual market absence. No new policy version or hidden status
override is introduced here. Monetary eligibility remains `not_applicable`.

Map `analytics_input` to `acceptance_input`, `analytics_limit` to
`acceptance_limit`; archive/coverage/projection/evidence failures to
`acceptance_evidence`; role/schema/database failures to `acceptance_database`;
version/metric/contract or unknown producer failures to `acceptance_contract`;
publication/output failures to `acceptance_output`. Interruption is
`acceptance_interrupted`. Never echo arbitrary exceptions or source values.

## Private result and compatibility

New canonical sidecar `nima-participation-acceptance-v1`, at most 64 KiB UTF-8.
Bind subject version/hash, request hash, explicit cutoff, source/run profiles,
metric ID/status/definition/SQL hashes and the original `snapshot_sha256`.
Use that same snapshot hash in the policy binding's generic `cohort_sha256` slot;
do not invent or recompute a different cohort identity.

Embed complete policy metadata/hash and the assessment's checks, required checks,
counters/grains, limitations, provider status and bound identities. Validate output
shape, closed vocabularies and cross-field bindings before publication.

**Do not copy the semantic request wholesale:** U1's request contains the supplier
tax number. Bind it through `request_sha256` while exposing only cutoff/run/source
metadata. Do not repeat tax IDs, buyer keys, company names, normalized records,
subjects, amounts or physical archive paths. Detailed results/evidence stay in the
existing private report. The sidecar also stays private; it is not anonymization.

Reuse the existing bounded canonical encoder and atomic no-clobber publisher,
0700/0600, fsync and identical-content retry checks. Every retry reconstructs;
a previous output is never a cached pass. SQL/archive inspection and publication
are not one atomic transaction. A completed artifact may survive a later failure;
a process kill may leave a private temporary file. Conflicting final bytes fail.

Stdout contains fixed status, subject/sidecar/policy hashes and decision; stderr
fixed stage events. Exit 0 for published `ready`/`limited`; 3 for published
`blocked`/`not_assessed`; 2 for input; 1 for operational/evidence/contract/size/output
failure; 130 for interruption. No report, request or source evidence is modified.

## Structure, style and verification

Proposed adapter `src/nima/dataops/participation_acceptance.py`, routed through the
existing DataOps dispatcher/acceptance CLI. Use frozen return records like the
citation consumer. A small shared subject-file guard may be extracted into a
public internal helper with a per-call byte bound and fixed errors. Preserve the
citation API, valid-command outputs and artifact bytes; avoid cross-module private
imports, a generic adapter registry or another publication implementation.

```python
@dataclass(frozen=True)
class ParticipationAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str
```

Implementation verification after approval:

```sh
uv run --frozen pytest tests/test_participation_acceptance.py
just lint
just typecheck
just security
just check
just audit
```

Require hand-computed answers for all eleven counters, tied unknown-supplier
versions, known-empty versus unknown lists, A→B→A, repeated observations, duplicate
matching ordinals/joint records, invalid occurrences, unknown country/buyer,
cancellation and after-cutoff evidence. Keep unresolved/empty statuses explicit.

Use owned PostgreSQL 17 fixtures and actual originals with the restricted reader:
complete/empty success, partial/quarantine/projection/page/SQL/raw refusal, exactly
one preparation call/connection, retry/relocation identity and unchanged input/SQL
state. Prohibit HTTP on success and failure. Cover relative paths, symlinks/hard
links, hash/body/binding drift, both subject byte limits, exact output bound,
policy drift, all decisions and private CLI failures. Test process interruption
before/after final publication, no open source SQL at that boundary, meaningful
mutations, 100% new-code line/branch, unchanged 90% overall floor, legacy pins,
installed-wheel operation, full gates and exact-head hosted jobs.

No dependency, CI, policy/semantic rule, schema/grant, journal, source activation,
metric review/certification or release change. Real investigator/cohort validation
remains open. Synthetic verification cannot close that product gate.

## Owner decisions

Owner approved all three recommended decisions on 2026-11-26 (Europe/Athens):

- **C1 — scope:** U1 supplier–buyer acceptance first, through one command/sidecar;
  leave U2–U4 and durable history separate.
- **C2 — meaning and privacy:** Adopt the eleven explicit grains/mappings, including
  unambiguous-only list/country eligibility unknowns, preserve provider status, and hash-bind the
  private supplier selection without repeating its tax number.
- **C3 — verification and reuse:** One fresh existing preparation per invocation,
  strict 1 MiB subject/64 KiB sidecar bounds, shared small file guards with citation
  compatibility, and no assessment on failed reconstruction.

Execute the approved bounded consumer under `tasks/plan.md` and `tasks/todo.md`.
The earlier citation correction remains separately approved; no U2–U4 consumer,
journal evolution, source activation or metric certification follows from C1–C3.

Contract #227 and prerequisite #226 are merged at `e3839c0`/`fcfa11d`.
Implemented in a separate consumer candidate; see the [runbook](../runbooks/participation-acceptance.md)
and [local verification record](../verification/participation-acceptance-readout.md).
Post-push gates and main-delivery state are tracked on the PR.
