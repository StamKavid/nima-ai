# Spec: dataset acceptance policy

Module ID: `dataset-acceptance` (V1-08). Status: **owner approved A1–A3 as
recommended on 2026-11-25, including implementation of the pure-policy slice.** Baseline: main `9273451`
(#222). Extends the [work package](../roadmap/agent-backlog.md#v1-08--dataset-acceptance-and-comparability)
and [release contract](SPEC-release-v1.0.md). This first policy slice does not
complete V1-08's durable-history or real-cohort acceptance requirements.

Pure-policy delivery: #223, main `a4eb99d`, tested `d2d94db` reachable with an
identical tree; all three main jobs passed in run 45639919348. The
[citation consumer](SPEC-citation-acceptance-readout.md) is delivered separately
in #225 at `e6c869d`, under B1–B3. The next
[U1 consumer contract](SPEC-participation-acceptance-readout.md) is a draft under
A3. The first-slice wording below describes the pure policy; durable history
and real-data acceptance remain open.

## Objective and assumptions

An operator or downstream insight can tell whether a specific verified capture
supports a specific analytical use, which records are excluded, and which
limitations remain. A complete response from a government endpoint establishes
neither national coverage nor the truth of every reported field.

Assumptions for review: one trusted local operator; existing PostgreSQL 17,
Python 3.12+ and private archives; explicit stored runs and an observation cutoff;
no new collection. Reuse the existing reconcilers and semantic providers. Do not
build a second normalizer, generic quality framework or orchestration layer.

## Starting point and scope

- U1–U4 already have deterministic providers, SQL parity, bounded readouts and
  [draft definitions](../semantics/metric-catalogue.md). U1–U3's shared snapshot
  requires complete managed runs without quarantine. U4 abstains unless both
  captures are complete, quarantine-free, query-matched and strictly ordered.
- #222 verifies both citation cohorts against originals, including incomplete
  captures, and reports `metric_eligibility: not_assessed_v1_08`. Exact citations
  are a separate draft relationship model, not a fifth numerical metric.
- [V1-01](SPEC-validation-history.md) verifies one published supplier–buyer
  artifact. `contracts/history.py` fixes its contract ID and check vocabulary;
  migration `0010.sql` enforces these identities and 4 KiB journal documents.
  Its existing tables cannot store general dataset-acceptance outcomes unchanged.

First slice: a pure, typed, versioned policy evaluator and its tests. Its caller
supplies facts produced by the existing verification/selection paths. The
evaluator never establishes byte integrity by trusting a JSON `verified: true`
flag. It evaluates evidence supplied through a documented internal boundary;
only an adapter that actually reconstructs a capture may claim verification.
Real SQL tests must exercise that boundary before integration is called proven.

No new command, artifact publication, migration, role grant or journal write is
part of this first slice. A later verified readout adapter and separately reviewed
additive journal contract are required before acceptance is durable or enforced
by consumers. Existing commands gain no gate implicitly.

## Policy and identity

Proposed policy ID `nima.dataset-acceptance`, version `1.0.0`; canonical hash binds
the complete rule definition and closed reason vocabulary. A behavior change
requires a new policy version. Facts bind the semantic request hash, frozen
snapshot/cohort hash, source/connector/normalizer versions, selected runs, cutoff,
and the exact metric or relationship-model definition hash and SQL hash.
The evaluator rejects contradictory or unsupported bindings. Archive paths,
DSNs, attempt IDs and check wall times never enter deterministic identity.

Each use gets its own result, with no cross-use average or trust score:

| Result | Meaning |
|---|---|
| `ready` | Required data checks passed; no applicable limitation was found |
| `limited` | Required checks passed; existing definition permits explicitly listed unknowns/exclusions |
| `blocked` | A known required data invariant or comparability rule failed |
| `not_assessed` | Required evidence or a supported policy/definition is unavailable |

These are data-fitness decisions, distinct from V1-01's verification states and
from a metric's `draft`, `reviewed` or `certified` status. `ready` never promotes a
definition, authorizes V1-09 to use draft metrics, or certifies publisher truth.
Known required-check failure takes precedence over missing proof; missing
required proof takes precedence over limitations and success. An unsupported
use is `not_assessed`.

Checks have fixed IDs and `passed`, `failed`, `not_assessed` or `not_applicable`
outcomes. Reasons come from the policy, never exception strings or source values.
All required checks must pass before `ready` or `limited`. Not-applicable checks
must be explicitly declared for that use; a missing required check is not a pass.
Counters applicable to a use must also be explicit, including genuine zeros.
An omitted diagnostic or denominator counter yields `not_assessed`; it is never
interpreted as zero or allowed to hide a known accounting failure.

## Check contract

| Check ID | Rule and interpretation |
|---|---|
| `bindings` | Request, cohort, versions, cutoff and definition/SQL hashes agree; unknown versions stop assessment |
| `evidence` | Required raw bytes were verified and normalized/SQL facts reconciled through the supported adapter; missing bytes mean not assessed, disagreement blocks |
| `keys` | No duplicate observation/page identities or contradictory facts under one version; repeated valid observations and A→B→A are retained |
| `membership` | Every record/quarantine entry belongs to its declared run/page/index; all admitted references and target evidence belong to the declared cohorts |
| `page_accounting` | Declared page/checkpoint/record totals reconcile, including empty pages and quarantine; an honest incomplete prefix is separate from contradictory totals |
| `capture_completeness` | Collection and normalization completeness and quarantine counts are explicit per run; zero-page partial is never complete-empty |
| `selection` | Inclusive observation cutoff, latest-version selection, ties and excluded observations follow the bound provider; no arbitrary winner |
| `eligibility` | Eligible, excluded, unknown and ambiguous counts reconcile at their declared grains; no source value silently becomes zero |
| `comparability` | U4's same-query, complete, quarantine-free and strictly ordered capture rules hold; not applicable to a single-capture description |

Do not add incompatible counts: page records reconcile to normalized plus
quarantined records; repeated observations do not increase distinct-record
counts. U2 CPV cells can overlap, and U3 supplier participations can overlap, so
neither cell sum is asserted equal to the distinct-record denominator.

An unresolved citation is absence from the selected cohort, not a broken foreign
key or proof of source absence. Ambiguous/mismatched/unknown-type targets remain
classified, never silently become resolved commitments. Membership consistency
can pass while the citation result carries these limitations. Cancelled or revoked
records retain the existing provider's treatment; no new legal-event rule is added.

## Required checks by analytical use

All supported uses require consistent bindings, verified admitted evidence,
valid keys/membership, page accounting and correct selection. Additional rules:

| Use | Required data fitness | Permitted limitations |
|---|---|---|
| U1 supplier–buyer participation | Existing complete-run/no-quarantine gate and distinct-record eligibility accounting | Unknown buyer/country/supplier data, ambiguity and cancellations follow U1's disclosed buckets |
| U2 CPV/month activity | Same complete-run gate; CPV/date parsing and overlapping-cell accounting match U2 | Unknown/unparseable month and unclassified CPV stay visible; no guessing or date-based trend claim |
| U3 buyer concentration | Same complete-run gate; exact resolved/unresolved denominators and joint participation follow U3 | Unresolved/partial suppliers and ambiguity remain visible; zero denominator never yields a share |
| U4 observed change | Both captures complete and quarantine-free, identical declared query, strictly ordered times | Existing ambiguity/exclusions remain disclosed; rule failure blocks comparison with its existing `incomparable` reasons |
| Exact citation inspection | Both admitted source cohorts reconcile, even when no edge resolves | Honest partial captures, unknown lists/types/statuses and unmatched/ambiguous targets are inspectable and yield `limited` |

No observations or only unknown/ambiguous records may produce an existing empty
or unresolved provider result. Acceptance must retain that result status; even
`ready` means only that those data checks passed, never that activity was absent.
Unknown fields unrelated to a use must not block it globally. All present metrics
count records, so monetary eligibility is explicitly `not_applicable`; a future
spend metric needs its own currency, stage, cancellation and allocation contract.

No invented 95% fill-rate, seven-day freshness target, minimum sample size, peer
threshold or national denominator. Report measured counts and query boundaries.
Keep CPV/date/identifier exclusion profiles available to future comparison gates;
this slice does not authorize concentration shifts, market trends or comparisons
between different queries. Completeness of selected captures is not stable market
coverage. V1-09 must specify any additional comparison rule with evidence first.

## Result boundary and code style

Use frozen dataclasses, explicit typed fields, fixed reasons and deterministic
sorting, following the existing style in `semantics/observed_change.py`:

```python
@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str
    reason: str
```

The actual types must validate the closed vocabularies and input relationships.
Return the policy ID/version/hash, bound dataset/use identity, all check outcomes,
data-fitness decision, provider result status and aggregate exclusion/coverage
counts with their grains. Do not copy source names, tax IDs, subjects, arbitrary
errors or physical locations. Detailed lineage remains in the bound readout.
This is an in-process result contract; a serialized export format and storage
limits belong to the later adapter spec, not an implemented-looking CLI here.
Old U1–U4 and `nima-source-citations-v1` bytes/hashes remain unchanged. In particular,
the citation v1 field stays `not_assessed_v1_08`; a future acceptance report binds
to it separately instead of rewriting an immutable artifact.

## Project structure, commands and testing

Policy belongs in `src/nima/contracts/acceptance.py`, with focused tests under
`tests/test_dataset_acceptance.py`; reuse existing public reconciliation and
semantic APIs. Any needed public preparation boundary stays with its current
provider. Planning must confirm those APIs before choosing adapter changes.
No new dependency, service, scheduler, CI rule or generic plugin system.

Verification commands for the proposed implementation, not evidence that this
draft is implemented:

```sh
uv run --frozen pytest tests/test_dataset_acceptance.py
just check
just audit
```

The first command applies after the proposed test file exists. Use pytest,
hand-computed tables and owned disposable PostgreSQL 17 integration fixtures.
Require 100% new policy line/branch coverage and the unchanged overall 90% gate.
Mutate decision precedence, completeness, membership, denominator handling and
unknown/ambiguous classifications; restore source and require the tests to fail.
Preserve existing semantic pins, definition hashes and readout byte fixtures.

## Success criteria and boundaries

- The same frozen facts/use/policy produce the same complete result regardless
  of SQL ordering or archive location. Each required-check failure is identifiable.
- Duplicated, missing and contradictory inputs fail precisely. Partial capture
  allows limited citation inspection while blocking U1–U4 as specified above.
- Unknown dates affect U2 placement, not unrelated U1/U3 counts. U3 joint awards
  preserve overlapping participation; U4 query mismatch/incompleteness abstains.
- Native SQL fixtures feed verified facts into the evaluator; an arbitrary status
  field in an untrusted artifact cannot bypass reconstruction. Missing proof never
  produces success. No database, archive or existing artifact is mutated.
- The actual four-positive owner-machine citation cohort still needs original
  archives and SQL inputs. Synthetic checks and the separate 77-record cohort
  cannot close that reconciliation or V1-08's real-data exit.

Always preserve provenance, unknowns, original bytes and metric status. Ask first
for an additive journal schema/adapter contract, external source access or any
dependency/CI change. Never alter migration 0010, widen source-reader privileges,
re-label the old validator, repair data silently or auto-certify a metric.

## Owner decisions

Owner approved all three recommended decisions on 2026-11-25:

- **A1:** Adopt per-use data-fitness decisions and the table above, preserving
  partial citation inspection and all existing metric rules.
- **A2:** Use explicit integrity/accounting invariants and disclosed counts;
  adopt no arbitrary quality thresholds or new numerical comparison claims.
- **A3:** Implement the bounded pure-policy slice first. Keep existing artifact
  contracts unchanged; scope the verified acceptance adapter and additive durable
  journal contract separately. V1-08 remains open until these and real reconciliation pass.

Execution is limited to this approved slice; the plan and checkpoints are in
`tasks/plan.md` and `tasks/todo.md`. No real-data acceptance, metric review or
certification, deployment or release is recorded by this approval.
