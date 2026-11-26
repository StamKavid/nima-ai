# Spec: CPV/month data-fitness readout

Module ID: `cpv-acceptance-readout` (V1-08). Status: **owner approved D1–D3,
including implementation, on 2026-11-26 (Europe/Athens)**. Baseline: #228 merged at `e6f48b4`.
Extends [A3](SPEC-dataset-acceptance.md#owner-decisions) after the citation and U1
consumers. This contract covers U2 only.

## Objective and assumptions

A market researcher can assess the fitness of an existing CPV/month captured-record
report, including unknown dates/classification, ambiguous revisions and cancellations.
CPV describes reported procurement objects; it is neither a company's KAD sector
nor evidence of market share. The metric remains draft and the taxonomy unchecked.
Counts describe captured contract-publication records, not spend, awards or payments.

Assume one trusted local operator, Python 3.12+, PostgreSQL 17, the existing
restricted reader, explicit runs/cutoff and private original archives. Reuse the
unchanged metric, reference SQL, policy, file guards and publisher. No new data
source, dependency, schema, journal, CI configuration or orchestration layer.

## Preparation boundary and command

Existing `analytics.cpv_readout.prepare_cpv_readout(dsn, request)` returns only
`(body, MetricResult)`. It reads one bounded SQL cohort, verifies original pages,
re-extracts CPV assertions, evaluates U2 and checks reference-SQL parity. The saved
report omits run profiles and quarantine counts, so those facts cannot be recovered
from its JSON or replaced by assumed zeros.

Propose an additive public `prepare_cpv_result(dsn, request)` returning a frozen
`PreparedCpvReadout` with `body`, `metric`, `cohort_json`, `observations` and `pages`.
Serialize the already-read cohort canonically; retain the existing typed CPV
observations and verified pages. Keep `prepare_cpv_readout` as a compatibility
wrapper returning its original tuple. Move the existing preparation sequence once;
do not copy it or add a second verifier. Existing CLI, report bytes, errors and
reference-SQL inputs remain unchanged.

The existing sequence has **two sequential read-only connections**: one
repeatable-read source-cohort read, then reference SQL over bound frozen JSON rows.
The second query does not re-read source tables. Preserve that behavior: exactly
one preparation and one source-cohort read per invocation, including retries.
Both connections close before sidecar publication. Do not claim a single shared
SQL transaction across archive verification and publication.

Proposed command, available only after implementation:

```sh
uv run --frozen python -m nima dataops assess-cpv \
  --request /PRIVATE/cpv-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

Use environment-only `NIMA_DATABASE_URL`; no journal DSN or attempt ID. Decode
the existing `nima-cpv-period-request-v1`, including programmatically supplied
requests: 1–10 runs, UTC observation cutoff, optional eight-digit CPV base code,
optional inclusive first/last reported month, and one archive binding per run.
Require all three paths to be absolute and safe before SQL work.

Reuse `dataops.acceptance_files`: owned private directories/files (0700/0600),
descriptor-safe stable single-link reads, no symlink traversal and lowercase
SHA-256 `.json` report basename. The report bound is **1 MiB**, matching the
existing U2 encoder. Preserve the existing cohort/page/original-byte bounds.
Require the saved body's hash to match its name and complete byte equality with
the fresh producer body. Saved success flags never establish verification.

Validate fresh producer types/shapes, run/page/observation membership, request,
cohort hash, typed/serialized result, definition/SQL bindings and CPV/date/cancellation
diagnostic consistency before policy evaluation. Do not import private producer
functions, re-read SQL facts or re-run extraction/evaluation in the acceptance adapter.

## Frozen policy and counters

Use unchanged `nima.dataset-acceptance` 1.0.0, `use="U2"`, policy SHA-256:
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
Metric: `captured_record_count_by_cpv_period.v1`, draft, definition SHA-256
`577d91161d92e5a954d773427762fc4d7060b537a0300f4f54ecdac0002f132d`;
SQL SHA-256 `7d9e7cb716e4184daf3601df7bd75a8064a8fe9a984880f73126cc5a714218e0`.
Preserve the existing semantic hash convention and public policy metadata.
Unknown policy metadata fails the contract; a supported verified producer shape
with a definition outside the policy receives its explicit `not_assessed` result.

Let `S` be the decoded frozen cohort, `D = prepared.metric`, and `C` the members
of `D.records` with `ambiguous == False`. C contains distinct latest-selected
source records at the cutoff **before CPV/month filtering**. Measure all ten
required counters, including zeros; reconcile typed lists and coverage fields.

| Counter | Grain | Mapping |
|---|---|---|
| `observations` | observation | `len(prepared.observations)`, all admitted observations including after cutoff |
| `pages` | page | `len(S["pages"])`, reconciled with verified pages |
| `page_records` | reported_record | Sum of admitted page `record_count` |
| `quarantined` | quarantined_record | Sum of admitted run `quarantine_count`; never a literal assumed zero |
| `selected_records` | source_record | `len(C)`, equal to `D.coverage.selected_records` |
| `ambiguous_records` | source_record | `len(D.ambiguous_source_ids)`, reconciled with ambiguous decisions |
| `unknown_dates` | source_record | `D.coverage.period_absent + D.coverage.period_unparseable`, reconciled with C |
| `unclassified_cpv` | source_record | `D.coverage.unclassified_no_reported_code + D.coverage.unclassified_metadata_unavailable`, reconciled with C |
| `unknown_cancellations` | source_record | Number of C records whose `cancelled is None` |
| `cancelled_records` | source_record | Number of C records whose `cancelled is True` |

Classification buckets partition C; parsed/absent/unparseable date buckets also
partition C. Unknown date, unclassified and cancellation buckets overlap one
another. Ambiguous records remain separate; never choose a tied version. Neither
cell counts nor cell cancellation counts are distinct-record denominators.
Filters change cells/period totals, not these existing coverage/diagnostic scopes.
Retain this cohort-wide scope explicitly, even if no cells match the selection.

A probe of the existing pure provider/policy used eight synthetic observations:
four unambiguous records, one tied record, one future-only record and one repeated
observation. It yielded five cell contributions for four distinct records, and
two cell cancellation contributions for one cancelled record. Unknown date,
unclassified CPV and unknown cancellation each counted once. Filtering to an
unmatched code or month preserved these counters and yielded
`selection_unresolved`; all three policy decisions were `limited`. This is a
mapping probe, not SQL/original-byte verification or an implemented consumer.

## Results, refusal and privacy

All nine policy checks stay explicit. Successful reconstruction supplies bindings,
evidence, keys, membership, page accounting, capture completeness, selection and
eligibility. Comparability is `not_applicable/not_required_for_use`; monetary
eligibility is `not_applicable`. The pure evaluator remains authoritative.

The existing verifier requires complete managed, quarantine-free runs. A real
partial/quarantined/no-page capture fails reconstruction with **no sidecar**;
do not fabricate facts to publish `blocked`. Complete-empty still requires its
original archived empty page. After reconstruction, publish the policy's actual
`ready`, `limited`, `blocked` or `not_assessed` decision without an override.
Keep provider status: `empty_capture`, `no_observations_before_cutoff`,
`observed_activity`, `selection_unresolved` and `no_observed_activity` stay distinct.
No decision establishes national coverage, source-current state or market absence.

New canonical private sidecar `nima-cpv-acceptance-v1`, at most **64 KiB**. Bind
subject format/hash, request hash, cutoff, source/run profiles, metric ID/status,
definition/SQL hashes and the producer's unchanged `cohort_sha256`. Embed policy
metadata/hash and complete assessment/checks/counters/grains/limitations. Declare
diagnostic scope as selected unambiguous records before CPV/month filters. Bind
the selection through its request hash; do not copy the semantic request, CPV
cells, source IDs, tax numbers, names, amounts, normalized records or archive paths.
The existing report retains detailed results/evidence; the sidecar remains private.

Reuse the existing canonical encoder and atomic no-clobber publisher, permissions,
fsync and identical-retry behavior. Each retry re-verifies; an earlier sidecar is
never a cached pass. Publication is not atomic with SQL/archive inspection; a
completed artifact may survive interruption and a kill may leave a private temp file.

Reuse the existing seven closed acceptance errors and U1 error mapping, fixed
stdout/stderr vocabulary and hash-only success summary. Exit 0 for published
`ready`/`limited`, 3 for published `blocked`/`not_assessed`, 2 for bad input, 1 for
operational/evidence/contract/size/output failure, 130 for interruption. Failure
does not modify the request/report, original archive or application SQL state.

## Structure, style and verification

Add `src/nima/dataops/cpv_acceptance.py`; extend the existing acceptance CLI and
DataOps dispatcher. The sole producer change is the additive public preparation
result/wrapper in `analytics/cpv_readout.py`. Reuse public file/policy/publisher
APIs; no adapter registry or generic framework. Follow existing frozen records:

```python
@dataclass(frozen=True)
class CpvAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str
```

After approval, test first with pytest (`tests/test_cpv_acceptance*.py`), native
PostgreSQL 17 and owned synthetic originals. Require hand-calculated ten-counter
answers, overlapping/duplicate CPV codes, all classification/date buckets,
cancellation, tied revisions, A→B→A, re-observation, after-cutoff observations,
filters/unresolved selection and genuine complete-empty capture. Preserve the
old preparation API and all existing report bytes/definition/SQL/contract pins.

Prove actual partial/quarantine/raw/SQL/projection/page/membership/principal
refusals, one preparation/one source-cohort read/two sequential read-only
connections, no HTTP/source writes, retry/relocation, removed originals after
prior success, and closed SQL before publication. Cover private path/hash/body/
binding/size/policy failures, all decisions and process interruption before/after
the final link. Require 100% new-code line/branch coverage, meaningful counter/
verification/publication mutations, the unchanged 90% overall floor and isolated
built-wheel CLI operation.

Commands after approval:

```sh
uv run --frozen pytest tests/test_cpv_acceptance.py
just lint
just typecheck
just security
just check
just audit
```

Run cheap gates before expensive proof; hold source stable and overlap independent
local/hosted gates. Require all exact-head hosted jobs before merge readiness.
Do not repeat the unchanged full suite merely to record a documentation status.
Real-cohort reconciliation, reviewed metrics and investigator task proof remain
open. No journal persistence, U3/U4, source activation or release in this scope.

## Owner decisions

Owner approved all three recommended decisions, including implementation:

- **D1 — scope:** one U2 acceptance command/sidecar, reusing the existing verifier
  through an additive frozen preparation result; preserve the old tuple API/bytes.
- **D2 — meaning:** ten explicit counters at their existing pre-filter scope;
  distinct-record cancellation counts, retained provider status and hash-bound selection.
- **D3 — verification:** one fresh preparation per call, unchanged two-connection
  read-only sequence, 1 MiB report/64 KiB sidecar, no sidecar on failed reconstruction.

Approval concerns this bounded consumer. U3/U4, durable acceptance history,
metric certification and actual product/source proof remain separate work.
