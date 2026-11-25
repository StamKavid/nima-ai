# Spec: verified citation-acceptance readout

Module ID: `citation-acceptance-readout` (V1-08). Status: **draft for owner review,
2026-11-25; B1–B3 not approved.** Baseline: main `a4eb99d` (#223). Extends the
[acceptance policy](SPEC-dataset-acceptance.md) under A3's separately scoped
adapter contract and the [V1-08 work package](../roadmap/agent-backlog.md#v1-08--dataset-acceptance-and-comparability).

## Objective and assumptions

A trusted local operator can inspect the data-fitness decision for one existing
KIMDIS–Diavgeia citation report, with reproducible bindings to its exact bytes,
request, source cohort, model and policy. Start with citation inspection only;
U1–U4 adapters and the durable journal follow as separate work. The policy remains
the authority for decisions; the adapter owns verification and counter assembly.

Assumptions: Python 3.12+, PostgreSQL 17, existing restricted source reader and
private archives, explicit stored runs and cutoff, no network or production
configuration change. The owner's four-positive originals are not available in
this workspace. Synthetic SQL proof cannot close that real-data reconciliation.

## Existing boundary to reuse

`analytics.citation_readout.prepare_citation_readout(dsn, request)` returns a fresh
canonical report and typed `CitationResult`. It already validates the request,
takes one bounded SELECT-only repeatable-read snapshot, reconciles all admitted
original pages/normalized facts/quarantine, and requires model/SQL parity.
Use it once per invocation, including retries. Do not copy its collector or
normalizers, open a second snapshot to assemble counters, or trust a saved JSON
success/coverage flag as evidence that these checks ran.

The existing report is `nima-source-citations-v1`; its
`metric_eligibility: not_assessed_v1_08` stays byte-identical. A new sidecar binds
to it without editing it. The current policy is `nima.dataset-acceptance` `1.0.0`,
definition hash:

```text
f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06
```

Freeze this mapping against that policy's `citations` check/counter vocabulary.
An unreviewed policy version or changed required-counter set fails the adapter
contract. A structurally supported model report whose definition hash is not
admitted by the policy can receive its explicit `not_assessed` decision.

## Proposed interface and verification

New command, **not implemented by this draft**:

```sh
uv run --frozen python -m nima dataops assess-citations \
  --request /PRIVATE/citation-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

Use environment-only `NIMA_DATABASE_URL`. No journal connection or attempt ID.
Reuse the existing private citation-request format, its combined ten-run bound,
source bindings, UTC cutoff and current row/page/byte limits. Paths are private
absolute paths, never credentials or identity. Report basename is a lowercase
SHA-256 plus `.json`; its inspected bytes are bounded to the existing 8 MiB limit.

1. Validate configuration/request and safely read the selected report. Reuse
   descriptor-based helpers: owned private directory/file, no symlink traversal,
   regular file, single hard link and stable metadata through the read. Do not
   import the private `validation._artifact` helper or add another file publisher.
2. Require the inspected bytes' SHA-256 to equal the basename. Reconstruct through
   the existing public preparation API, using the supplied archive bindings.
3. Require byte equality with the inspected report. Decode only the freshly
   generated body for capture/page metadata; obtain selection facts from the
   typed result. Reject unsupported shapes, missing fields/outcomes, wrong types
   or contradictory bindings. Never patch a report or fetch missing originals.
4. Build `DatasetFacts` with `use="citations"`, actual request/cohort/model/SQL
   hashes, cutoff and source-run profiles. Every counter below is measured
   explicitly; no fixture template or `.get(name, 0)` supplies missing evidence.
5. Evaluate through the unchanged pure policy. Validate result bindings against
   the assembled facts and policy metadata, encode the sidecar within its bound,
   close source resources, then publish through the existing private publisher.

Checking one inspected byte snapshot does not guarantee future file availability
or publisher truth. The database/filesystem are not one atomic transaction.
The sidecar's subject is the inspected content hash, not a mutable pathname.

## Counter mapping

`C` means selected, unambiguous KIMDIS source versions from the typed result;
ambiguous source records have their own count and are never arbitrarily selected.
`E` means the model's deduplicated citation edges. Source selection is already at
the request cutoff; page/observation/quarantine counters cover **all admitted
pages**, including after-cutoff evidence, as the existing verifier requires.

| Counter | Grain | Exact mapping |
|---|---|---|
| `observations` | observation | Number of reconciled evidence entries across both sources |
| `pages` | page | Number of verified admitted pages across both sources |
| `page_records` | reported_record | Sum of admitted pages' `record_count`, including quarantined items |
| `quarantined` | quarantined_record | Sum of captures' reconciled `quarantined_count` |
| `selected_records` | source_record | `result.records - len(result.source_ambiguous_ids)`; KIMDIS only |
| `ambiguous_records` | source_record | `len(result.source_ambiguous_ids)`; KIMDIS only |
| `unknown_reference_lists` | source_record | `len(result.unknown_reference_ids)`; known empty lists do not count |
| `unresolved_citations` | citation | `result.outcome_counts["unresolved"]` |
| `ambiguous_targets` | citation | `result.outcome_counts["target_ambiguous"]` |
| `unknown_target_types` | citation | `result.outcome_counts["target_type_unknown"]` |
| `mismatched_target_types` | citation | `result.outcome_counts["target_type_mismatch"]` |
| `unknown_cancellations` | source_record | Members of C whose `cancelled` is `None` |
| `cancelled_records` | source_record | Members of C whose `cancelled` is `True` |
| `revoked_targets` | citation | Edges in E with one selected target version whose status is exactly `REVOKED` |

The last count is edges pointing at revoked targets, not distinct decisions.
Shared targets can contribute once for each citing source record. A pending
revocation is not silently relabelled `REVOKED`; its status stays inspectable in
the referenced source report. Target ambiguity/type/status diagnostics can overlap
and must not be summed into a distinct-record denominator. Monetary eligibility
remains not applicable. No join is upgraded to legal identity or economic equivalence.

## Check mapping and negative results

Successful reconstruction establishes the `bindings`, `evidence`, `keys`,
`membership`, `page_accounting` and `selection` checks. Their scope is the existing
verifier's full admitted cohort, not only matching edges. Producer validation,
parity and explicit counter assembly establish `eligibility`; the policy still
checks its own numeric invariants and definition/profile support.

Derive `capture_completeness` from all captures' collection/normalization flags
and quarantine counts: quarantine gives `failed/quarantined_records`; otherwise
any incomplete capture gives `failed/incomplete_capture`; complete captures give
`passed/ok`. `comparability` is `not_applicable/not_required_for_use` for this use.
These do not override the pure evaluator's decision or perform U4 comparisons.

An honest zero-page partial capture is permitted: disclose `no_admitted_pages`,
make no retrieved-byte/date claim, and preserve the limited policy result.
Complete-empty captures still require their archived empty pages. Unknowns,
unresolved targets and ambiguous source/target versions remain distinct.

Publish any of the four policy decisions **only after** successful subject and
source reconstruction: `ready`, `limited`, `blocked`, `not_assessed`. Negative
data fitness is inspectable and never authorizes a numeric use. If report/raw/SQL
verification itself fails, no verified dataset reference or sidecar is fabricated:
return a fixed command failure. Recording such attempts is later journal work.

## Sidecar and command results

New canonical format `nima-citation-acceptance-v1`, at most 64 KiB of UTF-8:
subject version/hash, semantic request with cutoff/run IDs, verified cohort hash,
source-run profiles, admitted-page evidence scope, complete embedded policy
definition and its hash, and the immutable assessment's checks, required checks,
counts/grains, decision, limitations, provider status and identity hashes.
Validate the shape and cross-field bindings before publication; unsupported fields
and missing required counters are failures, not permissive defaults.

Do not duplicate the source report's record bodies, company names, tax IDs,
subjects, amounts, ADA lists or physical archive paths. The subject hash points
to their existing protected evidence. This versioned output is not a new ODCS
execution engine or a modification to the three existing ODCS contracts.

Reuse canonical encoding with a tighter per-call bound and atomic no-clobber
publication: 0700 directory, 0600 content-addressed JSON, fsync, identical-content
retry verification. No wall clock enters deterministic result identity. Recheck
SQL/originals/report on every retry; an existing sidecar is not a cached pass.
Crash before publication yields no final artifact; retry reconstructs. An identical
completed artifact can be reused after re-verification; conflicting output fails.

Stdout contains fixed operation status, subject/sidecar/policy hashes and the
per-use decision; stderr contains fixed stage events. No DSNs, paths, source
values or arbitrary exceptions. Exit 0: published `ready`/`limited`; 3: published
`blocked`/`not_assessed`; 2: invalid configuration/input; 1: operational, evidence,
contract, size or publication failure; 130: interruption.

Closed failure namespace: `acceptance_input`, `acceptance_limit`,
`acceptance_evidence`, `acceptance_database`, `acceptance_contract`,
`acceptance_output`, `acceptance_interrupted`. Reuse existing citation/reader error
categories through an explicit mapping; never echo the underlying exception.

## Structure, style and verification

Adapter: `src/nima/dataops/citation_acceptance.py`; command:
`src/nima/dataops/acceptance_cli.py`, routed by the existing DataOps dispatcher.
Pure policy stays independent of readers. Follow the existing frozen-record style:

```python
@dataclass(frozen=True)
class CitationAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
```

Use existing Python/Psycopg/file primitives, strict mypy and fixed errors. No new
dependency, CI change, source call, grant, schema migration, schedule or deployment.
Proposed test file/commands apply after implementation, not in this draft:

```sh
uv run --frozen pytest tests/test_citation_acceptance.py
just lint
just typecheck
just security
just check
just audit
```

Acceptance: hand-computed counter fixtures for shared/revoked targets, source and
target ties, A→B→A, unknown/empty references, cancellation, cutoff exclusion and
partial/quarantined/no-page/complete-empty captures. Real PostgreSQL 17/restricted
reader tests must require one preparation call/snapshot, actual original bytes,
all fourteen counters, matching artifact/request/model bindings and no HTTP on
both success **and failure** paths. No test bridge or saved success flag can
bypass verification. Test negative policy decisions separately from broken proof.

Require identical retry/relocation bytes, precise failures for corrupt/missing or
changed reports/SQL/originals, output conflicts and process interruption; retain
source SQL, original/report bytes and metadata. Verify all legacy artifact pins,
100% new-code line/branch coverage with unchanged overall 90% floor, meaningful
counter/verification/publication mutations, installed-wheel operation, full gates
and exact-head hosted CI. Real-cohort reconciliation and certification stay open.

## Owner decisions

- **B1 — scope:** Citation inspection is the first consumer, through one new
  command and sidecar. U1–U4 adapters and durable history remain separate.
- **B2 — provenance and format:** Reconstruct and byte-compare the original report
  before publishing the bounded, versioned sidecar with the fourteen mappings above.
  Preserve current policy and all existing artifact bytes/definitions.
- **B3 — failure behavior:** Publish all four decisions for reconstructed subjects;
  return exit 3 for negative fitness. Broken verification yields a fixed failure
  and no fabricated assessment; every retry re-verifies.

Recommended: accept B1–B3. This draft records no implementation approval, technical
plan, source activation, metric review or real-data acceptance.
