# Spec: observed-change data-fitness readout

Module ID: `change-acceptance-readout` (V1-08). Status: **owner approved F1–F3,
including implementation, on 2026-11-26 (Europe/Athens)**. Baseline: main `003680b` after #232, identical reviewed
`967d7ef` tree. Extends [A3](SPEC-dataset-acceptance.md#owner-decisions), after
citation/U1/U2/U3 consumers. Date: 2026-11-26 (Europe/Athens).

## Objective and assumptions

A company/market researcher can tell whether two stored captures support the
existing U4 observed-change comparison, or why comparison is blocked. Preserve
the [meaning of U4](../semantics/observed-change.md): a missing record is absent
from the later capture, not a deletion or legal event; different content does
not establish which field changed or why. No trend, fraud or market-coverage claim.

Assume one trusted local operator, Python 3.12+, PostgreSQL 17, the existing
restricted reader, private originals and explicit earlier/later run selections.
Keep the current policy, metric/SQL, source parsing and report bytes unchanged.
No new dependency, schema/grant, journal, CI change, source activation or release.

## Public preparation and command

Add `analytics.change_readout.prepare_change_result(dsn, request)` returning
frozen `PreparedChangeReadout(body, metric, cohort_json, earlier, later, pages)`.
`earlier`/`later` are the existing typed `Capture` values; `cohort_json` is the
canonical frozen cohort string or `None`, and `pages` the verified-page tuple.
Expose facts already obtained by the producer; do not widen its SQL projection.
Keep `prepare_change_readout` as a compatibility wrapper returning the original
`(body, MetricResult)`, preserving report/tuple bytes, errors and export behavior.

Keep one source repeatable-read snapshot: SQL run facts first; only if comparable,
read the cohort in that same snapshot and verify originals. Then check reference
SQL parity on the frozen inputs through the existing second read-only connection.
Preserve this sequence on both paths, including the preliminary comparability
evaluation; close both connections before publication. Prepare once per attempt.
No second cohort, source query, metric evaluation or independent selection algorithm
in the consumer. Original verification covers every admitted comparable page.

Proposed command, available only after implementation:

```sh
uv run --frozen python -m nima dataops assess-changes \
  --request /PRIVATE/change-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

Use environment-only `NIMA_DATABASE_URL`; no journal DSN/attempt ID. Decode the
existing `nima-observed-change-request-v1`, including programmatic inputs:
1–10 distinct runs in the union, disjoint captures, one archive binding per run.
One side may be empty: preserve its existing `no_runs` result. Both empty is an
invalid request. Keep the 16 KiB request bound and current comparable-cohort
500-observation/32-page/original-byte limits. Do not apply cohort preflight or
archive reads to the existing SQL-only abstention path.

All three command paths must be absolute/safe before SQL. Reuse descriptor-safe
private file guards: owned 0700/0600 directory/file, stable regular single-link
subject, no symlink traversal, lowercase SHA-256 `.json` basename. Subject bound:
**1 MiB**. Require hash/name and full bytes to equal the freshly prepared report.
Validate typed shapes and request/run/capture/cohort/page/observation/definition/
SQL/result bindings. A saved success flag is never verification.

## Comparable-path counters and accounting

When `cohort_json` exists, require verified originals, matching run facts and SQL
parity. Preserve the provider's page-observation clock for captured versions;
do not substitute another timestamp or invent a request cutoff.

Let E be the distinct union of both typed ambiguity lists. Let C be the distinct
union of source IDs in `added`, `changed`, `missing_from_later_capture` and
`unchanged`. Validate that category sets are pairwise disjoint, C excludes E,
category lengths match typed counts, and evidence binds every admitted version
to its declared capture/run/page/hash/pointer. All cohort observations are cited,
including older revisions and repeated observations, not just category witnesses.

Supply all six policy counts explicitly, including actual zeros:

| Counter | Grain | Mapping |
|---|---|---|
| `observations` | observation | Number of admitted cohort records, across both captures |
| `pages` | page | Number of admitted pages, matched to verified pages |
| `page_records` | reported_record | Sum of admitted page `record_count` |
| `quarantined` | quarantined_record | Sum of both captures' SQL run facts, reconciled with cohort runs |
| `selected_records` | source_record | `len(C)`, distinct comparison-eligible source IDs across both captures |
| `ambiguous_records` | source_record | `len(E)`, distinct source IDs ambiguous on either side |

Do not sum the two capture summaries to obtain `selected_records`, or add the
two ambiguity-list lengths. A source present on both sides counts once in C;
one ambiguous on both sides counts once in E. Ambiguity on either side excludes
that source from every category, including added/missing in the other capture.

The four category counts sum to `selected_records`. Each capture's unambiguous
summary equals its applicable categories plus its unambiguous sources excluded
because the opposite capture is ambiguous. Preserve repeated observations and
A→B→A without multiplying records. All-ambiguous captures may retain provider
status `no_observed_change` while assessment is `limited`; that status does not
establish unchanged underlying data. Genuine complete-empty captures still need
their verified empty pages; they can be `ready` without proving source absence.

Comparable reconstruction supplies all nine required checks, including
comparability. Use the existing policy's actual `ready`, `limited`, `blocked`
or `not_assessed` decision; monetary eligibility remains `not_applicable`.

## Incomparable-path contract

The existing producer deliberately returns no cohort, verified pages or evidence
when SQL run facts establish `incomparable`. Preserve that behavior, including
when originals are missing. Reconstruct and SQL-parity-check this exact abstention
report; never call a skipped verifier or claim raw-byte validation occurred.

Publish a `blocked` assessment with explicit `verification_scope: sql_comparability_only`:

- Keep `cohort_sha256: null`, `raw_bytes: not_performed_incomparable`, and all
  sorted native reasons. Use the first sorted reason for the policy's single
  failed comparability check; retain the complete reason list in the sidecar.
- Supply only the measured `quarantined` count from SQL run facts. The other five
  core counts are unavailable, not zero. Empty typed version/category arrays on
  this path are abstention output, not measurements of an empty capture.
- Set `bindings`, `evidence`, `keys`, `membership`, `page_accounting`, `selection`
  and `eligibility` explicitly `not_assessed/proof_unavailable`. No run-version
  profiles were read: the policy binding's run tuple is empty, never filled with
  current constants. Bind known earlier/later run UUIDs separately to the request.
- Set capture completeness from actual run facts: `failed/quarantined_records`
  when any quarantine exists; otherwise `failed/incomplete_capture` for missing
  sides or incomplete runs; otherwise `passed/ok` for query/time mismatch alone.

Known required-check failure takes precedence over unavailable proof under the
unchanged policy. This path diagnoses comparability; it certifies neither SQL/raw
agreement nor archive health. Missing SQL runs, denied access, SQL parity failure,
corrupt producer shapes or reconstruction failure yield a closed operation error
and **no sidecar**, rather than a fabricated negative assessment.

## Binding, output and privacy

Use unchanged `nima.dataset-acceptance` 1.0.0, `use="U4"`, policy hash
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
Metric `observed_change_between_captures.v1` stays draft, definition hash
`5ef663ebc1c297e9db184a5cfbf87afd2ea4c1231e1b2feb378cd082157cd2de`,
SQL hash `76cf61bd7285eea0c4834cb1439cd5a42c62903f80c7cff9e3f8017d481f259d`.
Preserve hash conventions, unsupported-binding decisions and all native statuses:
`incomparable`, `observed_changes`, `no_observed_change`.

New private canonical sidecar `nima-change-acceptance-v1`, at most **64 KiB**:
subject format/hash, request/cohort hashes, earlier/later run UUID roles,
verification scope, metric ID/status/definition/SQL hashes, full policy metadata/
hash and assessment/checks/counts/grains/limitations. Comparable scope is
`verified_two_capture_cohort`; include actual cohort run profiles only there.
For the policy's required UTC `cutoff`, use the maximum stored `observed_to` of
all selected run facts on either path, with `time_basis: stored_capture_end`.
This is a deterministic capture-end binding, not a user-selected cutoff or freshness.

Do not copy query text, source IDs, company/tax IDs/names, categories/version lists,
amounts, normalized records, credentials or physical paths. Detailed lineage and
capture facts remain in the bound parent report. Never promote metric status.

Reuse the current canonical encoder and atomic no-clobber publisher, fsync,
private permissions and identical-content retry. Every retry reconstructs; prior
publication is not a cached pass. Existing output can survive a failure and a
kill can leave a private temp file. Reuse the seven closed acceptance errors and
terminal vocabulary. Exit 0 for published `ready`/`limited`, 3 for published
`blocked`/`not_assessed`, 2 for input, 1 for other failures, 130 for interruption.

## Structure, style and verification

Add `src/nima/dataops/change_acceptance.py`; extend the existing acceptance CLI
and DataOps dispatcher. The only producer change is the additive preparation
result/wrapper in `analytics/change_readout.py`. No run-facts reader, verifier,
selection engine, generic adapter registry or journal refactor is needed.
Match existing frozen output records:

```python
@dataclass(frozen=True)
class ChangeAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str
```

After approval, use pytest (`tests/test_change_acceptance*.py`), owned native
PostgreSQL 17 fixtures, actual synthetic originals and restricted readers. Require
hand-computed category/counter answers, one-/both-side ambiguity, repeated
observations, A→B→A, multiple runs, all-ambiguous/complete-empty cases and every
abstention reason alone/together. Prove strict-time equality blocks comparison,
both paths use one fresh preparation/two closed read-only connections, incomplete
and mismatched captures do not read archives, and missing originals after a
positive publication refuse the next attempt. Preserve old tuples/report bytes.

Cover raw/SQL/projection/membership/principal failures, unavailable-proof honesty,
private paths, binding/shape drift, limits, all decisions, retry/relocation and
process interruption before/after the final link. No HTTP or input/SQL writes.
Require 100% new line/branch coverage, meaningful behavior mutations, unchanged
90% overall floor and all legacy semantic/SQL/ODCS/policy pins; prove the installed
wheel's real native command and all exact-head hosted jobs before merge readiness.

Implementation verification commands (not evidence this draft is implemented):

```sh
uv run --frozen pytest tests/test_change_acceptance.py
just lint
just typecheck
just security
just check
just audit
```

The contract probe exercised 15 pure synthetic model/policy cases, including
both-side ambiguity counting once, all-ambiguous limited/no-change, genuine empty
captures and blocked abstention with only quarantine measured. Its page/run facts
were controlled inputs: no SQL, archive, consumer or actual-data proof. Private
probe: `/workspace/work/nima-change-acceptance-contract-proof/probe.json`.

Always preserve unknowns/provenance and reconstruct before assessing. Scope
changes to schema, dependencies, CI, source access, policy/model rules or durable
history need separate review. Never repair evidence, infer deletion/legal events,
weaken checks, copy sensitive source detail, merge or deploy automatically.
V1-08 remains open for durable history and actual cohort reconciliation; metric
review/certification and investigator task proof are separate release gates.

## Owner decisions

- **F1 — scope (recommended):** additive frozen preparation result and one
  `assess-changes` consumer; preserve the existing two-path/two-connection sequence,
  tuple/report bytes and policy. Include implementation after contract approval.
- **F2 — meaning (recommended):** six comparable-path counts at the grains above;
  distinct cross-capture category/ambiguity unions; SQL-only blocked abstention
  preserves every reason and declares unmeasured counts/version profiles unavailable.
- **F3 — verification/privacy (recommended):** fresh reconstruction per retry,
  1 MiB subject/64 KiB sidecar, explicit capture-end binding, unchanged native
  verification/permission boundaries and the test/installed-wheel gates above.

Owner approved all three recommended decisions, including implementation. This approval
does not approve durable history, collection, certification, deployment or release.
